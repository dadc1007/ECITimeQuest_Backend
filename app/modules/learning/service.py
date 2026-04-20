from datetime import datetime, date, timezone, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.enums.enums import CoinReason, ErrorType
from app.modules.content.models import Topic
from app.modules.learning.models import (
    UserProgress, TopicProgress, LearningSession,
    ConceptGap, CoinTransaction, UserBadge, LearningSyncEvent
)
from app.modules.learning.schemas import (
    StartSessionRequest, FinishSessionRequest,
    SubmitAnswerRequest, ConceptGapCreate, AnswerSubmitResponse,
    LearningSyncRequest, LearningSyncResponse, LearningSyncItemResponse
)

MAX_LIVES = 5
LIFE_REFILL_MINUTES = 30
XP_PER_LEVEL = 100  
MAX_XP_PER_SESSION = 500
MAX_COINS_PER_SESSION = 200
XP_PER_CORRECT_ANSWER = 20
COINS_PER_CORRECT_ANSWER = 5
COMPLETION_XP_BONUS = 50
COMPLETION_COIN_BONUS = 10



def get_or_create_progress(db: Session, user_id: UUID) -> UserProgress:
    progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
    if not progress:
        try:
            progress = UserProgress(user_id=user_id)
            db.add(progress)
            db.commit()
            db.refresh(progress)
        except IntegrityError:
            db.rollback()
            progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
            if not progress:
                raise
    return progress


