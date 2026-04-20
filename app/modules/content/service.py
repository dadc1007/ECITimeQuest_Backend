from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.modules.content.models import (
    HistoricalPeriod, Topic, HistoricalEvent,
    HistoricalFigure, Challenge
)
from app.modules.content.schemas import (
    HistoricalPeriodCreate, HistoricalPeriodUpdate,
    TopicCreate, TopicUpdate,
    HistoricalEventCreate, HistoricalEventUpdate,
    HistoricalFigureCreate, HistoricalFigureUpdate,
    ChallengeCreate, ChallengeUpdate,
    TopicContextForAI
)


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _normalize_pagination(skip: int, limit: int) -> tuple[int, int]:
    safe_skip = max(0, skip)
    safe_limit = max(1, min(limit, MAX_PAGE_SIZE))
    return safe_skip, safe_limit


def _commit_and_refresh(
    db: Session,
    entity,
    *,
    conflict_detail: str | None = None,
):
    try:
        db.commit()
        db.refresh(entity)
        return entity
    except IntegrityError:
        db.rollback()
        if conflict_detail:
            raise HTTPException(status_code=409, detail=conflict_detail)
        raise


# ── HistoricalPeriod ──────────────────────────────────────

def get_all_periods(
    db: Session,
    only_published: bool = True,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[HistoricalPeriod]:
    safe_skip, safe_limit = _normalize_pagination(skip, limit)
    query = db.query(HistoricalPeriod).filter(HistoricalPeriod.is_active.is_(True))
    if only_published:
        query = query.filter(HistoricalPeriod.is_published.is_(True))
    return query.order_by(HistoricalPeriod.order).offset(safe_skip).limit(safe_limit).all()


def get_period_by_id(db: Session, period_id: UUID, include_unpublished: bool = False) -> HistoricalPeriod:
    query = db.query(HistoricalPeriod).filter(HistoricalPeriod.id == period_id)
    if not include_unpublished:
        query = query.filter(
            HistoricalPeriod.is_active.is_(True),
            HistoricalPeriod.is_published.is_(True),
        )
    period = query.first()
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
    return period


def create_period(db: Session, data: HistoricalPeriodCreate, updated_by: str) -> HistoricalPeriod:
    period = HistoricalPeriod(**data.model_dump(), updated_by=updated_by)
    db.add(period)
    return _commit_and_refresh(
        db,
        period,
        conflict_detail="A period with this name already exists",
    )


def update_period(db: Session, period_id: UUID, data: HistoricalPeriodUpdate, updated_by: str) -> HistoricalPeriod:
    period = get_period_by_id(db, period_id, include_unpublished=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(period, field, value)
    period.updated_by = updated_by
    period.version += 1
    return _commit_and_refresh(
        db,
        period,
        conflict_detail="A period with this name already exists",
    )


# ── Topic ─────────────────────────────────────────────────

def get_topics_by_period(
    db: Session,
    period_id: UUID,
    only_published: bool = True,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[Topic]:
    safe_skip, safe_limit = _normalize_pagination(skip, limit)
    query = db.query(Topic).filter(
        Topic.period_id == period_id,
        Topic.is_active.is_(True),
    )
    if only_published:
        query = query.filter(Topic.is_published.is_(True))
    return query.order_by(Topic.order).offset(safe_skip).limit(safe_limit).all()


def get_topic_by_id(db: Session, topic_id: UUID, include_unpublished: bool = False) -> Topic:
    query = db.query(Topic).filter(Topic.id == topic_id)
    if not include_unpublished:
        query = query.filter(
            Topic.is_active.is_(True),
            Topic.is_published.is_(True),
        )
    topic = query.first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def create_topic(db: Session, data: TopicCreate, updated_by: str) -> Topic:
    get_period_by_id(db, data.period_id, include_unpublished=True)
    topic = Topic(**data.model_dump(), updated_by=updated_by)
    db.add(topic)
    return _commit_and_refresh(
        db,
        topic,
        conflict_detail="A topic with this name already exists in this period",
    )


def update_topic(db: Session, topic_id: UUID, data: TopicUpdate, updated_by: str) -> Topic:
    topic = get_topic_by_id(db, topic_id, include_unpublished=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(topic, field, value)
    topic.updated_by = updated_by
    topic.version += 1
    return _commit_and_refresh(
        db,
        topic,
        conflict_detail="A topic with this name already exists in this period",
    )


# ── HistoricalEvent ───────────────────────────────────────

def get_all_events(
    db: Session,
    only_published: bool = True,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[HistoricalEvent]:
    safe_skip, safe_limit = _normalize_pagination(skip, limit)
    query = db.query(HistoricalEvent)
    if only_published:
        query = query.filter(HistoricalEvent.is_published.is_(True))
    return query.order_by(HistoricalEvent.year).offset(safe_skip).limit(safe_limit).all()


def get_event_by_id(db: Session, event_id: UUID, include_unpublished: bool = False) -> HistoricalEvent:
    query = db.query(HistoricalEvent).filter(HistoricalEvent.id == event_id)
    if not include_unpublished:
        query = query.filter(HistoricalEvent.is_published.is_(True))
    event = query.first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def create_event(db: Session, data: HistoricalEventCreate, updated_by: str) -> HistoricalEvent:
    event = HistoricalEvent(**data.model_dump(), updated_by=updated_by)
    db.add(event)
    return _commit_and_refresh(db, event)


def update_event(db: Session, event_id: UUID, data: HistoricalEventUpdate, updated_by: str) -> HistoricalEvent:
    event = get_event_by_id(db, event_id, include_unpublished=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(event, field, value)
    event.updated_by = updated_by
    event.version += 1
    return _commit_and_refresh(db, event)


def add_event_to_topic(db: Session, topic_id: UUID, event_id: UUID) -> Topic:
    topic = get_topic_by_id(db, topic_id, include_unpublished=True)
    event = get_event_by_id(db, event_id, include_unpublished=True)
    if event in topic.events:
        raise HTTPException(status_code=409, detail="Event already linked to this topic")
    topic.events.append(event)
    return _commit_and_refresh(db, topic)


def remove_event_from_topic(db: Session, topic_id: UUID, event_id: UUID) -> Topic:
    topic = get_topic_by_id(db, topic_id, include_unpublished=True)
    event = get_event_by_id(db, event_id, include_unpublished=True)
    if event not in topic.events:
        raise HTTPException(status_code=404, detail="Event not linked to this topic")
    topic.events.remove(event)
    return _commit_and_refresh(db, topic)


# ── HistoricalFigure ──────────────────────────────────────

def get_all_figures(
    db: Session,
    only_published: bool = True,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[HistoricalFigure]:
    safe_skip, safe_limit = _normalize_pagination(skip, limit)
    query = db.query(HistoricalFigure)
    if only_published:
        query = query.filter(HistoricalFigure.is_published.is_(True))
    return query.order_by(HistoricalFigure.name).offset(safe_skip).limit(safe_limit).all()


def get_figure_by_id(db: Session, figure_id: UUID, include_unpublished: bool = False) -> HistoricalFigure:
    query = db.query(HistoricalFigure).filter(HistoricalFigure.id == figure_id)
    if not include_unpublished:
        query = query.filter(HistoricalFigure.is_published.is_(True))
    figure = query.first()
    if not figure:
        raise HTTPException(status_code=404, detail="Figure not found")
    return figure


def create_figure(db: Session, data: HistoricalFigureCreate, updated_by: str) -> HistoricalFigure:
    figure = HistoricalFigure(**data.model_dump(), updated_by=updated_by)
    db.add(figure)
    return _commit_and_refresh(
        db,
        figure,
        conflict_detail="A figure with this name already exists",
    )


def update_figure(db: Session, figure_id: UUID, data: HistoricalFigureUpdate, updated_by: str) -> HistoricalFigure:
    figure = get_figure_by_id(db, figure_id, include_unpublished=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(figure, field, value)
    figure.updated_by = updated_by
    figure.version += 1
    return _commit_and_refresh(
        db,
        figure,
        conflict_detail="A figure with this name already exists",
    )


def add_figure_to_topic(db: Session, topic_id: UUID, figure_id: UUID) -> Topic:
    topic = get_topic_by_id(db, topic_id, include_unpublished=True)
    figure = get_figure_by_id(db, figure_id, include_unpublished=True)
    if figure in topic.figures:
        raise HTTPException(status_code=409, detail="Figure already linked to this topic")
    topic.figures.append(figure)
    return _commit_and_refresh(db, topic)


def remove_figure_from_topic(db: Session, topic_id: UUID, figure_id: UUID) -> Topic:
    topic = get_topic_by_id(db, topic_id, include_unpublished=True)
    figure = get_figure_by_id(db, figure_id, include_unpublished=True)
    if figure not in topic.figures:
        raise HTTPException(status_code=404, detail="Figure not linked to this topic")
    topic.figures.remove(figure)
    return _commit_and_refresh(db, topic)


# ── Challenge ─────────────────────────────────────────────

def get_challenges_by_topic(
    db: Session,
    topic_id: UUID,
    only_published: bool = True,
    skip: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> list[Challenge]:
    safe_skip, safe_limit = _normalize_pagination(skip, limit)
    get_topic_by_id(db, topic_id, include_unpublished=not only_published)
    query = db.query(Challenge).filter(
        Challenge.topic_id == topic_id,
        Challenge.is_active.is_(True),
    )
    if only_published:
        query = query.filter(Challenge.is_published.is_(True))
    return query.order_by(Challenge.created_at.desc()).offset(safe_skip).limit(safe_limit).all()


def get_challenge_by_id(db: Session, challenge_id: UUID, include_unpublished: bool = False) -> Challenge:
    query = db.query(Challenge).filter(Challenge.id == challenge_id)
    if not include_unpublished:
        query = query.filter(
            Challenge.is_active.is_(True),
            Challenge.is_published.is_(True),
        )
    challenge = query.first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def create_challenge(db: Session, data: ChallengeCreate, updated_by: str) -> Challenge:
    get_topic_by_id(db, data.topic_id, include_unpublished=True)
    challenge = Challenge(**data.model_dump(), updated_by=updated_by)
    db.add(challenge)
    return _commit_and_refresh(
        db,
        challenge,
        conflict_detail="A challenge with this title already exists for this topic",
    )


def update_challenge(db: Session, challenge_id: UUID, data: ChallengeUpdate, updated_by: str) -> Challenge:
    challenge = get_challenge_by_id(db, challenge_id, include_unpublished=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(challenge, field, value)
    challenge.updated_by = updated_by
    challenge.version += 1
    return _commit_and_refresh(
        db,
        challenge,
        conflict_detail="A challenge with this title already exists for this topic",
    )


# ── Context para IA ───────────────────────────────────────

def get_topic_context_for_ai(db: Session, topic_id: UUID) -> TopicContextForAI:
    topic = get_topic_by_id(db, topic_id)

    if topic.period is None or not topic.period.is_published or not topic.period.is_active:
        raise HTTPException(status_code=404, detail="Topic not available")

    published_events = [event for event in topic.events if event.is_published]
    published_events.sort(key=lambda item: (item.year is None, item.year, item.name.lower()))

    published_figures = [figure for figure in topic.figures if figure.is_published]
    published_figures.sort(key=lambda item: item.name.lower())

    return TopicContextForAI(
        topic_id=topic.id,
        topic_name=topic.name,
        topic_description=topic.description,
        difficulty=topic.difficulty,
        difficulty_hint=topic.difficulty_hint,
        period_name=topic.period.name,
        events=published_events,
        figures=published_figures,
    )