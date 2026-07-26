from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    attempts: Mapped[list[Attempt]] = relationship(back_populates="user")
    mastery_records: Mapped[list[Mastery]] = relationship(back_populates="user")
    papers: Mapped[list[Paper]] = relationship(back_populates="user")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    submitted_answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    points_awarded: Mapped[Any] = mapped_column(JSONB_TYPE, nullable=False, default=dict)
    marks_earned: Mapped[float | None] = mapped_column(Float)
    marks_possible: Mapped[float | None] = mapped_column(Float)
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


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    paper: Mapped[Paper] = relationship(back_populates="question_links")
    question: Mapped[Question] = relationship(back_populates="paper_links")


__all__ = [
    "Attempt",
    "Base",
    "JSONB_TYPE",
    "MarkSchemePoint",
    "Mastery",
    "Paper",
    "PaperQuestion",
    "Question",
    "Subject",
    "User",
]