def _calculate_level(xp_total: int) -> int:
    return max(1, xp_total // XP_PER_LEVEL + 1)


def _update_streak(progress: UserProgress) -> None:
    today = date.today()
    if progress.last_activity_date is None:
        progress.streak_day = 1
    elif progress.last_activity_date == today:
        return  
    elif progress.last_activity_date == today - timedelta(days=1):
        progress.streak_day += 1  
    else:
        progress.streak_day = 1  

    if progress.streak_day > progress.longest_streak:
        progress.longest_streak = progress.streak_day

    progress.last_activity_date = today


def _compute_session_outcome(data: FinishSessionRequest, available_lives: int) -> tuple[int, int, int]:
    if data.correct_answers == 0 and data.wrong_answers == 0:
        raise HTTPException(status_code=400, detail="Session cannot finish without answers")

    xp_gained = (data.correct_answers * XP_PER_CORRECT_ANSWER) + (COMPLETION_XP_BONUS if data.completed else 0)
    coins_gained = (data.correct_answers * COINS_PER_CORRECT_ANSWER) + (COMPLETION_COIN_BONUS if data.completed else 0)
    lives_lost = min(available_lives, data.wrong_answers)

    return min(xp_gained, MAX_XP_PER_SESSION), min(coins_gained, MAX_COINS_PER_SESSION), lives_lost


def _classify_error_type(response_time_ms: int) -> ErrorType:
    if response_time_ms <= 3000:
        return ErrorType.CONCEPTUAL
    if response_time_ms <= 7000:
        return ErrorType.FACTUAL
    return ErrorType.CONTEXTUAL


def _get_topic_for_learning(db: Session, topic_id: UUID) -> Topic:
    topic = db.query(Topic).filter(
        Topic.id == topic_id,
        Topic.is_active.is_(True),
        Topic.is_published.is_(True),
    ).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not available")
    return topic


def _apply_session_completion(
    db: Session,
    user_id: UUID,
    session: LearningSession,
    data: FinishSessionRequest,
    finished_at: datetime | None = None,
) -> tuple[int, int, int]:
    progress = get_or_create_progress(db, user_id)
    _refill_lives_if_needed(progress)

    xp_gained, coins_gained, lives_lost = _compute_session_outcome(data, progress.lives)

    session.xp_gained = xp_gained
    session.coins_gained = coins_gained
    session.lives_lost = lives_lost
    session.completed = data.completed
    session.finished_at = finished_at or datetime.now(timezone.utc)

    progress.xp_total += xp_gained
    progress.level = _calculate_level(progress.xp_total)
    progress.coins += coins_gained
    progress.lives = max(0, progress.lives - lives_lost)
    _update_streak(progress)

    if progress.lives < MAX_LIVES and not progress.lives_refill_at:
        progress.lives_refill_at = datetime.now(timezone.utc) + timedelta(minutes=LIFE_REFILL_MINUTES)

    if coins_gained > 0:
        _register_coin_transaction(db, user_id, coins_gained, CoinReason.LESSON)

    _update_topic_progress(db, user_id, session.topic_id, xp_gained, data.completed)
    _check_and_award_badges(db, user_id, progress)

    return xp_gained, coins_gained, lives_lost


def _refill_lives_if_needed(progress: UserProgress) -> None:
    if progress.lives >= MAX_LIVES:
        progress.lives_refill_at = None
        return
    now = datetime.now(timezone.utc)
    if progress.lives_refill_at and now >= progress.lives_refill_at:
        elapsed_seconds = (now - progress.lives_refill_at).total_seconds()
        lives_to_add = int(elapsed_seconds // (LIFE_REFILL_MINUTES * 60)) + 1
        progress.lives = min(MAX_LIVES, progress.lives + lives_to_add)
        if progress.lives < MAX_LIVES:
            progress.lives_refill_at = now + timedelta(minutes=LIFE_REFILL_MINUTES)
        else:
            progress.lives_refill_at = None




def start_session(db: Session, user_id: UUID, data: StartSessionRequest) -> LearningSession:
    progress = get_or_create_progress(db, user_id)
    _refill_lives_if_needed(progress)

    if progress.lives <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_lives",
                "message": "No lives remaining",
                "lives_refill_at": progress.lives_refill_at.isoformat() if progress.lives_refill_at else None
            }
        )

    _get_topic_for_learning(db, data.topic_id)

    session = LearningSession(user_id=user_id, topic_id=data.topic_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def submit_answer(db: Session, user_id: UUID, session_id: UUID, data: SubmitAnswerRequest) -> AnswerSubmitResponse:
    session = db.query(LearningSession).filter(
        LearningSession.id == session_id,
        LearningSession.user_id == user_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if data.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id in path and body must match")
    if session.finished_at:
        raise HTTPException(status_code=400, detail="Session already finished")

    xp_earned = XP_PER_CORRECT_ANSWER if data.is_correct else 0
    coins_earned = COINS_PER_CORRECT_ANSWER if data.is_correct else 0
    lives_lost = 0 if data.is_correct else 1
    feedback = "Correct answer" if data.is_correct else "Review this concept and try again"

    if not data.is_correct:
        upsert_concept_gap(
            db,
            user_id,
            ConceptGapCreate(
                topic_id=session.topic_id,
                concept=f"question:{data.question_id}",
                error_type=_classify_error_type(data.response_time_ms),
                weakness_score=0.6,
                avg_response_time_ms=data.response_time_ms,
            ),
        )

    return AnswerSubmitResponse(
        session_id=session_id,
        is_correct=data.is_correct,
        xp_earned=xp_earned,
        coins_earned=coins_earned,
        feedback=feedback,
        lives_lost=lives_lost,
    )


def finish_session(db: Session, user_id: UUID, session_id: UUID, data: FinishSessionRequest) -> LearningSession:
    session = db.query(LearningSession).filter(
        LearningSession.id == session_id,
        LearningSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.finished_at:
        raise HTTPException(status_code=400, detail="Session already finished")

    _apply_session_completion(db, user_id, session, data)

    db.commit()
    db.refresh(session)
    return session


def sync_offline_sessions(db: Session, user_id: UUID, data: LearningSyncRequest) -> LearningSyncResponse:
    processed = 0
    skipped = 0
    items: list[LearningSyncItemResponse] = []

    for offline_session in data.sessions:
        topic_exists = db.query(Topic).filter(
            Topic.id == offline_session.topic_id,
            Topic.is_active.is_(True),
            Topic.is_published.is_(True),
        ).first()
        if not topic_exists:
            skipped += 1
            items.append(
                LearningSyncItemResponse(
                    client_session_id=offline_session.client_session_id,
                    processed=False,
                    skipped=True,
                )
            )
            continue

        existing_event = db.query(LearningSyncEvent).filter(
            LearningSyncEvent.user_id == user_id,
            LearningSyncEvent.client_session_id == offline_session.client_session_id,
        ).first()

        if existing_event:
            skipped += 1
            items.append(
                LearningSyncItemResponse(
                    client_session_id=offline_session.client_session_id,
                    processed=False,
                    skipped=True,
                )
            )
            continue

        session = LearningSession(
            user_id=user_id,
            topic_id=offline_session.topic_id,
            started_at=offline_session.started_at or datetime.now(timezone.utc),
        )
        db.add(session)
        if session.id is None:
            session.id = uuid4()

        completion_data = FinishSessionRequest(
            correct_answers=offline_session.correct_answers,
            wrong_answers=offline_session.wrong_answers,
            avg_response_time_ms=offline_session.avg_response_time_ms,
            completed=offline_session.completed,
        )
        _apply_session_completion(
            db,
            user_id,
            session,
            completion_data,
            finished_at=offline_session.finished_at or datetime.now(timezone.utc),
        )

        sync_event = LearningSyncEvent(
            user_id=user_id,
            client_session_id=offline_session.client_session_id,
            topic_id=offline_session.topic_id,
            learning_session_id=session.id,
        )
        db.add(sync_event)
        try:
            db.commit()
            db.refresh(session)
        except IntegrityError:
            db.rollback()
            conflict_event = db.query(LearningSyncEvent).filter(
                LearningSyncEvent.user_id == user_id,
                LearningSyncEvent.client_session_id == offline_session.client_session_id,
            ).first()
            if conflict_event:
                skipped += 1
                items.append(
                    LearningSyncItemResponse(
                        client_session_id=offline_session.client_session_id,
                        processed=False,
                        skipped=True,
                    )
                )
                continue
            raise

        processed += 1
        items.append(
            LearningSyncItemResponse(
                client_session_id=offline_session.client_session_id,
                processed=True,
                skipped=False,
                session=session,
            )
        )

    return LearningSyncResponse(processed=processed, skipped=skipped, sessions=items)



def _update_topic_progress(db: Session, user_id: UUID, topic_id: UUID, xp_gained: int, completed: bool) -> None:
    topic_progress = db.query(TopicProgress).filter(
        TopicProgress.user_id == user_id,
        TopicProgress.topic_id == topic_id
    ).first()

    if not topic_progress:
        topic_progress = TopicProgress(user_id=user_id, topic_id=topic_id)
        db.add(topic_progress)

    if topic_progress.xp_earned is None:
        topic_progress.xp_earned = 0
    if topic_progress.completion_percentage is None:
        topic_progress.completion_percentage = 0.0

    topic_progress.xp_earned += xp_gained
    topic_progress.last_studied_at = datetime.now(timezone.utc)
    if completed:
        topic_progress.completion_percentage = min(100.0, topic_progress.completion_percentage + 10.0)



def _register_coin_transaction(db: Session, user_id: UUID, amount: int, reason: CoinReason) -> None:
    transaction = CoinTransaction(user_id=user_id, amount=amount, reason=reason)
    db.add(transaction)


def spend_coins(db: Session, user_id: UUID, amount: int, reason: CoinReason) -> UserProgress:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    progress = get_or_create_progress(db, user_id)
    if progress.coins < amount:
        raise HTTPException(status_code=400, detail="Not enough coins")
    progress.coins -= amount
    _register_coin_transaction(db, user_id, -amount, reason)
    db.commit()
    db.refresh(progress)
    return progress



def upsert_concept_gap(db: Session, user_id: UUID, data: ConceptGapCreate) -> ConceptGap:
    gap = db.query(ConceptGap).filter(
        ConceptGap.user_id == user_id,
        ConceptGap.topic_id == data.topic_id,
        ConceptGap.concept == data.concept
    ).first()

    if not gap:
        gap = ConceptGap(user_id=user_id, **data.model_dump())
        db.add(gap)
    else:
        gap.weakness_score = data.weakness_score
        gap.error_type = data.error_type
        if data.avg_response_time_ms is not None:
            gap.avg_response_time_ms = data.avg_response_time_ms

    db.commit()
    db.refresh(gap)
    return gap



BADGE_CONDITIONS = {
    "first_lesson": lambda p: p.xp_total >= XP_PER_LEVEL,
    "streak_7": lambda p: p.streak_day >= 7,
    "streak_30": lambda p: p.streak_day >= 30,
    "level_5": lambda p: p.level >= 5,
    "level_10": lambda p: p.level >= 10,
}

def _check_and_award_badges(db: Session, user_id: UUID, progress: UserProgress) -> None:
    existing = {b.badge_name for b in db.query(UserBadge).filter(UserBadge.user_id == user_id).all()}
    for badge_name, condition in BADGE_CONDITIONS.items():
        if badge_name not in existing and condition(progress):
            db.add(UserBadge(user_id=user_id, badge_name=badge_name))