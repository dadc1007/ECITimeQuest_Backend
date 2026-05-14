import json
import logging
from typing import Dict, Any
from pydantic import ValidationError
from openai import RateLimitError, APIConnectionError
from app.modules.ai_orchestrator.schemas import (
    AITaskPayload,
    AnswerExplanationContext,
    AnswerExplanationGeneratedResponse,
    LearningContextDTO,
    PersonalizedQuizContext,
    TopicContext,
    GapAnalysisContext,
    QuizGeneratedResponse,
    GapAnalysisResponse,
    ContentExpansionGeneratedResponse,
)
from app.workers.celery_app import celery_app
from app.modules.ai_orchestrator.services.llm_gateway import (
    generate_structured_json,
    LLMGatewayException,
)
from app.modules.ai_orchestrator.services.redis_cache import get_redis_cache
from app.modules.ai_orchestrator.services.prompt_engine import (
    build_personalized_quiz_prompt,
    build_gap_analysis_prompt,
    build_content_expansion_prompt,
    build_answer_explanation_prompt,
)
from app.modules.ai_orchestrator.registry import AITaskRegistry

logger = logging.getLogger(__name__)


def _save_to_cache(cache_key: str, data: dict, ttl: int = 21600):
    if cache_key:
        redis_client = get_redis_cache()
        redis_client.setex(cache_key, ttl, json.dumps(data))


def _validate_and_return(result: dict, response_model, cache_key: str):
    validated_result = response_model(**result)
    _save_to_cache(cache_key, validated_result.model_dump())
    return validated_result.model_dump()


@AITaskRegistry.register("quiz_generation")
@celery_app.task(
    bind=True,
    autoretry_for=(
        RateLimitError,
        APIConnectionError,
        LLMGatewayException,
        ValidationError,
    ),
    retry_backoff=True,  # Exponential Backoff (1s, 2s, 4s...)
    retry_kwargs={"max_retries": 3},
    name="ai_orchestrator.generate_quiz",
)
def generate_quiz_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a quiz for a specific topic.
    Saves the result in the domain cache.
    """
    p = AITaskPayload(**payload)
    logger.info(
        f"Starting generate_quiz_task for reference_id: {p.reference_id}, user_id: {p.user_id}"
    )

    try:
        quiz_ctx = PersonalizedQuizContext(**p.context)
        learning_ctx = LearningContextDTO(**(p.learning_context or {}))
        system_prompt, user_prompt = build_personalized_quiz_prompt(
            quiz_ctx, learning_ctx
        )

        logger.debug(
            f"Calling OpenAI for topic {p.context.get('topic_name', 'Unknown Topic')}"
        )

        result = generate_structured_json(system_prompt, user_prompt)

        logger.info(
            f"Successfully generated and cached quiz for {p.reference_id} / {p.user_id}"
        )

        return _validate_and_return(result, QuizGeneratedResponse, p.cache_key)
    except Exception as e:
        logger.error(f"Error in generate_quiz_task for {p.reference_id}: {str(e)}")
        raise self.retry(exc=e)


@AITaskRegistry.register("gap_analysis")
@celery_app.task(
    bind=True,
    autoretry_for=(
        RateLimitError,
        APIConnectionError,
        LLMGatewayException,
        ValidationError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="ai_orchestrator.analyze_gaps",
)
def analyze_gaps_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes a specific concept gap to identify why the student is struggling.
    Saves the result in the domain cache.
    """
    p = AITaskPayload(**payload)

    logger.info(
        f"Starting analyze_gaps_task for reference: {p.reference_id}, user: {p.user_id}"
    )

    try:
        gap_ctx = GapAnalysisContext(**p.context)
        learning_ctx = LearningContextDTO(**(p.learning_context or {}))
        system_prompt, user_prompt = build_gap_analysis_prompt(gap_ctx, learning_ctx)

        logger.debug(
            f"Calling OpenAI for gap analysis of concept: {gap_ctx.target_concept}"
        )

        result = generate_structured_json(system_prompt, user_prompt)
        logger.info(f"Successfully analyzed gap for {p.reference_id} / {p.user_id}")

        return _validate_and_return(result, GapAnalysisResponse, p.cache_key)
    except Exception as e:
        logger.error(f"Error in analyze_gaps_task for {p.reference_id}: {str(e)}")
        raise self.retry(exc=e)


@AITaskRegistry.register("content_expansion")
@celery_app.task(
    bind=True,
    autoretry_for=(
        RateLimitError,
        APIConnectionError,
        LLMGatewayException,
        ValidationError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="ai_orchestrator.expand_content",
)
def expand_content_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expands on a historical figure or event to provide more lore/details.
    """
    p = AITaskPayload(**payload)

    logger.info(
        f"Starting expand_content_task for reference: {p.reference_id}, user: {p.user_id}"
    )

    try:
        topic_ctx = TopicContext(**p.context)
        learning_ctx = LearningContextDTO(**(p.learning_context or {}))
        system_prompt, user_prompt = build_content_expansion_prompt(
            topic_ctx, learning_ctx
        )
        result = generate_structured_json(system_prompt, user_prompt)
        logger.info(f"Successfully expanded content for {p.reference_id} / {p.user_id}")

        return _validate_and_return(
            result, ContentExpansionGeneratedResponse, p.cache_key
        )
    except Exception as e:
        logger.error(f"Error in expand_content_task for {p.reference_id}: {str(e)}")
        raise self.retry(exc=e)


@AITaskRegistry.register("answer_explanation")
@celery_app.task(
    bind=True,
    autoretry_for=(
        RateLimitError,
        APIConnectionError,
        LLMGatewayException,
        ValidationError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="ai_orchestrator.explain_answer",
)
def explain_answer_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Explains why a quiz answer is incorrect and provides targeted feedback.
    Receives: question, user_answer (wrong), correct_answer, topic_name.
    Returns: explanation, key_concept, tip.

    Note: learning_context is intentionally not used by this task.
    The AITaskPayload contract carries it for architectural consistency,
    but answer feedback does not require user profiling.
    """
    p = AITaskPayload(**payload)

    logger.info(
        f"Starting explain_answer_task for reference: {p.reference_id}, user: {p.user_id}"
    )

    try:
        answer_ctx = AnswerExplanationContext(**p.context)
        system_prompt, user_prompt = build_answer_explanation_prompt(answer_ctx)
        result = generate_structured_json(system_prompt, user_prompt)

        logger.info(
            f"Successfully generated answer explanation for {p.reference_id} / {p.user_id}"
        )

        return _validate_and_return(
            result, AnswerExplanationGeneratedResponse, p.cache_key
        )
    except Exception as e:
        logger.error(f"Error in explain_answer_task for {p.reference_id}: {str(e)}")
        raise self.retry(exc=e)
