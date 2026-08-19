from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt


class SubjectResponse(BaseModel):
    id: int
    code: str
    name: str


class QuestionResponse(BaseModel):
    id: int
    subject: SubjectResponse
    paper: str
    year: int
    session: str
    variant: str
    question_number: str
    sub_label: str
    topic: str | None = None
    subtopic: str | None = None
    command_word: str | None = None
    difficulty: str | None = None
    marks: int | None = None
    raw_text: str


class AttemptCreate(BaseModel):
    user_id: PositiveInt
    question_id: PositiveInt
    submitted_answer_text: str = Field(min_length=1, max_length=20_000)


class GradingResult(BaseModel):
    attempt_id: int
    user_id: int
    question_id: int
    points_hit: list[str]
    points_missed: list[str]
    marks_earned: float = Field(ge=0)
    marks_possible: float = Field(ge=0)
    feedback: str
    mastery_updated: bool
    grading_model: str | None = None
    grading_policy_version: str
    grading_status: Literal["graded", "corrected", "disputed"]


class MasteryCell(BaseModel):
    subject: str
    topic: str
    subtopic: str
    command_word: str
    score: float = Field(ge=0, le=1)
    has_evidence: bool
    last_reviewed_at: datetime | None = None


class MasteryGridResponse(BaseModel):
    user_id: int
    subject: SubjectResponse
    cells: list[MasteryCell]


class PaperGenerateRequest(BaseModel):
    user_id: PositiveInt
    subject: str = Field(min_length=1, max_length=16)
    mode: Literal["weak_spot"] = "weak_spot"
    paper: str | None = Field(default=None, min_length=1, max_length=16)
    target_marks: PositiveInt | None = Field(default=None, le=300)
    min_real_questions_per_cell: int = Field(default=2, ge=1, le=5)


class GeneratedPaperQuestion(BaseModel):
    id: int
    position: int
    source_type: Literal["real", "ai_generated"]
    paper: str
    year: int
    session: str
    variant: str
    question_number: str
    sub_label: str
    topic: str | None = None
    subtopic: str | None = None
    command_word: str | None = None
    marks: int | None = None
    raw_text: str


class GeneratedPaperResponse(BaseModel):
    id: int
    user_id: int
    subject: SubjectResponse
    mode: Literal["weak_spot"]
    paper: str
    target_marks: int
    total_marks: int
    questions: list[GeneratedPaperQuestion]


class CurriculumChapterResponse(BaseModel):
    id: int
    subject: SubjectResponse
    grade_stage: str
    syllabus_revision: str
    map_version: str
    chapter_code: str
    name: str
    position: int
    review_status: Literal["approved"]


class GuidanceChapter(BaseModel):
    id: int
    chapter_code: str
    name: str
    grade_stage: str
    syllabus_revision: str
    map_version: str
    evidence_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    state: Literal["not_enough_evidence", "developing", "needs_practice", "strong"]


class RecommendationResponse(BaseModel):
    id: int
    chapter: GuidanceChapter
    state: Literal["developing", "needs_practice"]
    reason: str
    evidence_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    activity_type: str
    rule_version: str
    curriculum_version: str
    dismissed_at: datetime | None = None


class GuidanceResponse(BaseModel):
    user_id: int
    subject: SubjectResponse
    state: Literal["no_content", "start_diagnostic", "needs_practice", "on_track"]
    explanation: str
    chapters: list[GuidanceChapter]
    recommendation: RecommendationResponse | None = None


class RecommendationDismissRequest(BaseModel):
    user_id: PositiveInt


class DiagnosticStartRequest(BaseModel):
    user_id: PositiveInt
    subject: str = Field(min_length=1, max_length=16)
    grade_stage: str | None = Field(default=None, min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    question_limit: int = Field(default=20, ge=1, le=100)


class DiagnosticResponseSave(BaseModel):
    user_id: PositiveInt
    answer_text: str = Field(min_length=1, max_length=20_000)


class DiagnosticResponseResult(BaseModel):
    diagnostic_id: int
    question_id: int
    answer_text: str
    state: Literal["active", "submitted", "abandoned"]


class DiagnosticStartResponse(BaseModel):
    id: int
    user_id: int
    subject: SubjectResponse
    grade_stage: str | None
    state: Literal["active", "submitted", "abandoned"]
    questions: list[QuestionResponse]


class PracticeSessionCreate(BaseModel):
    user_id: PositiveInt
    subject: str = Field(min_length=1, max_length=16)
    question_ids: list[PositiveInt] = Field(min_length=1, max_length=100)
    paper_id: PositiveInt | None = None
    recommendation_id: PositiveInt | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class PracticeAnswerResponse(BaseModel):
    question_id: int
    answer_text: str
    status: Literal["draft", "submitted"]


class PracticeSessionResponse(BaseModel):
    id: int
    user_id: int
    subject: SubjectResponse
    state: Literal["draft", "active", "submitted", "abandoned", "expired"]
    question_ids: list[int]
    answers: list[PracticeAnswerResponse]
    created_at: datetime
    started_at: datetime | None = None
    submitted_at: datetime | None = None
