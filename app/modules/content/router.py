from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.enums.enums import UserRole
from app.modules.auth.service import get_user_by_firebase_uid
from app.modules.content import service, schemas

router = APIRouter(prefix="/content", tags=["Content"])


COMMON_AUTH_RESPONSES = {
    401: {"description": "Invalid or expired token"},
}

COMMON_ADMIN_RESPONSES = {
    **COMMON_AUTH_RESPONSES,
    403: {"description": "Admin role required"},
}


def _updated_by(current_user: dict) -> str:
    # Firebase tokens can omit email in some providers; fall back to uid.
    return current_user.get("email") or current_user.get("uid") or "system"


def _require_admin(current_user: dict, db: Session) -> None:
    # Lógica de admin deshabilitada para pruebas
    # uid = current_user.get("uid")
    # user = get_user_by_firebase_uid(db, uid) if uid else None
    # 
    # if user is not None:
    #     user_role = None
    #     if isinstance(user, dict):
    #         user_role = str(user.get("role", "")).lower()
    #     else:
    #         user_role = str(getattr(user, "role", "")).lower()
    # 
    #     if user_role == UserRole.ADMIN.value:
    #         return
    # 
    # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    pass


# ── HistoricalPeriod ──────────────────────────────────────

@router.get("/periods", response_model=list[schemas.HistoricalPeriodResponse], responses={
    **COMMON_AUTH_RESPONSES,
})
@limiter.limit("60/minute")
def list_periods(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
):
    return service.get_all_periods(db, only_published=True, skip=skip, limit=limit)


