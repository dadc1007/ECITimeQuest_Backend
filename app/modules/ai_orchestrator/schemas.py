from typing import Literal, Dict, Any, Optional, List
from pydantic import BaseModel, Field


class HistoricalEvent(BaseModel):
    name: str = Field(..., description="The name of the historical event")
    description: str = Field(..., description="A brief description of the event")
    year: Optional[int] = Field(
        default=None, description="The specific year the event occurred"
    )
    era_start_year: Optional[int] = Field(
        default=None, description="The starting year of the era"
    )
    era_end_year: Optional[int] = Field(
        default=None, description="The ending year of the era"
    )
    location: Optional[str] = Field(
        default=None, description="Where the event took place"
    )


class HistoricalFigure(BaseModel):
    name: str = Field(..., description="The name of the historical figure")
    role: Optional[str] = Field(
        default=None, description="The role or title of the figure"
    )
    biography: str = Field(..., description="A short biography of the figure")
    birth_year: Optional[int] = Field(
        default=None, description="The year the figure was born"
    )
    death_year: Optional[int] = Field(
        default=None, description="The year the figure died"
    )


class TopicContext(BaseModel):
    topic_name: str = Field(..., description="The name of the topic")
    topic_description: str = Field(..., description="A description of the topic")
    period_name: str = Field(..., description="The historical period name")
    events: List[HistoricalEvent] = Field(
        ..., description="A list of key events for this topic"
    )
    figures: List[HistoricalFigure] = Field(
        ..., description="A list of key figures for this topic"
    )


class GapAnalysisContext(TopicContext):
    target_concept: str = Field(
        ...,
        description="The specific concept to analyze as a gap",
    )


class LearningContextDTO(BaseModel):
    user_level: int = Field(
        ..., description="The current proficiency level of the user (1-5)"
    )
    concept_gaps: List[str] = Field(
        ..., description="List of concepts where the user has identified gaps"
    )


class PersonalizedQuizContext(BaseModel):
    topic_name: str = Field(
        default="Unknown Topic", description="The name of the topic for the quiz"
    )
    summary: str = Field(
        ..., description="A summary of the topic to generate questions from"
    )
    key_facts: List[str] = Field(
        ..., description="Key facts that should be tested in the quiz"
    )
    fun_fact: str = Field(..., description="An interesting fact to potentially include")


class QuizQuestion(BaseModel):
    text: str = Field(..., description="The text of the question")
    options: List[str] = Field(
        ..., min_length=4, max_length=4, description="List of 4 possible answers"
    )
    correct_index: int = Field(
        ...,
        ge=0,
        le=3,
        description="The index of the correct answer in the options list",
    )
    concept: str = Field(
        ..., description="The specific historical concept being tested"
    )


class QuizGeneratedResponse(BaseModel):
    questions: List[QuizQuestion] = Field(
        ..., description="A list of generated quiz questions"
    )


class GapAnalysisResponse(BaseModel):
    concept: str = Field(
        ..., description="The historical concept the user is struggling with"
    )
    explanation: str = Field(
        ..., description="An explanation of the detected misunderstanding"
    )
    severity: Literal["bajo", "medio", "alto"] = Field(
        ..., description="The severity of the conceptual gap"
    )


class ExpandedContent(BaseModel):
    summary: str = Field(..., description="A detailed summary of the expanded topic")
    key_facts: List[str] = Field(..., description="A list of new key facts discovered")
    fun_fact: str = Field(..., description="A new interesting fact about the topic")


class ContentExpansionGeneratedResponse(BaseModel):
    content: ExpandedContent = Field(
        ..., description="The expanded educational content"
    )


class AnswerExplanationContext(BaseModel):
    topic_name: str = Field(
        ..., description="The name of the historical topic the question belongs to"
    )
    question: str = Field(
        ..., description="The quiz question that was answered incorrectly"
    )
    user_answer: str = Field(
        ..., description="The incorrect answer selected by the user"
    )
    correct_answer: str = Field(..., description="The correct answer to the question")


class AnswerExplanationGeneratedResponse(BaseModel):
    explanation: str = Field(
        ...,
        description="A clear explanation of why the selected answer is wrong and what the correct answer means",
    )
    key_concept: str = Field(
        ..., description="The core historical concept the question was testing"
    )
    tip: str = Field(
        ...,
        description="A short learning tip to help the student remember the correct answer",
    )


class AITaskRequest(BaseModel):
    task_type: Literal[
        "quiz_generation", "gap_analysis", "content_expansion", "answer_explanation"
    ] = Field(..., description="The type of AI task to be performed")
    reference_id: str = Field(
        ..., description="The ID of the topic or entity this task belongs to"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Context variables needed for the prompt"
    )


class AITaskResponse(BaseModel):
    status: Literal["processing", "completed", "failed"] = Field(
        ..., description="Current status of the task"
    )
    task_id: Optional[str] = Field(
        default=None, description="The Celery task ID for polling"
    )
    source: Optional[str] = Field(
        default=None,
        description="Whether the result came from 'cache' or was 'computed'",
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="The resulting data if the task is completed"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if the task failed"
    )


class AITaskPayload(BaseModel):
    """
    Unified contract passed to every Celery task.

    Following the Interface Segregation Principle, each task only reads
    the fields it actually needs from this object. Fields that a task
    does not need (e.g. learning_context for answer_explanation) are
    simply ignored — no dead parameters, no **kwargs hacks.
    """

    reference_id: str = Field(..., description="The target entity ID")
    user_id: str = Field(..., description="The ID of the user requesting the task")
    context: Dict[str, Any] = Field(
        ..., description="The specific input context for the task type"
    )
    cache_key: str = Field(
        default="", description="The pre-computed cache key for the result"
    )
    learning_context: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional profiling data for the user"
    )
