"""
Tests for the AI Orchestrator module.

Coverage:
- AITaskRegistry (register, get_task, duplicate detection)
- Prompt Engine (all 4 builders including build_answer_explanation_prompt)
- analyze_gaps_task logic (empty gaps early return, LLM call, validation)
- generate_quiz_task logic (success, LLM failure)
- expand_content_task logic (success, LLM failure)
- explain_answer_task logic (success, LLM failure, prompt builder)
- LLMGateway (success, rate limit, api error, json decode error, empty response)
- AIOrchestratorService (cache hit, in-progress deduplication, new task dispatch,
  ValueError on unknown task, learning context enrichment exception, get_task_status branches)
- Router endpoints (POST /ai/task, GET /ai/task/{task_id}, 500 error handlers)
"""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.database import get_db
from app.modules.ai_orchestrator.registry import AITaskRegistry
from app.modules.ai_orchestrator.router import router
from app.modules.ai_orchestrator.schemas import (
    AITaskPayload,
    AITaskRequest,
    LearningContextDTO,
    PersonalizedQuizContext,
    TopicContext,
    HistoricalEvent,
    HistoricalFigure,
    GapAnalysisContext,
)
from app.modules.ai_orchestrator.service import AIOrchestratorService
from app.modules.ai_orchestrator.services.prompt_engine import (
    _append_learning_context,
    _truncate,
    _format_historical_context,
    build_gap_analysis_prompt,
    build_content_expansion_prompt,
    build_personalized_quiz_prompt,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

USER_ID = str(uuid4())
TOPIC_ID = str(uuid4())
FIREBASE_UID = "firebase-test-uid"
AUTH_LOOKUP_PATH = "app.modules.ai_orchestrator.router.get_user_by_firebase_uid"


def _fake_user():
    return MagicMock(id=USER_ID)


def _learning_ctx(gaps: list[str] | None = None) -> LearningContextDTO:
    return LearningContextDTO(user_level=3, concept_gaps=gaps or [])


def _topic_ctx() -> TopicContext:
    return TopicContext(
        topic_name="The Crusades",
        topic_description="Medieval military campaigns.",
        period_name="Middle Ages",
        events=[
            HistoricalEvent(
                name="First Crusade",
                description="Launched in 1096.",
                year=1096,
            )
        ],
        figures=[
            HistoricalFigure(
                name="Richard I",
                role="King",
                biography="Led the Third Crusade.",
            )
        ],
    )


def _quiz_ctx() -> PersonalizedQuizContext:
    return PersonalizedQuizContext(
        topic_name="The Crusades",
        summary="Medieval military campaigns.",
        key_facts=["Started in 1096", "Pope Urban II called for it"],
        fun_fact="Crusaders called their enemies 'Saracens'.",
    )


def _gap_analysis_ctx() -> GapAnalysisContext:
    return GapAnalysisContext(
        topic_name="The Crusades",
        topic_description="Medieval military campaigns.",
        period_name="Middle Ages",
        events=[],
        figures=[],
        target_concept="Feudalism",
    )


@pytest.fixture
def app_client() -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": FIREBASE_UID,
        "email": "test@example.com",
    }
    return TestClient(app)


@pytest.fixture
def raw_client() -> TestClient:
    """Client without authentication override."""
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. AITaskRegistry Tests
# ---------------------------------------------------------------------------


class TestAITaskRegistry:
    def test_registered_tasks_contain_all_types(self):
        """All four task types must be discoverable after module load."""
        for task_type in (
            "quiz_generation",
            "gap_analysis",
            "content_expansion",
            "answer_explanation",
        ):
            task = AITaskRegistry.get_task(task_type)
            assert callable(task)

    def test_get_unknown_task_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown task type"):
            AITaskRegistry.get_task("nonexistent_task_type")

    def test_registering_duplicate_type_raises_value_error(self):
        """The registry must protect against accidental double-registration."""
        with pytest.raises(ValueError, match="already registered"):
            AITaskRegistry.register("quiz_generation")(lambda: None)


# ---------------------------------------------------------------------------
# 2. Prompt Engine Tests
# ---------------------------------------------------------------------------


