from datetime import datetime, date
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field
from app.enums.enums import ErrorType, CoinReason


# ── UserProgress ──────────────────────────────────────────
class UserProgressResponse(BaseModel):
    id: UUID
    user_id: UUID
    xp_total: int
    level: int
    coins: int
    lives: int
    lives_refill_at: Optional[datetime] = None
    streak_day: int
    longest_streak: int
    last_activity_date: Optional[date] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Era / Period Progress ─────────────────────────────────

class EraTopicProgressItem(BaseModel):
    topic_id: UUID
    name: str
    completion_percentage: float
    xp_earned: int


class EraProgressResponse(BaseModel):
    period_id: UUID
    period_name: str
    topics_count: int
    topics_completed: int
    xp_total: int
    avg_completion: float
    topics: list[EraTopicProgressItem] | None = None

    model_config = {"from_attributes": True}


class EraMasteryItemResponse(BaseModel):
    period_id: UUID
    period_name: str
    mastery_percentage: float
    topics_count: int
    topics_completed: int
    xp_total: int


# ── TopicProgress ─────────────────────────────────────────
class TopicProgressResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic_id: UUID
    completion_percentage: float
    xp_earned: int
    last_studied_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── LearningSession ───────────────────────────────────────
class StartSessionRequest(BaseModel):
    topic_id: UUID

class SubmitAnswerRequest(BaseModel):
    session_id: UUID
    question_id: UUID
    concept: str = Field(..., min_length=2)
    answer: str = Field(min_length=1)
    response_time_ms: int = Field(ge=0)
    is_correct: bool

class AnswerSubmitResponse(BaseModel):
    session_id: UUID
    is_correct: bool
    xp_earned: int
    coins_earned: int
    feedback: Optional[str] = None
    lives_lost: int = 0


class FinishSessionRequest(BaseModel):
    correct_answers: int = Field(ge=0)
    wrong_answers: int = Field(ge=0)
    avg_response_time_ms: Optional[int] = Field(default=None, ge=0)
    completed: bool

class LearningSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic_id: UUID
    xp_gained: int
    coins_gained: int
    lives_lost: int
    completed: bool
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OfflineSessionSyncRequest(BaseModel):
    client_session_id: UUID
    topic_id: UUID
    correct_answers: int = Field(ge=0)
    wrong_answers: int = Field(ge=0)
    avg_response_time_ms: Optional[int] = Field(default=None, ge=0)
    completed: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class LearningSyncRequest(BaseModel):
    sessions: list[OfflineSessionSyncRequest]


class LearningSyncItemResponse(BaseModel):
    client_session_id: UUID
    processed: bool
    skipped: bool = False
    session: Optional[LearningSessionResponse] = None


class LearningSyncResponse(BaseModel):
    processed: int
    skipped: int
    sessions: list[LearningSyncItemResponse]


# ── ConceptGap ────────────────────────────────────────────
class ConceptGapCreate(BaseModel):
    topic_id: UUID
    concept: str
    error_type: ErrorType
    weakness_score: float = Field(ge=0.0, le=1.0)
    avg_response_time_ms: Optional[int] = Field(default=None, ge=0)

class ConceptGapResponse(BaseModel):
    id: UUID
    user_id: UUID
    topic_id: UUID
    topic_name: Optional[str] = None
    concept: str
    error_type: ErrorType
    weakness_score: float
    avg_response_time_ms: Optional[int] = None
    detected_at: datetime

    model_config = {"from_attributes": True}


# ── CoinTransaction ───────────────────────────────────────
class CoinTransactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    amount: int
    reason: CoinReason
    created_at: datetime

    model_config = {"from_attributes": True}


class SpendCoinsRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: CoinReason


# ── UserBadge ─────────────────────────────────────────────
class UserBadgeCreate(BaseModel):
    badge_name: str = Field(min_length=1)

class UserBadgeResponse(BaseModel):
    id: UUID
    user_id: UUID
    badge_name: str
    awarded_at: datetime

    model_config = {"from_attributes": True}


# ── NextExercise ──────────────────────────────────────────
class NextExerciseResponse(BaseModel):
    exercise_id: UUID
    topic_id: UUID
    question: str
    difficulty: int = Field(ge=1, le=10)
    hint: Optional[str] = None

    