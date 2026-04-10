from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.modules.auth.service import get_user_by_firebase_uid
from app.modules.learning import service, schemas

router = APIRouter(prefix="/learning", tags=["Learning"])


def _get_user(current_user: dict, db: Session):
    user = get_user_by_firebase_uid(db, current_user["uid"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Call /auth/sync first.")
    return user


# ── UserProgress ──────────────────────────────────────────

@router.get("/progress", response_model=schemas.UserProgressResponse, responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("30/minute")
def get_progress(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.get_or_create_progress(db, user.id)


# ── LearningSession ───────────────────────────────────────

@router.post("/sync", response_model=schemas.LearningSyncResponse, responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("10/minute")
def sync_learning(
    request: Request,
    data: schemas.LearningSyncRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.sync_offline_sessions(db, user.id, data)

@router.post("/sessions/{session_id}/answers", response_model=schemas.AnswerSubmitResponse, responses={
    400: {"description": "Session already finished"},
    401: {"description": "Invalid or expired token"},
    404: {"description": "Session not found"},
})
@limiter.limit("30/minute")
def submit_answer(
    request: Request,
    session_id: UUID,
    data: schemas.SubmitAnswerRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.submit_answer(db, user.id, session_id, data)

@router.post("/sessions/start", response_model=schemas.LearningSessionResponse, responses={
    400: {"description": "No lives remaining"},
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("20/minute")
def start_session(
    request: Request,
    data: schemas.StartSessionRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.start_session(db, user.id, data)


@router.post("/sessions/{session_id}/finish", response_model=schemas.LearningSessionResponse, responses={
    400: {"description": "Session already finished or no answers"},
    401: {"description": "Invalid or expired token"},
    404: {"description": "Session not found"},
})
@limiter.limit("20/minute")
def finish_session(
    request: Request,
    session_id: UUID,
    data: schemas.FinishSessionRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.finish_session(db, user.id, session_id, data)


# ── TopicProgress ─────────────────────────────────────────

@router.get("/topics/{topic_id}/progress", response_model=schemas.TopicProgressResponse, responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "Topic progress not found"},
})
@limiter.limit("30/minute")
def get_topic_progress(
    request: Request,
    topic_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    from app.modules.learning.models import TopicProgress
    progress = db.query(TopicProgress).filter(
        TopicProgress.user_id == user.id,
        TopicProgress.topic_id == topic_id
    ).first()
    if not progress:
        raise HTTPException(status_code=404, detail="No progress found for this topic")
    return progress


# ── ConceptGap ────────────────────────────────────────────

@router.get("/gaps", response_model=list[schemas.ConceptGapResponse], responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("20/minute")
def get_concept_gaps(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    from app.modules.learning.models import ConceptGap
    return db.query(ConceptGap).filter(ConceptGap.user_id == user.id).all()


# ── Coins ─────────────────────────────────────────────────

@router.post("/coins/spend", response_model=schemas.UserProgressResponse, responses={
    400: {"description": "Not enough coins"},
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("10/minute")
def spend_coins(
    request: Request,
    data: schemas.SpendCoinsRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    return service.spend_coins(db, user.id, data.amount, data.reason)


# ── Badges ────────────────────────────────────────────────

@router.get("/badges", response_model=list[schemas.UserBadgeResponse], responses={
    401: {"description": "Invalid or expired token"},
    404: {"description": "User not found"},
})
@limiter.limit("20/minute")
def get_badges(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(current_user, db)
    from app.modules.learning.models import UserBadge
    return db.query(UserBadge).filter(UserBadge.user_id == user.id).all()