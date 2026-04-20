from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Boolean,
    DateTime, ForeignKey, Table, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ── Tablas pivot (many-to-many) ───────────────────────────

topic_event = Table(
    "topic_event",
    Base.metadata,
    Column("topic_id", UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    Column("event_id", UUID(as_uuid=True), ForeignKey("historical_events.id", ondelete="CASCADE"), primary_key=True),
)

topic_figure = Table(
    "topic_figure",
    Base.metadata,
    Column("topic_id", UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    Column("figure_id", UUID(as_uuid=True), ForeignKey("historical_figures.id", ondelete="CASCADE"), primary_key=True),
)


# ── HistoricalPeriod ──────────────────────────────────────

class HistoricalPeriod(Base):
    __tablename__ = "historical_periods"
    __table_args__ = (
        Index("ix_historical_periods_order", "order"),
        CheckConstraint('"order" >= 0', name="ck_historical_periods_order_non_negative"),
        CheckConstraint("version >= 1", name="ck_historical_periods_version_min_one"),
        CheckConstraint(
            "start_year IS NULL OR end_year IS NULL OR start_year <= end_year",
            name="ck_historical_periods_year_range",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=False)
    start_year = Column(Integer, nullable=True)
    end_year = Column(Integer, nullable=True)
    order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topics = relationship("Topic", back_populates="period", cascade="all, delete-orphan")


# ── Topic ─────────────────────────────────────────────────

class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index("ix_topics_period_id", "period_id"),
        Index("ix_topics_order", "order"),
        UniqueConstraint("period_id", "name", name="uq_topics_period_name"),
        CheckConstraint("difficulty >= 1 AND difficulty <= 10", name="ck_topics_difficulty_range"),
        CheckConstraint('"order" >= 0', name="ck_topics_order_non_negative"),
        CheckConstraint("xp_reward >= 0", name="ck_topics_xp_reward_non_negative"),
        CheckConstraint("version >= 1", name="ck_topics_version_min_one"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id = Column(UUID(as_uuid=True), ForeignKey("historical_periods.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(Integer, nullable=False, default=1)
    difficulty_hint = Column(Text, nullable=True)
    order = Column(Integer, nullable=False, default=0)
    is_premium = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    xp_reward = Column(Integer, default=50, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    period = relationship("HistoricalPeriod", back_populates="topics")
    events = relationship("HistoricalEvent", secondary=topic_event, back_populates="topics")
    figures = relationship("HistoricalFigure", secondary=topic_figure, back_populates="topics")
    challenges = relationship("Challenge", back_populates="topic", cascade="all, delete-orphan")


# ── HistoricalEvent ───────────────────────────────────────

class HistoricalEvent(Base):
    __tablename__ = "historical_events"
    __table_args__ = (
        Index("ix_historical_events_year", "year"),
        CheckConstraint(
            "era_start_year IS NULL OR era_end_year IS NULL OR era_start_year <= era_end_year",
            name="ck_historical_events_era_year_range",
        ),
        CheckConstraint("version >= 1", name="ck_historical_events_version_min_one"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    era_start_year = Column(Integer, nullable=True)
    era_end_year = Column(Integer, nullable=True)
    location = Column(String, nullable=True)
    difficulty_hint = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topics = relationship("Topic", secondary=topic_event, back_populates="events")


# ── HistoricalFigure ──────────────────────────────────────

class HistoricalFigure(Base):
    __tablename__ = "historical_figures"
    __table_args__ = (
        CheckConstraint(
            "birth_year IS NULL OR death_year IS NULL OR birth_year <= death_year",
            name="ck_historical_figures_lifespan_range",
        ),
        CheckConstraint("version >= 1", name="ck_historical_figures_version_min_one"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    role = Column(String, nullable=True)
    biography = Column(Text, nullable=False)
    birth_year = Column(Integer, nullable=True)
    death_year = Column(Integer, nullable=True)
    difficulty_hint = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topics = relationship("Topic", secondary=topic_figure, back_populates="figures")


# ── Challenge ─────────────────────────────────────────────

class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        Index("ix_challenges_topic_id", "topic_id"),
        UniqueConstraint("topic_id", "title", name="uq_challenges_topic_title"),
        CheckConstraint("xp_reward >= 0", name="ck_challenges_xp_reward_non_negative"),
        CheckConstraint("coin_reward >= 0", name="ck_challenges_coin_reward_non_negative"),
        CheckConstraint("required_score >= 0 AND required_score <= 100", name="ck_challenges_required_score_range"),
        CheckConstraint("version >= 1", name="ck_challenges_version_min_one"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    xp_reward = Column(Integer, default=100, nullable=False)
    coin_reward = Column(Integer, default=50, nullable=False)
    required_score = Column(Integer, default=80, nullable=False)
    is_premium = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topic = relationship("Topic", back_populates="challenges")