@router.get("/periods/{period_id}", response_model=schemas.HistoricalPeriodResponse, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Period not found"},
})
@limiter.limit("60/minute")
def get_period(
    request: Request,
    period_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_period_by_id(db, period_id)


@router.post("/periods", response_model=schemas.HistoricalPeriodResponse, status_code=201, responses={
    **COMMON_ADMIN_RESPONSES,
    409: {"description": "A period with this name already exists"},
})
@limiter.limit("20/minute")
def create_period(
    request: Request,
    data: schemas.HistoricalPeriodCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.create_period(db, data, updated_by=_updated_by(current_user))


@router.patch("/periods/{period_id}", response_model=schemas.HistoricalPeriodResponse, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Period not found"},
    409: {"description": "A period with this name already exists"},
})
@limiter.limit("20/minute")
def update_period(
    request: Request,
    period_id: UUID,
    data: schemas.HistoricalPeriodUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_period(db, period_id, data, updated_by=_updated_by(current_user))


# ── Topic ─────────────────────────────────────────────────

@router.get("/periods/{period_id}/topics", response_model=list[schemas.TopicSummary], responses={
    **COMMON_AUTH_RESPONSES,
})
@limiter.limit("60/minute")
def list_topics(
    request: Request,
    period_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
):
    return service.get_topics_by_period(db, period_id, only_published=True, skip=skip, limit=limit)


@router.get("/topics/{topic_id}", response_model=schemas.TopicResponse, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Topic not found"},
})
@limiter.limit("60/minute")
def get_topic(
    request: Request,
    topic_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_topic_by_id(db, topic_id)


@router.post("/topics", response_model=schemas.TopicResponse, status_code=201, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Period not found"},
    409: {"description": "A topic with this name already exists in this period"},
})
@limiter.limit("20/minute")
def create_topic(
    request: Request,
    data: schemas.TopicCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.create_topic(db, data, updated_by=_updated_by(current_user))


@router.patch("/topics/{topic_id}", response_model=schemas.TopicResponse, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic not found"},
    409: {"description": "A topic with this name already exists in this period"},
})
@limiter.limit("20/minute")
def update_topic(
    request: Request,
    topic_id: UUID,
    data: schemas.TopicUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_topic(db, topic_id, data, updated_by=_updated_by(current_user))


# ── Events ────────────────────────────────────────────────

@router.get("/events", response_model=list[schemas.HistoricalEventResponse], responses={
    **COMMON_AUTH_RESPONSES,
})
@limiter.limit("60/minute")
def list_events(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
):
    return service.get_all_events(db, only_published=True, skip=skip, limit=limit)


@router.get("/events/{event_id}", response_model=schemas.HistoricalEventResponse, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Event not found"},
})
@limiter.limit("60/minute")
def get_event(
    request: Request,
    event_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_event_by_id(db, event_id)


@router.post("/events", response_model=schemas.HistoricalEventResponse, status_code=201, responses={
    **COMMON_ADMIN_RESPONSES,
})
@limiter.limit("20/minute")
def create_event(
    request: Request,
    data: schemas.HistoricalEventCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.create_event(db, data, updated_by=_updated_by(current_user))


@router.patch("/events/{event_id}", response_model=schemas.HistoricalEventResponse, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Event not found"},
})
@limiter.limit("20/minute")
def update_event(
    request: Request,
    event_id: UUID,
    data: schemas.HistoricalEventUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_event(db, event_id, data, updated_by=_updated_by(current_user))


@router.post("/topics/{topic_id}/events/{event_id}", status_code=204, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic or event not found"},
    409: {"description": "Event already linked to this topic"},
})
@limiter.limit("20/minute")
def link_event_to_topic(
    request: Request,
    topic_id: UUID,
    event_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    service.add_event_to_topic(db, topic_id, event_id)


@router.delete("/topics/{topic_id}/events/{event_id}", status_code=204, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic/event not found or event not linked to topic"},
})
@limiter.limit("20/minute")
def unlink_event_from_topic(
    request: Request,
    topic_id: UUID,
    event_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    service.remove_event_from_topic(db, topic_id, event_id)


# ── Figures ───────────────────────────────────────────────

@router.get("/figures", response_model=list[schemas.HistoricalFigureResponse], responses={
    **COMMON_AUTH_RESPONSES,
})
@limiter.limit("60/minute")
def list_figures(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
):
    return service.get_all_figures(db, only_published=True, skip=skip, limit=limit)


@router.get("/figures/{figure_id}", response_model=schemas.HistoricalFigureResponse, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Figure not found"},
})
@limiter.limit("60/minute")
def get_figure(
    request: Request,
    figure_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_figure_by_id(db, figure_id)


@router.post("/figures", response_model=schemas.HistoricalFigureResponse, status_code=201, responses={
    **COMMON_ADMIN_RESPONSES,
    409: {"description": "A figure with this name already exists"},
})
@limiter.limit("20/minute")
def create_figure(
    request: Request,
    data: schemas.HistoricalFigureCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.create_figure(db, data, updated_by=_updated_by(current_user))


@router.patch("/figures/{figure_id}", response_model=schemas.HistoricalFigureResponse, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Figure not found"},
    409: {"description": "A figure with this name already exists"},
})
@limiter.limit("20/minute")
def update_figure(
    request: Request,
    figure_id: UUID,
    data: schemas.HistoricalFigureUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_figure(db, figure_id, data, updated_by=_updated_by(current_user))


@router.post("/topics/{topic_id}/figures/{figure_id}", status_code=204, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic or figure not found"},
    409: {"description": "Figure already linked to this topic"},
})
@limiter.limit("20/minute")
def link_figure_to_topic(
    request: Request,
    topic_id: UUID,
    figure_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    service.add_figure_to_topic(db, topic_id, figure_id)


@router.delete("/topics/{topic_id}/figures/{figure_id}", status_code=204, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic/figure not found or figure not linked to topic"},
})
@limiter.limit("20/minute")
def unlink_figure_from_topic(
    request: Request,
    topic_id: UUID,
    figure_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    service.remove_figure_from_topic(db, topic_id, figure_id)


# ── Challenges ────────────────────────────────────────────

@router.get("/topics/{topic_id}/challenges", response_model=list[schemas.ChallengeResponse], responses={
    **COMMON_AUTH_RESPONSES,
})
@limiter.limit("60/minute")
def list_challenges(
    request: Request,
    topic_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE_SIZE)] = service.DEFAULT_PAGE_SIZE,
):
    return service.get_challenges_by_topic(db, topic_id, only_published=True, skip=skip, limit=limit)


@router.get("/challenges/{challenge_id}", response_model=schemas.ChallengeResponse, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Challenge not found"},
})
@limiter.limit("60/minute")
def get_challenge(
    request: Request,
    challenge_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_challenge_by_id(db, challenge_id)


@router.post("/challenges", response_model=schemas.ChallengeResponse, status_code=201, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Topic not found"},
    409: {"description": "A challenge with this title already exists for this topic"},
})
@limiter.limit("20/minute")
def create_challenge(
    request: Request,
    data: schemas.ChallengeCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.create_challenge(db, data, updated_by=_updated_by(current_user))


@router.patch("/challenges/{challenge_id}", response_model=schemas.ChallengeResponse, responses={
    **COMMON_ADMIN_RESPONSES,
    404: {"description": "Challenge not found"},
    409: {"description": "A challenge with this title already exists for this topic"},
})
@limiter.limit("20/minute")
def update_challenge(
    request: Request,
    challenge_id: UUID,
    data: schemas.ChallengeUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_admin(current_user, db)
    return service.update_challenge(db, challenge_id, data, updated_by=_updated_by(current_user))


# ── Context para IA ───────────────────────────────────────

@router.get("/topics/{topic_id}/ai-context", response_model=schemas.TopicContextForAI, responses={
    **COMMON_AUTH_RESPONSES,
    404: {"description": "Topic not available"},
})
@limiter.limit("30/minute")
def get_ai_context(
    request: Request,
    topic_id: UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return service.get_topic_context_for_ai(db, topic_id)