from typing import Literal, Dict, Any, Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class HistoricalEvent(BaseModel):
    name: str
    description: str
    year: Optional[int] = None
    era_start_year: Optional[int] = None
    era_end_year: Optional[int] = None
    location: Optional[str] = None


class HistoricalFigure(BaseModel):
    name: str
    role: Optional[str] = None
    biography: str
    birth_year: Optional[int] = None
    death_year: Optional[int] = None


class TopicContext(BaseModel):
    topic_name: str
    topic_description: str
    period_name: str
    events: list[HistoricalEvent]
    figures: list[HistoricalFigure]


class LearningContextDTO(BaseModel):
    user_level: int
    concept_gaps: list[str]


class PersonalizedQuizContext(BaseModel):
    topic_name: str = "Unknown Topic"
    summary: str
    key_facts: List[str]
    fun_fact: str


class QuizQuestion(BaseModel):
    text: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3)
    concept: str


class QuizGeneratedResponse(BaseModel):
    questions: List[QuizQuestion]


class ConceptGap(BaseModel):
    concept: str
    explanation: str
    severity: Literal["low", "medium", "high"]


class GapAnalysisGeneratedResponse(BaseModel):
    concept_gaps: List[ConceptGap]


class ExpandedContent(BaseModel):
    summary: str
    key_facts: List[str]
    fun_fact: str


class ContentExpansionGeneratedResponse(BaseModel):
    content: ExpandedContent


class AITaskRequest(BaseModel):
    task_type: Literal["quiz_generation", "gap_analysis", "content_expansion"]
    reference_id: str = Field(
        ..., description="The ID of the topic this task belongs to"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="The ID of the user requesting the task for personalization (extracted from token)",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Context variables needed for the prompt"
    )
    learning_context: Optional[LearningContextDTO] = None


class AITaskResponse(BaseModel):
    status: Literal["processing", "completed", "failed"]
    task_id: Optional[str] = None
    source: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