class TestPromptEngineHelpers:
    def test_truncate_short_string_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_truncate_long_string_adds_ellipsis(self):
        text = "a" * 200
        result = _truncate(text, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_truncate_empty_string_returns_empty(self):
        assert _truncate("") == ""

    def test_append_learning_context_without_context_returns_base(self):
        base = "Base prompt.\n"
        result = _append_learning_context(base, None, "level_hint", "intro", "rule")
        assert result == base

    def test_append_learning_context_adds_level_info(self):
        base = "Base prompt.\n"
        ctx = _learning_ctx()
        result = _append_learning_context(
            base, ctx, "Adjust complexity", "Gaps:", "Fix gaps"
        )
        assert "User Level: 3" in result
        assert "Adjust complexity" in result

    def test_append_learning_context_adds_gaps_when_present(self):
        base = "Base prompt.\n"
        ctx = _learning_ctx(["Feudal system", "Papal authority"])
        result = _append_learning_context(base, ctx, "", "Gaps:", "Fix them")
        assert "Feudal system" in result
        assert "Papal authority" in result

    def test_format_historical_context_includes_events_and_figures(self):
        ctx = _topic_ctx()
        formatted = _format_historical_context(ctx)
        assert "First Crusade" in formatted
        assert "Richard I" in formatted
        assert "Middle Ages" in formatted

    def test_format_historical_context_handles_empty_events_and_figures(self):
        ctx = TopicContext(
            topic_name="Empty Topic",
            topic_description="No details.",
            period_name="Unknown Era",
            events=[],
            figures=[],
        )
        formatted = _format_historical_context(ctx)
        assert "Empty Topic" in formatted
        assert "Unknown Era" in formatted


class TestPromptBuilders:
    def test_build_personalized_quiz_prompt_returns_two_strings(self):
        system_p, user_p = build_personalized_quiz_prompt(_quiz_ctx(), _learning_ctx())
        assert isinstance(system_p, str) and len(system_p) > 0
        assert isinstance(user_p, str) and len(user_p) > 0

    def test_build_personalized_quiz_prompt_contains_topic_name(self):
        system_p, user_p = build_personalized_quiz_prompt(_quiz_ctx(), _learning_ctx())
        assert "The Crusades" in user_p

    def test_build_gap_analysis_prompt_returns_two_strings(self):
        system_p, user_p = build_gap_analysis_prompt(
            _gap_analysis_ctx(), _learning_ctx(["Feudalism"])
        )
        assert isinstance(system_p, str) and len(system_p) > 0
        assert isinstance(user_p, str) and len(user_p) > 0

    def test_build_gap_analysis_prompt_includes_gap(self):
        _, user_p = build_gap_analysis_prompt(
            _gap_analysis_ctx(), _learning_ctx(["Feudalism"])
        )
        assert "Feudalism" in user_p

    def test_build_content_expansion_prompt_returns_two_strings(self):
        system_p, user_p = build_content_expansion_prompt(_topic_ctx(), _learning_ctx())
        assert isinstance(system_p, str) and len(system_p) > 0
        assert isinstance(user_p, str) and len(user_p) > 0

    def test_build_content_expansion_prompt_contains_period(self):
        _, user_p = build_content_expansion_prompt(_topic_ctx(), _learning_ctx())
        assert "Middle Ages" in user_p


# ---------------------------------------------------------------------------
# 3. analyze_gaps_task Logic Tests (unit - no Celery broker needed)
# ---------------------------------------------------------------------------


class TestAnalyzeGapsTaskLogic:
    """
    Tests the analyze_gaps_task behavior using Celery's task.apply() API,
    which executes tasks eagerly (synchronously) without a broker.
    """

    def _context(self) -> dict:
        return {
            "topic_name": "The Crusades",
            "topic_description": "Medieval campaigns.",
            "period_name": "Middle Ages",
            "events": [],
            "figures": [],
            "target_concept": "Feudalism",
        }

    def test_with_gaps_calls_llm_and_returns_validated_result(self, monkeypatch):
        """When the task is called, the LLM must be called and the result validated."""
        fake_llm_result = {
            "concept": "Feudalism",
            "explanation": "Student confuses feudal hierarchy.",
            "severity": "medio",
        }
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            lambda sys_p, usr_p: fake_llm_result,
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import analyze_gaps_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 2, "concept_gaps": ["Feudalism"]},
            cache_key="test-key",
        )
        result = analyze_gaps_task.apply(args=[payload.model_dump()])

        assert result.successful()
        data = result.result
        assert data["concept"] == "Feudalism"
        assert data["severity"] == "medio"

    def test_llm_error_marks_task_as_failed(self, monkeypatch):
        """If the LLM call raises an exception, the task must fail (not crash silently)."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            MagicMock(side_effect=Exception("LLM timeout")),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import analyze_gaps_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 2, "concept_gaps": ["Feudalism"]},
            cache_key="",
        )
        result = analyze_gaps_task.apply(args=[payload.model_dump()])

        assert result.failed()


# ---------------------------------------------------------------------------
# 4. AIOrchestratorService Tests
# ---------------------------------------------------------------------------


class TestAIOrchestratorService:
    def _make_service(self, redis_mock: MagicMock) -> AIOrchestratorService:
        with patch(
            "app.modules.ai_orchestrator.service.get_redis_cache",
            return_value=redis_mock,
        ):
            return AIOrchestratorService()

    def _base_request(self, task_type: str = "gap_analysis") -> AITaskRequest:
        return AITaskRequest(
            task_type=task_type,
            reference_id=TOPIC_ID,
            context={
                "topic_name": "The Crusades",
                "topic_description": "Medieval campaigns.",
                "period_name": "Middle Ages",
                "events": [],
                "figures": [],
            },
        )

    def test_returns_cached_result_when_available(self, monkeypatch):
        cached_payload = {"concept_gaps": []}
        redis_mock = MagicMock()
        redis_mock.get.return_value = json.dumps(cached_payload)

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=None)
                )
            ),
        )

        service = self._make_service(redis_mock)
        db_mock = MagicMock()
        request = self._base_request()

        response = service.process_task_request(db_mock, request, USER_ID)

        assert response.status == "completed"
        assert response.source == "cache"
        assert response.data == cached_payload

    def test_returns_existing_task_id_when_processing(self, monkeypatch):
        existing_task_id = "celery-task-abc123"
        redis_mock = MagicMock()
        # First call (cache check) returns None; second call (processing check) returns task_id
        redis_mock.get.side_effect = [None, existing_task_id]

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=None)
                )
            ),
        )

        service = self._make_service(redis_mock)
        db_mock = MagicMock()
        request = self._base_request()

        response = service.process_task_request(db_mock, request, USER_ID)

        assert response.status == "processing"
        assert response.task_id == existing_task_id

    def test_dispatches_new_celery_task_when_no_cache(self, monkeypatch):
        redis_mock = MagicMock()
        redis_mock.get.return_value = None  # No cache, no in-progress task

        fake_task_id = "new-celery-task-id"
        fake_celery_task = MagicMock()
        fake_celery_task.delay.return_value = MagicMock(id=fake_task_id)

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=None)
                )
            ),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.registry.AITaskRegistry.get_task",
            lambda task_type: fake_celery_task,
        )

        service = self._make_service(redis_mock)
        db_mock = MagicMock()
        request = self._base_request()

        response = service.process_task_request(db_mock, request, USER_ID)

        assert response.status == "processing"
        assert response.task_id == fake_task_id
        fake_celery_task.delay.assert_called_once()

    def test_returns_failed_when_context_empty(self, monkeypatch):
        redis_mock = MagicMock()
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=None)
                )
            ),
        )

        service = self._make_service(redis_mock)
        db_mock = MagicMock()

        request = AITaskRequest(
            task_type="gap_analysis",
            reference_id=TOPIC_ID,
            context={},  # empty context triggers validation error
        )

        response = service.process_task_request(db_mock, request, USER_ID)

        assert response.status == "failed"
        assert "context" in response.error.lower()


# ---------------------------------------------------------------------------
# 5. Router Tests
# ---------------------------------------------------------------------------


class TestAITaskRouter:
    def test_post_task_returns_202_processing(
        self, app_client: TestClient, monkeypatch
    ):
        fake_task_id = str(uuid4())
        monkeypatch.setattr(AUTH_LOOKUP_PATH, lambda db, uid: _fake_user())
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.router.orchestrator_service.process_task_request",
            lambda db, req, user_id: MagicMock(
                status="processing",
                task_id=fake_task_id,
                source=None,
                data=None,
                error=None,
                model_dump=lambda: {
                    "status": "processing",
                    "task_id": fake_task_id,
                    "source": None,
                    "data": None,
                    "error": None,
                },
            ),
        )

        response = app_client.post(
            "/ai/task",
            json={
                "task_type": "gap_analysis",
                "reference_id": TOPIC_ID,
                "context": {
                    "topic_name": "The Crusades",
                    "topic_description": "Medieval campaigns.",
                    "period_name": "Middle Ages",
                    "events": [],
                    "figures": [],
                },
            },
        )

        assert response.status_code == 202
        assert response.json()["status"] == "processing"
        assert response.json()["task_id"] == fake_task_id

    def test_post_task_user_not_found_returns_404(
        self, app_client: TestClient, monkeypatch
    ):
        monkeypatch.setattr(AUTH_LOOKUP_PATH, lambda db, uid: None)

        response = app_client.post(
            "/ai/task",
            json={
                "task_type": "gap_analysis",
                "reference_id": TOPIC_ID,
                "context": {
                    "topic_name": "The Crusades",
                    "topic_description": "Medieval campaigns.",
                    "period_name": "Middle Ages",
                    "events": [],
                    "figures": [],
                },
            },
        )

        assert response.status_code == 404
        assert "sync" in response.json()["detail"]

    def test_post_task_without_auth_returns_403(self, raw_client: TestClient):
        response = raw_client.post(
            "/ai/task",
            json={
                "task_type": "gap_analysis",
                "reference_id": TOPIC_ID,
                "context": {},
            },
        )

        assert response.status_code == 403

    def test_post_task_invalid_task_type_returns_422(
        self, app_client: TestClient, monkeypatch
    ):
        monkeypatch.setattr(AUTH_LOOKUP_PATH, lambda db, uid: _fake_user())

        response = app_client.post(
            "/ai/task",
            json={
                "task_type": "invalid_type",
                "reference_id": TOPIC_ID,
                "context": {},
            },
        )

        assert response.status_code == 422

    def test_get_task_status_returns_completed(
        self, app_client: TestClient, monkeypatch
    ):
        task_id = str(uuid4())
        fake_data = {"concept_gaps": []}

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.router.orchestrator_service.get_task_status",
            lambda tid: MagicMock(
                status="completed",
                task_id=tid,
                source="computed",
                data=fake_data,
                error=None,
                model_dump=lambda: {
                    "status": "completed",
                    "task_id": tid,
                    "source": "computed",
                    "data": fake_data,
                    "error": None,
                },
            ),
        )

        response = app_client.get(f"/ai/task/{task_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["data"] == fake_data

    def test_get_task_status_returns_processing(
        self, app_client: TestClient, monkeypatch
    ):
        task_id = str(uuid4())

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.router.orchestrator_service.get_task_status",
            lambda tid: MagicMock(
                status="processing",
                task_id=tid,
                source=None,
                data=None,
                error=None,
                model_dump=lambda: {
                    "status": "processing",
                    "task_id": tid,
                    "source": None,
                    "data": None,
                    "error": None,
                },
            ),
        )

        response = app_client.get(f"/ai/task/{task_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "processing"

    def test_post_task_raises_500_on_unexpected_error(
        self, app_client: TestClient, monkeypatch
    ):
        """Unexpected exceptions in the POST handler must return HTTP 500."""
        monkeypatch.setattr(AUTH_LOOKUP_PATH, lambda db, uid: _fake_user())
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.router.orchestrator_service.process_task_request",
            MagicMock(side_effect=RuntimeError("unexpected boom")),
        )

        response = app_client.post(
            "/ai/task",
            json={
                "task_type": "gap_analysis",
                "reference_id": TOPIC_ID,
                "context": {
                    "topic_name": "The Crusades",
                    "topic_description": "Medieval campaigns.",
                    "period_name": "Middle Ages",
                    "events": [],
                    "figures": [],
                },
            },
        )

        assert response.status_code == 500
        assert "unexpected boom" in response.json()["detail"]

    def test_get_task_status_raises_500_on_unexpected_error(
        self, app_client: TestClient, monkeypatch
    ):
        """Unexpected exceptions in the GET handler must return HTTP 500."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.router.orchestrator_service.get_task_status",
            MagicMock(side_effect=RuntimeError("celery unavailable")),
        )

        response = app_client.get(f"/ai/task/{uuid4()}")

        assert response.status_code == 500
        assert "celery unavailable" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 6. Additional Service Tests (missing lines: 31-33, 114-115, 135-148)
