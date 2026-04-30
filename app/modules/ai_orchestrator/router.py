from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import get_current_user
from app.modules.auth.service import get_user_by_firebase_uid
from app.modules.ai_orchestrator.schemas import AITaskRequest, AITaskResponse
from app.modules.ai_orchestrator.service import orchestrator_service

router = APIRouter(prefix="/ai", tags=["AI Orchestrator"])


def _get_user(current_user: dict, db: Session):
    user = get_user_by_firebase_uid(db, current_user["uid"])
    if not user:
        raise HTTPException(
            status_code=404, detail="User not found. Call /auth/sync first."
        )
    return user


@router.post("/task", response_model=AITaskResponse, status_code=202)
def request_ai_task(
    request: AITaskRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """
    Submits a new AI task (quiz_generation, gap_analysis, content_expansion) for background processing.
    """
    try:
        user = _get_user(current_user, db)
        user_id = str(user.id)
        response = orchestrator_service.process_task_request(db, request, user_id)

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}", response_model=AITaskResponse)
def get_task_status(task_id: str):
    """
    Retrieves the status and result (if completed) of an AI task by its ID.
    """
    try:
        response = orchestrator_service.get_task_status(task_id)

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
