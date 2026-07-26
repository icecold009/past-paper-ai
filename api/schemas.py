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