# ---------------------------------------------------------------------------


class TestAIOrchestratorServiceExtra:
    def _make_service(self, redis_mock: MagicMock) -> AIOrchestratorService:
        with patch(
            "app.modules.ai_orchestrator.service.get_redis_cache",
            return_value=redis_mock,
        ):
            return AIOrchestratorService()

    def test_fetch_learning_context_returns_none_on_exception(self, monkeypatch):
        """If LearningFacade raises, _fetch_learning_context must return None silently."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(side_effect=Exception("DB connection error")),
        )
        redis_mock = MagicMock()
        service = self._make_service(redis_mock)
        db_mock = MagicMock()

        result = service._fetch_learning_context(db_mock, USER_ID, TOPIC_ID)

        assert result is None

    def test_fetch_learning_context_returns_dto_when_facade_returns_data(
        self, monkeypatch
    ):
        """When LearningFacade returns a context dict, it is parsed into LearningContextDTO."""
        fake_ctx = {"user_level": 5, "concept_gaps": ["Feudalism"]}
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=fake_ctx)
                )
            ),
        )
        redis_mock = MagicMock()
        service = self._make_service(redis_mock)
        db_mock = MagicMock()

        result = service._fetch_learning_context(db_mock, USER_ID, TOPIC_ID)

        assert result is not None
        assert result.user_level == 5
        assert "Feudalism" in result.concept_gaps

    def test_returns_failed_when_registry_raises_value_error(self, monkeypatch):
        """If the registry raises ValueError, service must return a failed response."""
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.LearningFacade",
            MagicMock(
                return_value=MagicMock(
                    get_user_learning_context=MagicMock(return_value=None)
                )
            ),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.registry.AITaskRegistry.get_task",
            MagicMock(side_effect=ValueError("Unknown task type: 'bad_type'")),
        )

        service = self._make_service(redis_mock)
        db_mock = MagicMock()
        request = AITaskRequest(
            task_type="gap_analysis",
            reference_id=TOPIC_ID,
            context={
                "topic_name": "X",
                "topic_description": "Y",
                "period_name": "Z",
                "events": [],
                "figures": [],
            },
        )

        response = service.process_task_request(db_mock, request, USER_ID)

        assert response.status == "failed"
        assert "Unknown task type" in response.error

    def test_get_task_status_completed(self, monkeypatch):
        """get_task_status returns 'completed' with data when the Celery task succeeded."""
        fake_result = {"concept_gaps": []}
        mock_async = MagicMock()
        mock_async.successful.return_value = True
        mock_async.failed.return_value = False
        mock_async.result = fake_result

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.AsyncResult",
            lambda task_id: mock_async,
        )

        redis_mock = MagicMock()
        service = self._make_service(redis_mock)
        response = service.get_task_status("some-task-id")

        assert response.status == "completed"
        assert response.source == "computed"
        assert response.data == fake_result

    def test_get_task_status_failed(self, monkeypatch):
        """get_task_status returns 'failed' with the error message when Celery task failed."""
        mock_async = MagicMock()
        mock_async.successful.return_value = False
        mock_async.failed.return_value = True
        mock_async.result = Exception("LLM exploded")

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.AsyncResult",
            lambda task_id: mock_async,
        )

        redis_mock = MagicMock()
        service = self._make_service(redis_mock)
        response = service.get_task_status("some-task-id")

        assert response.status == "failed"
        assert "LLM exploded" in response.error

    def test_get_task_status_pending(self, monkeypatch):
        """get_task_status returns 'processing' when the task state is PENDING."""
        mock_async = MagicMock()
        mock_async.successful.return_value = False
        mock_async.failed.return_value = False
        mock_async.state = "PENDING"

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.service.AsyncResult",
            lambda task_id: mock_async,
        )

        redis_mock = MagicMock()
        service = self._make_service(redis_mock)
        response = service.get_task_status("some-task-id")

        assert response.status == "processing"


# ---------------------------------------------------------------------------
# 7. generate_quiz_task and expand_content_task Tests (missing L67-88, L168-186)
# ---------------------------------------------------------------------------


class TestGenerateQuizTask:
    def _context(self) -> dict:
        return {
            "topic_name": "The Crusades",
            "summary": "Medieval military campaigns.",
            "key_facts": ["Pope Urban II called for it", "Started in 1096"],
            "fun_fact": "Crusaders called enemies 'Saracens'.",
        }

    def test_success_returns_validated_quiz(self, monkeypatch):
        """generate_quiz_task must call the LLM and return a validated quiz."""
        fake_llm_result = {
            "questions": [
                {
                    "text": "When did the First Crusade start?",
                    "options": ["1066", "1096", "1204", "1453"],
                    "correct_index": 1,
                    "concept": "First Crusade",
                }
            ]
        }
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            lambda sys_p, usr_p: fake_llm_result,
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import generate_quiz_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 2, "concept_gaps": []},
            cache_key="",
        )
        result = generate_quiz_task.apply(args=[payload.model_dump()])

        assert result.successful()
        assert len(result.result["questions"]) == 1
        assert result.result["questions"][0]["concept"] == "First Crusade"

    def test_llm_error_marks_task_as_failed(self, monkeypatch):
        """generate_quiz_task must fail when the LLM raises an exception."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            MagicMock(side_effect=Exception("LLM timeout")),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import generate_quiz_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 2, "concept_gaps": []},
            cache_key="",
        )
        result = generate_quiz_task.apply(args=[payload.model_dump()])

        assert result.failed()


