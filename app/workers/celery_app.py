from celery import Celery
from app.config import settings

celery_app = Celery(
    "ai_orchestrator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.modules.ai_orchestrator.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=120,  # Hard limit to avoid hung workers
    task_soft_time_limit=90,  # Soft limit (allows exception catching)
)
