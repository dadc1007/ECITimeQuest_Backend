from datetime import datetime, date, timezone

import uuid
from sqlalchemy import Column, Integer, Float, Boolean, String, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from app.database import Base
from app.enums.enums import ErrorType, CoinReason


class UserProgress(Base):
    __tablename__ = "user_progress"
    __table_args__ = (
        CheckConstraint("xp_total >= 0", name="ck_user_progress_xp_total_non_negative"),
        CheckConstraint("level >= 1", name="ck_user_progress_level_min_one"),
        CheckConstraint("coins >= 0", name="ck_user_progress_coins_non_negative"),
        CheckConstraint("lives >= 0", name="ck_user_progress_lives_non_negative"),
        CheckConstraint("streak_day >= 0", name="ck_user_progress_streak_day_non_negative"),
        CheckConstraint("longest_streak >= 0", name="ck_user_progress_longest_streak_non_negative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    xp_total = Column(Integer, nullable=False, default=0)
    level = Column(Integer, nullable=False, default=1)
    coins = Column(Integer, nullable=False, default=0)
    lives = Column(Integer, nullable=False, default=5)

    lives_refill_at = Column(DateTime(timezone=True), nullable=True)
    streak_day = Column(Integer, nullable=False, default=0)
    longest_streak = Column(Integer, nullable=False, default=0)
    last_activity_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="progress", uselist=False)


class TopicProgress(Base):
    __tablename__ = "topic_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_topic_progress_user_topic"),
        CheckConstraint("completion_percentage >= 0.0", name="ck_topic_progress_completion_min"),
        CheckConstraint("completion_percentage <= 100.0", name="ck_topic_progress_completion_max"),
        CheckConstraint("xp_earned >= 0", name="ck_topic_progress_xp_earned_non_negative"),
        Index("ix_topic_progress_topic_id", "topic_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(UUID(as_uuid=True), nullable=False)

    completion_percentage = Column(Float, default=0.0, nullable=False)
    xp_earned = Column(Integer, default=0, nullable=False)
    last_studied_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", backref="topic_progress")



class LearningSession(Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        Index("ix_learning_sessions_topic_id", "topic_id"),
        CheckConstraint("xp_gained >= 0", name="ck_learning_sessions_xp_gained_non_negative"),
        CheckConstraint("coins_gained >= 0", name="ck_learning_sessions_coins_gained_non_negative"),
        CheckConstraint("lives_lost >= 0", name="ck_learning_sessions_lives_lost_non_negative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    topic_id = Column(UUID(as_uuid=True), nullable=False)
    xp_gained = Column(Integer, default=0, nullable=False)
    coins_gained = Column(Integer, default=0, nullable=False)
    lives_lost = Column(Integer, default=0, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)




class ConceptGap(Base):
    __tablename__ = "concept_gaps"
    __table_args__ = (
        Index("ix_concept_gaps_topic_id", "topic_id"),
        CheckConstraint("weakness_score >= 0.0", name="ck_concept_gaps_weakness_min"),
        CheckConstraint("weakness_score <= 1.0", name="ck_concept_gaps_weakness_max"),
        CheckConstraint("avg_response_time_ms >= 0", name="ck_concept_gaps_avg_response_time_non_negative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(UUID(as_uuid=True), nullable=False)
    concept = Column(String, nullable=False)
    error_type = Column(SAEnum(ErrorType), nullable=False)
    weakness_score = Column(Float, default=0.5, nullable=False)
    avg_response_time_ms = Column(Integer, nullable=True)
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="concept_gaps")


class CoinTransaction(Base):
    __tablename__ = "coin_transactions"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_coin_transactions_amount_non_zero"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Integer, nullable=False)
    reason = Column(SAEnum(CoinReason), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_name", name="uq_user_badges_user_badge"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    badge_name = Column(String, nullable=False)
    awarded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="badges")


class LearningSyncEvent(Base):
    __tablename__ = "learning_sync_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_session_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    topic_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    learning_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", backref="sync_events")