class TestExpandContentTask:
    def _context(self) -> dict:
        return {
            "topic_name": "The Crusades",
            "topic_description": "Medieval military campaigns.",
            "period_name": "Middle Ages",
            "events": [],
            "figures": [],
        }

    def test_success_returns_validated_content(self, monkeypatch):
        """expand_content_task must call the LLM and return validated expanded content."""
        fake_llm_result = {
            "content": {
                "summary": "The Crusades were medieval military campaigns.",
                "key_facts": ["Started in 1096", "Called by Pope Urban II"],
                "fun_fact": "The word crusade comes from the Latin 'crux'.",
            }
        }
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            lambda sys_p, usr_p: fake_llm_result,
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import expand_content_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 3, "concept_gaps": []},
            cache_key="",
        )
        result = expand_content_task.apply(args=[payload.model_dump()])

        assert result.successful()
        assert result.result["content"]["summary"] is not None
        assert len(result.result["content"]["key_facts"]) == 2

    def test_llm_error_marks_task_as_failed(self, monkeypatch):
        """expand_content_task must fail when the LLM raises an exception."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            MagicMock(side_effect=Exception("API connection error")),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import expand_content_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            learning_context={"user_level": 3, "concept_gaps": []},
            cache_key="",
        )
        result = expand_content_task.apply(args=[payload.model_dump()])

        assert result.failed()


# ---------------------------------------------------------------------------
# 8. LLM Gateway Tests (missing L14-35)
# ---------------------------------------------------------------------------


class TestLLMGateway:
    """Tests for generate_structured_json in llm_gateway.py."""

    def test_success_returns_parsed_dict(self, monkeypatch):
        """A valid JSON response from OpenAI must be returned as a dict."""
        fake_response = MagicMock()
        fake_response.choices[0].message.content = '{"concept_gaps": []}'

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.services.llm_gateway.client.chat.completions.create",
            lambda **kwargs: fake_response,
        )

        from app.modules.ai_orchestrator.services.llm_gateway import (
            generate_structured_json,
        )

        result = generate_structured_json("system prompt", "user prompt")

        assert result == {"concept_gaps": []}

    def test_empty_response_raises_llm_gateway_exception(self, monkeypatch):
        """An empty content response must raise LLMGatewayException."""
        fake_response = MagicMock()
        fake_response.choices[0].message.content = None

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.services.llm_gateway.client.chat.completions.create",
            lambda **kwargs: fake_response,
        )

        from app.modules.ai_orchestrator.services.llm_gateway import (
            generate_structured_json,
            LLMGatewayException,
        )

        with pytest.raises(LLMGatewayException, match="Empty response"):
            generate_structured_json("system", "user")

    def test_api_error_raises_llm_gateway_exception(self, monkeypatch):
        """An OpenAI APIError must be wrapped into LLMGatewayException."""
        from openai import APIError

        # Use a subclass-compatible raise without version-dependent constructor kwargs
        class FakeAPIError(APIError):
            def __init__(self):
                super().__init__("Bad request", request=MagicMock(), body=None)

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.services.llm_gateway.client.chat.completions.create",
            MagicMock(side_effect=FakeAPIError()),
        )

        from app.modules.ai_orchestrator.services.llm_gateway import (
            generate_structured_json,
            LLMGatewayException,
        )

        with pytest.raises(LLMGatewayException, match="OpenAI API Error"):
            generate_structured_json("system", "user")

    def test_invalid_json_raises_llm_gateway_exception(self, monkeypatch):
        """A non-JSON response from the LLM must raise LLMGatewayException."""
        fake_response = MagicMock()
        fake_response.choices[0].message.content = "not valid json {{"

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.services.llm_gateway.client.chat.completions.create",
            lambda **kwargs: fake_response,
        )

        from app.modules.ai_orchestrator.services.llm_gateway import (
            generate_structured_json,
            LLMGatewayException,
        )

        with pytest.raises(LLMGatewayException, match="valid JSON"):
            generate_structured_json("system", "user")

    def test_rate_limit_error_is_re_raised(self, monkeypatch):
        """RateLimitError must be re-raised as-is so Celery autoretry catches it."""
        from openai import RateLimitError

        monkeypatch.setattr(
            "app.modules.ai_orchestrator.services.llm_gateway.client.chat.completions.create",
            MagicMock(
                side_effect=RateLimitError(
                    "rate limit", response=MagicMock(), body=None
                )
            ),
        )

        from app.modules.ai_orchestrator.services.llm_gateway import (
            generate_structured_json,
        )

        with pytest.raises(RateLimitError):
            generate_structured_json("system", "user")


# ---------------------------------------------------------------------------
# 9. explain_answer_task Tests
# ---------------------------------------------------------------------------


class TestExplainAnswerTask:
    def _context(self) -> dict:
        return {
            "question": "In what year did the First Crusade begin?",
            "user_answer": "1066",
            "correct_answer": "1096",
            "topic_name": "The First Crusade",
        }

    def test_success_returns_explanation_feedback(self, monkeypatch):
        """explain_answer_task must call the LLM and return explanation, key_concept and tip."""
        fake_llm_result = {
            "explanation": (
                "1066 is the year of the Battle of Hastings, not the First Crusade. "
                "The First Crusade began in 1096 after Pope Urban II's call."
            ),
            "key_concept": "First Crusade Timeline",
            "tip": "Remember: 1096 for the Crusade, 1066 for Hastings.",
        }
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            lambda sys_p, usr_p: fake_llm_result,
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import explain_answer_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            cache_key="",
        )
        result = explain_answer_task.apply(args=[payload.model_dump()])

        assert result.successful()
        data = result.result
        assert "explanation" in data
        assert "key_concept" in data
        assert "tip" in data
        assert "First Crusade" in data["key_concept"]

    def test_llm_error_marks_task_as_failed(self, monkeypatch):
        """explain_answer_task must fail when the LLM raises an exception."""
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.generate_structured_json",
            MagicMock(side_effect=Exception("LLM timeout")),
        )
        monkeypatch.setattr(
            "app.modules.ai_orchestrator.tasks.get_redis_cache",
            lambda: MagicMock(setex=MagicMock()),
        )

        from app.modules.ai_orchestrator.tasks import explain_answer_task

        payload = AITaskPayload(
            reference_id=TOPIC_ID,
            user_id=USER_ID,
            context=self._context(),
            cache_key="",
        )
        result = explain_answer_task.apply(args=[payload.model_dump()])

        assert result.failed()

    def test_prompt_builder_includes_question_and_answers(self):
        """build_answer_explanation_prompt must embed all 4 context fields in the user prompt."""
        from app.modules.ai_orchestrator.schemas import AnswerExplanationContext
        from app.modules.ai_orchestrator.services.prompt_engine import (
            build_answer_explanation_prompt,
        )

        ctx = AnswerExplanationContext(
            question="When did the First Crusade start?",
            user_answer="1066",
            correct_answer="1096",
            topic_name="The First Crusade",
        )
        system_p, user_p = build_answer_explanation_prompt(ctx)

        assert isinstance(system_p, str) and len(system_p) > 0
        assert "1066" in user_p
        assert "1096" in user_p
        assert "When did the First Crusade start?" in user_p
