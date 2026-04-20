from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field
from pydantic import model_validator


# ── HistoricalPeriod ──────────────────────────────────────

class HistoricalPeriodResponse(BaseModel):
    id: UUID
    name: str
    description: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    order: int
    is_active: bool
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoricalPeriodCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    order: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def validate_year_range(self):
        if self.start_year is not None and self.end_year is not None and self.start_year > self.end_year:
            raise ValueError("start_year must be less than or equal to end_year")
        return self


class HistoricalPeriodUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None

    @model_validator(mode="after")
    def validate_year_range(self):
        if self.start_year is not None and self.end_year is not None and self.start_year > self.end_year:
            raise ValueError("start_year must be less than or equal to end_year")
        return self


# ── Topic ─────────────────────────────────────────────────

class TopicSummary(BaseModel):
    id: UUID
    name: str
    difficulty: int
    is_premium: bool
    xp_reward: int
    order: int

    model_config = {"from_attributes": True}


class TopicResponse(BaseModel):
    id: UUID
    period_id: UUID
    name: str
    description: str
    difficulty: int
    difficulty_hint: Optional[str] = None
    order: int
    is_premium: bool
    is_active: bool
    is_published: bool
    xp_reward: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicCreate(BaseModel):
    period_id: UUID
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    difficulty: int = Field(ge=1, le=10, default=1)
    difficulty_hint: Optional[str] = None
    order: int = Field(ge=0, default=0)
    is_premium: bool = False
    xp_reward: int = Field(ge=0, default=50)


class TopicUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    difficulty: Optional[int] = Field(default=None, ge=1, le=10)
    difficulty_hint: Optional[str] = None
    order: Optional[int] = Field(default=None, ge=0)
    is_premium: Optional[bool] = None
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None
    xp_reward: Optional[int] = Field(default=None, ge=0)


# ── HistoricalEvent ───────────────────────────────────────

class HistoricalEventResponse(BaseModel):
    id: UUID
    name: str
    description: str
    year: Optional[int] = None
    era_start_year: Optional[int] = None
    era_end_year: Optional[int] = None
    location: Optional[str] = None
    difficulty_hint: Optional[str] = None
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoricalEventCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    year: Optional[int] = None
    era_start_year: Optional[int] = None
    era_end_year: Optional[int] = None
    location: Optional[str] = None
    difficulty_hint: Optional[str] = None

    @model_validator(mode="after")
    def validate_era_year_range(self):
        if self.era_start_year is not None and self.era_end_year is not None and self.era_start_year > self.era_end_year:
            raise ValueError("era_start_year must be less than or equal to era_end_year")
        return self


class HistoricalEventUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    year: Optional[int] = None
    era_start_year: Optional[int] = None
    era_end_year: Optional[int] = None
    location: Optional[str] = None
    difficulty_hint: Optional[str] = None
    is_published: Optional[bool] = None

    @model_validator(mode="after")
    def validate_era_year_range(self):
        if self.era_start_year is not None and self.era_end_year is not None and self.era_start_year > self.era_end_year:
            raise ValueError("era_start_year must be less than or equal to era_end_year")
        return self


# ── HistoricalFigure ──────────────────────────────────────

class HistoricalFigureResponse(BaseModel):
    id: UUID
    name: str
    role: Optional[str] = None
    biography: str
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    difficulty_hint: Optional[str] = None
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoricalFigureCreate(BaseModel):
    name: str = Field(min_length=1)
    biography: str = Field(min_length=1)
    role: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    difficulty_hint: Optional[str] = None

    @model_validator(mode="after")
    def validate_lifespan_year_range(self):
        if self.birth_year is not None and self.death_year is not None and self.birth_year > self.death_year:
            raise ValueError("birth_year must be less than or equal to death_year")
        return self


class HistoricalFigureUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    biography: Optional[str] = Field(default=None, min_length=1)
    role: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    difficulty_hint: Optional[str] = None
    is_published: Optional[bool] = None

    @model_validator(mode="after")
    def validate_lifespan_year_range(self):
        if self.birth_year is not None and self.death_year is not None and self.birth_year > self.death_year:
            raise ValueError("birth_year must be less than or equal to death_year")
        return self


# ── Challenge ─────────────────────────────────────────────

class ChallengeResponse(BaseModel):
    id: UUID
    topic_id: UUID
    title: str
    description: str
    xp_reward: int
    coin_reward: int
    required_score: int
    is_premium: bool
    is_active: bool
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChallengeCreate(BaseModel):
    topic_id: UUID
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    xp_reward: int = Field(ge=0, default=100)
    coin_reward: int = Field(ge=0, default=50)
    required_score: int = Field(ge=0, le=100, default=80)
    is_premium: bool = False


class ChallengeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    xp_reward: Optional[int] = Field(default=None, ge=0)
    coin_reward: Optional[int] = Field(default=None, ge=0)
    required_score: Optional[int] = Field(default=None, ge=0, le=100)
    is_premium: Optional[bool] = None
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None


# ── Context para IA ───────────────────────────────────────

class TopicContextForAI(BaseModel):
    topic_id: UUID
    topic_name: str
    topic_description: str
    difficulty: int
    difficulty_hint: Optional[str] = None
    period_name: str
    events: list[HistoricalEventResponse]
    figures: list[HistoricalFigureResponse]

    model_config = {"from_attributes": True}