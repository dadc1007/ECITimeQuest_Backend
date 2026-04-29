import json
import logging
from typing import Dict, Any
from pydantic import ValidationError
from openai import RateLimitError, APIConnectionError
from app.modules.ai_orchestrator.schemas import (
    LearningContextDTO,
    PersonalizedQuizContext,
    TopicContext,
    QuizGeneratedResponse,
    GapAnalysisGeneratedResponse,
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
def generate_quiz_task(
    self,
    reference_id: str,
    user_id: str,
    context: Dict[str, Any],
    learning_context: Dict[str, Any],
    cache_key: str = "",
) -> Dict[str, Any]:
    """
    Generates a quiz for a specific topic.
    Saves the result in the domain cache.
    """
    logger.info(
        f"Starting generate_quiz_task for reference_id: {reference_id}, user_id: {user_id}"
    )

    try:
        quiz_ctx = PersonalizedQuizContext(**context)
        learning_ctx = LearningContextDTO(**learning_context)
        system_prompt, user_prompt = build_personalized_quiz_prompt(
            quiz_ctx, learning_ctx
        )
        logger.debug(
            f"Calling OpenAI for topic {context.get('topic_name', 'Unknown Topic')}"
        )
        result = generate_structured_json(system_prompt, user_prompt)
        logger.info(
            f"Successfully generated and cached quiz for {reference_id} / {user_id}"
        )

        return _validate_and_return(result, QuizGeneratedResponse, cache_key)
    except Exception as e:
        logger.error(f"Error in generate_quiz_task for {reference_id}: {str(e)}")
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
def analyze_gaps_task(
    self,
    reference_id: str,
    user_id: str,
    context: Dict[str, Any],
    learning_context: Dict[str, Any],
    cache_key: str = "",
) -> Dict[str, Any]:
    """
    Analyzes student errors to identify core concept gaps.
    Saves the result in the domain cache.
    """
    logger.info(
        f"Starting analyze_gaps_task for reference: {reference_id}, user: {user_id}"
    )

    try:
        topic_ctx = TopicContext(**context)
        learning_ctx = LearningContextDTO(**learning_context)

        # If there are no gaps, skip the AI call and return empty result immediately
        if not learning_ctx.concept_gaps:
            logger.info(
                f"No gaps found in learning_ctx for {reference_id} / {user_id}, skipping AI call."
            )
            return _validate_and_return(
                {"concept_gaps": []}, GapAnalysisGeneratedResponse, cache_key
            )

        system_prompt, user_prompt = build_gap_analysis_prompt(topic_ctx, learning_ctx)
        logger.debug("Calling OpenAI for gap analysis")
        result = generate_structured_json(system_prompt, user_prompt)
        logger.info(f"Successfully analyzed gaps for {reference_id} / {user_id}")

        return _validate_and_return(result, GapAnalysisGeneratedResponse, cache_key)
    except Exception as e:
        logger.error(f"Error in analyze_gaps_task for {reference_id}: {str(e)}")
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
def expand_content_task(
    self,
    reference_id: str,
    user_id: str,
    context: Dict[str, Any],
    learning_context: Dict[str, Any],
    cache_key: str = "",
) -> Dict[str, Any]:
    """
    Expands on a historical figure or event to provide more lore/details.
    """
    logger.info(
        f"Starting expand_content_task for reference: {reference_id}, user: {user_id}"
    )

    try:
        topic_ctx = TopicContext(**context)
        learning_ctx = LearningContextDTO(**learning_context)
        system_prompt, user_prompt = build_content_expansion_prompt(
            topic_ctx, learning_ctx
        )
        result = generate_structured_json(system_prompt, user_prompt)
        logger.info(f"Successfully expanded content for {reference_id} / {user_id}")

        return _validate_and_return(
            result, ContentExpansionGeneratedResponse, cache_key
        )
    except Exception as e:
        logger.error(f"Error in expand_content_task for {reference_id}: {str(e)}")
        raise self.retry(exc=e)
