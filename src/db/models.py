from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


JSONB_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    questions: Mapped[list[Question]] = relationship(back_populates="subject")
    papers: Mapped[list[Paper]] = relationship(back_populates="subject")
    chapters: Mapped[list[CurriculumChapter]] = relationship(back_populates="subject")
    diagnostics: Mapped[list[Diagnostic]] = relationship(back_populates="subject")
    practice_sessions: Mapped[list[PracticeSession]] = relationship(back_populates="subject")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "paper",
            "year",
            "session",
            "variant",
            "question_number",
            "sub_label",
            name="uq_question_natural_key",
        ),
        CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
            name="ck_question_difficulty",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    paper: Mapped[str] = mapped_column(String(16), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    session: Mapped[str] = mapped_column(String(32), nullable=False)
    variant: Mapped[str] = mapped_column(String(8), nullable=False)
    question_number: Mapped[str] = mapped_column(String(16), nullable=False)
    # Empty string represents the top-level question; labels contain values such as (a) or (a)(i).
    sub_label: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    topic: Mapped[str | None] = mapped_column(String(255))
    subtopic: Mapped[str | None] = mapped_column(String(255))
    command_word: Mapped[str | None] = mapped_column(String(64))
    difficulty: Mapped[str | None] = mapped_column(String(16))
    marks: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    subject: Mapped[Subject] = relationship(back_populates="questions")
    mark_scheme_points: Mapped[list[MarkSchemePoint]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    attempts: Mapped[list[Attempt]] = relationship(back_populates="question")
    paper_links: Mapped[list[PaperQuestion]] = relationship(back_populates="question")
    chapter_mappings: Mapped[list[QuestionChapterMapping]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    diagnostic_responses: Mapped[list[DiagnosticResponse]] = relationship(back_populates="question")
    practice_answers: Mapped[list[PracticeAnswer]] = relationship(back_populates="question")


class MarkSchemePoint(Base):
    __tablename__ = "mark_scheme_points"
    __table_args__ = (
        UniqueConstraint("question_id", "point_text", "marks_value", name="uq_mark_scheme_point"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    point_text: Mapped[str] = mapped_column(Text, nullable=False)
    marks_value: Mapped[int | None] = mapped_column(Integer)

    question: Mapped[Question] = relationship(back_populates="mark_scheme_points")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="student", server_default="student")
    school_id: Mapped[str | None] = mapped_column(String(64))
    grade_stage: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    attempts: Mapped[list[Attempt]] = relationship(back_populates="user")
    mastery_records: Mapped[list[Mastery]] = relationship(back_populates="user")
    papers: Mapped[list[Paper]] = relationship(back_populates="user")
    diagnostic_evidence: Mapped[list[DiagnosticEvidence]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    diagnostics: Mapped[list[Diagnostic]] = relationship(back_populates="user", cascade="all, delete-orphan")
    practice_sessions: Mapped[list[PracticeSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class CurriculumChapter(Base):
    """A reviewed, versioned chapter in the school's approved curriculum map."""

    __tablename__ = "curriculum_chapters"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "grade_stage",
            "syllabus_revision",
            "chapter_code",
            name="uq_curriculum_chapter_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    grade_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    syllabus_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    map_version: Mapped[str] = mapped_column(String(64), nullable=False, default="unversioned", server_default="unversioned")
    chapter_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(320))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject: Mapped[Subject] = relationship(back_populates="chapters")
    question_mappings: Mapped[list[QuestionChapterMapping]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )
    diagnostic_evidence: Mapped[list[DiagnosticEvidence]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )


class QuestionChapterMapping(Base):
    """A question-to-chapter link whose review state is explicit."""

    __tablename__ = "question_chapter_mappings"
    __table_args__ = (
        UniqueConstraint("question_id", "chapter_id", name="uq_question_chapter_mapping"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    question: Mapped[Question] = relationship(back_populates="chapter_mappings")
    chapter: Mapped[CurriculumChapter] = relationship(back_populates="question_mappings")


class DiagnosticEvidence(Base):
    """Stored evidence used to calculate a chapter state."""

    __tablename__ = "diagnostic_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_enough_evidence")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="diagnostic_evidence")
    chapter: Mapped[CurriculumChapter] = relationship(back_populates="diagnostic_evidence")


class Recommendation(Base):
    """An explainable next action generated from stored evidence."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("curriculum_chapters.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float | None] = mapped_column(Float)
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    curriculum_version: Mapped[str] = mapped_column(String(64), nullable=False, default="unversioned", server_default="unversioned")
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="recommendations")
    chapter: Mapped[CurriculumChapter] = relationship(back_populates="recommendations")


class Diagnostic(Base):
    """A persisted baseline run whose answers can later be graded or reviewed."""

    __tablename__ = "diagnostics"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'submitted', 'abandoned')",
            name="ck_diagnostic_state",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_diagnostic_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    grade_stage: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="diagnostics")
    subject: Mapped[Subject] = relationship(back_populates="diagnostics")
    responses: Mapped[list[DiagnosticResponse]] = relationship(
        back_populates="diagnostic", cascade="all, delete-orphan"
    )


class DiagnosticResponse(Base):
    """One answer slot in a diagnostic; scoring is intentionally nullable until reviewed."""

    __tablename__ = "diagnostic_responses"
    __table_args__ = (
        UniqueConstraint("diagnostic_id", "question_id", name="uq_diagnostic_response_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    diagnostic_id: Mapped[int] = mapped_column(ForeignKey("diagnostics.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)
    marks_earned: Mapped[float | None] = mapped_column(Float)
    marks_possible: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    diagnostic: Mapped[Diagnostic] = relationship(back_populates="responses")
    question: Mapped[Question] = relationship(back_populates="diagnostic_responses")


class PracticeSession(Base):
    """A retry-safe practice run containing a stable set of questions."""

    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'active', 'submitted', 'abandoned', 'expired')",
            name="ck_practice_session_state",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_session_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="practice_sessions")
    subject: Mapped[Subject] = relationship(back_populates="practice_sessions")
    paper: Mapped[Paper | None] = relationship(back_populates="practice_sessions")
    recommendation: Mapped[Recommendation | None] = relationship()
    answers: Mapped[list[PracticeAnswer]] = relationship(back_populates="session", cascade="all, delete-orphan")


class PracticeAnswer(Base):
    """A saved answer slot, separate from the immutable scored Attempt record."""

    __tablename__ = "practice_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_practice_answer_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped[PracticeSession] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="practice_answers")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    submitted_answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    points_awarded: Mapped[Any] = mapped_column(JSONB_TYPE, nullable=False, default=dict)
    marks_earned: Mapped[float | None] = mapped_column(Float)
    marks_possible: Mapped[float | None] = mapped_column(Float)
    grading_model: Mapped[str | None] = mapped_column(String(128))
    grading_policy_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="gemini-json-v1", server_default="gemini-json-v1"
    )
    grading_status: Mapped[str] = mapped_column(String(32), nullable=False, default="graded", server_default="graded")
    correction_note: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="attempts")
    question: Mapped[Question] = relationship(back_populates="attempts")


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", "subtopic", "command_word", name="uq_mastery_dimension"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    subtopic: Mapped[str] = mapped_column(String(255), nullable=False)
    command_word: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="mastery_records")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="papers")
    subject: Mapped[Subject] = relationship(back_populates="papers")
    question_links: Mapped[list[PaperQuestion]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    practice_sessions: Mapped[list[PracticeSession]] = relationship(back_populates="paper")


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="real", server_default="real")

    paper: Mapped[Paper] = relationship(back_populates="question_links")
    question: Mapped[Question] = relationship(back_populates="paper_links")


__all__ = [
    "Attempt",
    "Base",
    "CurriculumChapter",
    "Diagnostic",
    "DiagnosticEvidence",
    "DiagnosticResponse",
    "JSONB_TYPE",
    "MarkSchemePoint",
    "Mastery",
    "Paper",
    "PaperQuestion",
    "PracticeAnswer",
    "PracticeSession",
    "Question",
    "QuestionChapterMapping",
    "Recommendation",
    "Subject",
    "User",
]
