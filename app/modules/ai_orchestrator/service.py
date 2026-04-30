import json
import hashlib
import logging
from typing import Optional
from sqlalchemy.orm import Session
from celery.result import AsyncResult
from app.modules.learning.facade import LearningFacade
from app.modules.ai_orchestrator.registry import AITaskRegistry
from app.modules.ai_orchestrator.services.redis_cache import get_redis_cache
from app.modules.ai_orchestrator.services.prompt_engine import PROMPT_VERSIONS
from app.modules.ai_orchestrator.schemas import (
    AITaskPayload,
    AITaskRequest,
    AITaskResponse,
    LearningContextDTO,
)
from app.modules.ai_orchestrator import tasks  # Trigger task registration

logger = logging.getLogger(__name__)


class AIOrchestratorService:
    def _fetch_learning_context(
        self, db: Session, user_id: str, reference_id: str
    ) -> Optional[LearningContextDTO]:
        """Fetches and returns the user's learning context. Returns None on failure."""
        try:
            learning_facade = LearningFacade(db)
            context_dict = learning_facade.get_user_learning_context(
                user_id=user_id, topic_id=reference_id
            )
            if context_dict:
                return LearningContextDTO(**context_dict)
        except Exception:
            pass
        return None

    def _validate_request(self, request: AITaskRequest) -> Optional[AITaskResponse]:
        """Validates that required fields are present and correct."""
        if (
            not hasattr(request, "context")
            or request.context is None
            or (isinstance(request.context, dict) and not request.context)
        ):
            return AITaskResponse(
                status="failed",
                error="The 'context' field is required and cannot be empty.",
            )
        return None

    def __init__(self):
        self.redis_cache = get_redis_cache()

    def _get_cache_key(
        self,
        request: AITaskRequest,
        user_id: str,
        learning_context: Optional[LearningContextDTO],
    ) -> str:
        """Centralized cache key generation using semantic hashing."""
        combined_context = {
            "task_context": request.context,
            "learning_context": (
                learning_context.model_dump() if learning_context else {}
            ),
        }
        context_str = json.dumps(combined_context, sort_keys=True)
        context_hash = hashlib.sha256(context_str.encode("utf-8")).hexdigest()[:12]
        version = PROMPT_VERSIONS.get(request.task_type, "v1")

        return f"ai:cache:{version}:{request.task_type}:{request.reference_id}:{user_id}:{context_hash}"

    def process_task_request(
        self, db: Session, request: AITaskRequest, user_id: Optional[str] = None
    ) -> AITaskResponse:
        """
        Handles incoming task requests efficiently:
        1. Fetches the User Learning Context using LearningFacade.
        2. Returns cached final data if available (using hash-based caching).
        3. Returns existing task_id if another worker is already processing it.
        4. Enqueues a new Celery task and locks it in Redis.
        """
        learning_context = self._fetch_learning_context(
            db, user_id, request.reference_id
        )

        # Validate required fields
        validation_error = self._validate_request(request)
        if validation_error:
            logger.debug("Validation failed for request")
            return validation_error
        cache_key = self._get_cache_key(request, user_id, learning_context)

        # 1. Check if the final result is already cached
        cached_data = self.redis_cache.get(cache_key)
        if cached_data:
            logger.debug("The task is already cached, returning cached data.")
            return AITaskResponse(
                status="completed", source="cache", data=json.loads(cached_data)
            )

        # 2. Prevent duplicate processing by checking if a task is already in progress for the same content
        processing_key = f"processing:{cache_key}"
        existing_task_id = self.redis_cache.get(processing_key)
        if existing_task_id:
            logger.debug("The task is already processing, returning existing task_id.")
            return AITaskResponse(status="processing", task_id=existing_task_id)

        try:
            task_func = AITaskRegistry.get_task(request.task_type)
        except ValueError as e:
            return AITaskResponse(status="failed", error=str(e))

        payload = AITaskPayload(
            reference_id=request.reference_id,
            user_id=user_id,
            context=request.context,
            cache_key=cache_key,
            learning_context=(
                learning_context.model_dump() if learning_context else None
            ),
        )

        task = task_func.delay(payload.model_dump())

        # 5. Mark as processing to prevent duplicate tasks
        # TTL of 300 seconds (5 minutes) to avoid deadlocks if a worker crashes
        self.redis_cache.setex(processing_key, 300, task.id)

        return AITaskResponse(status="processing", task_id=task.id)

    def get_task_status(self, task_id: str) -> AITaskResponse:
        """
        Queries the Celery Result Backend to get the status of a task.
        """
        task_result = AsyncResult(task_id)
        response = AITaskResponse(status="processing", task_id=task_id)

        if task_result.successful():
            response.status = "completed"
            response.source = "computed"
            response.data = task_result.result
        elif task_result.failed():
            response.status = "failed"
            response.error = str(task_result.result)
        elif task_result.state == "PENDING":
            response.status = "processing"

        return response


orchestrator_service = AIOrchestratorService()
