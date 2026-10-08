from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from src.db.models import (
    Attempt,
    Diagnostic,
    DiagnosticEvidence,
    DiagnosticResponse,
    Mastery,
    MarkSchemePoint,
    Paper,
    PaperQuestion,
    PracticeAnswer,
    PracticeSession,
    Question,
    QuestionChapterMapping,
    Recommendation,
    User,
)


def _records(rows: Iterable[object], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: getattr(row, field) for field in fields} for row in rows]


def generated_question_owner_ids(session: Session, question_id: int) -> set[int]:
    return set(
        session.scalars(
            select(Paper.user_id)
            .join(PaperQuestion, PaperQuestion.paper_id == Paper.id)
            .where(
                PaperQuestion.question_id == question_id,
                PaperQuestion.source_type == "ai_generated",
            )
            .distinct()
        ).all()
    )


def is_generated_question(session: Session, question: Question | int) -> bool:
    question_id = question if isinstance(question, int) else question.id
    if not isinstance(question, int) and question.paper == "ai_generated":
        return True
    return (
        session.scalar(
            select(PaperQuestion.question_id)
            .where(
                PaperQuestion.question_id == question_id,
                PaperQuestion.source_type == "ai_generated",
            )
            .limit(1)
        )
        is not None
    )


def export_student_data(session: Session, user: User) -> dict[str, object]:
    """Return the authenticated user's app-held records without copying shared content."""
    user_id = user.id
    diagnostics = select(Diagnostic).where(Diagnostic.user_id == user_id)
    sessions = select(PracticeSession).where(PracticeSession.user_id == user_id)
    papers = select(Paper).where(Paper.user_id == user_id)
    paper_question_rows = session.scalars(
        select(PaperQuestion)
        .join(Paper, Paper.id == PaperQuestion.paper_id)
        .where(Paper.user_id == user_id)
        .order_by(PaperQuestion.paper_id, PaperQuestion.position)
        .options(selectinload(PaperQuestion.question).selectinload(Question.mark_scheme_points))
    ).all()
    paper_question_records: list[dict[str, Any]] = []
    for link in paper_question_rows:
        question = link.question
        is_generated = link.source_type == "ai_generated" or question.paper == "ai_generated"
        record: dict[str, Any] = {
            "paper_id": link.paper_id,
            "question_id": link.question_id,
            "position": link.position,
            "source_type": link.source_type,
            "generated_content": None,
        }
        if is_generated:
            owns_generated_content = generated_question_owner_ids(session, question.id) == {user_id}
            record["generated_content_status"] = (
                "available" if owns_generated_content else "unavailable_ambiguous_or_missing_owner"
            )
            if owns_generated_content:
                record["generated_content"] = {
                    "raw_text": question.raw_text,
                    "marks": question.marks,
                    "mark_scheme_points": [
                        {"point_text": point.point_text, "marks_value": point.marks_value}
                        for point in question.mark_scheme_points
                    ],
                }
        paper_question_records.append(record)

    return {
        "format_version": 1,
        "exported_at": datetime.now(timezone.utc),
        "profile": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "school_id": user.school_id,
            "grade_stage": user.grade_stage,
            "is_active": user.is_active,
            "created_at": user.created_at,
        },
        "records": {
            "attempts": _records(
                session.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.id)).all(),
                (
                    "id", "question_id", "submitted_answer_text", "points_awarded", "marks_earned",
                    "marks_possible", "grading_model", "grading_policy_version", "grading_status",
                    "correction_note", "corrected_at", "attempted_at",
                ),
            ),
            "mastery": _records(
                session.scalars(select(Mastery).where(Mastery.user_id == user_id).order_by(Mastery.id)).all(),
                (
                    "id", "topic", "subtopic", "command_word", "score", "last_reviewed_at",
                    "next_review_at",
                ),
            ),
            "papers": _records(
                session.scalars(papers.order_by(Paper.id)).all(),
                ("id", "subject_id", "mode", "created_at"),
            ),
            "paper_questions": paper_question_records,
            "diagnostic_evidence": _records(
                session.scalars(
                    select(DiagnosticEvidence)
                    .where(DiagnosticEvidence.user_id == user_id)
                    .order_by(DiagnosticEvidence.id)
                ).all(),
                (
                    "id", "chapter_id", "attempt_id", "source_type", "evidence_count", "score",
                    "confidence", "state", "observed_at",
                ),
            ),
            "recommendations": _records(
                session.scalars(
                    select(Recommendation).where(Recommendation.user_id == user_id).order_by(Recommendation.id)
                ).all(),
                (
                    "id", "chapter_id", "state", "reason", "evidence_count", "confidence", "activity_type",
                    "rule_version", "curriculum_version", "decision_source", "decision_version",
                    "decision_confidence", "provider_model", "selection_distribution", "dismissed_at",
                    "created_at",
                ),
            ),
            "diagnostics": _records(
                session.scalars(diagnostics.order_by(Diagnostic.id)).all(),
                (
                    "id", "subject_id", "grade_stage", "state", "idempotency_key", "created_at",
                    "submitted_at",
                ),
            ),
            "diagnostic_responses": _records(
                session.scalars(
                    select(DiagnosticResponse)
                    .join(Diagnostic, Diagnostic.id == DiagnosticResponse.diagnostic_id)
                    .where(Diagnostic.user_id == user_id)
                    .order_by(DiagnosticResponse.id)
                ).all(),
                (
                    "id", "diagnostic_id", "question_id", "answer_text", "marks_earned", "marks_possible",
                    "feedback", "answered_at",
                ),
            ),
            "practice_sessions": _records(
                session.scalars(sessions.order_by(PracticeSession.id)).all(),
                (
                    "id", "subject_id", "paper_id", "recommendation_id", "state", "idempotency_key",
                    "created_at", "started_at", "submitted_at",
                ),
            ),
            "practice_answers": _records(
                session.scalars(
                    select(PracticeAnswer)
                    .join(PracticeSession, PracticeSession.id == PracticeAnswer.session_id)
                    .where(PracticeSession.user_id == user_id)
                    .order_by(PracticeAnswer.id)
                ).all(),
                ("id", "session_id", "question_id", "answer_text", "status", "attempt_id", "updated_at"),
            ),
        },
        "shared_content_note": "Shared source questions and mark schemes are referenced by ID only. Private AI-generated question text and marks are included only when this user's paper is the sole owner.",
    }


def _erase_generated_question_content(session: Session, question_ids: list[int]) -> None:
    if not question_ids:
        return

    session.execute(delete(MarkSchemePoint).where(MarkSchemePoint.question_id.in_(question_ids)))
    session.execute(delete(QuestionChapterMapping).where(QuestionChapterMapping.question_id.in_(question_ids)))

    referenced_ids: set[int] = set()
    for model in (Attempt, DiagnosticResponse, PracticeAnswer, PaperQuestion):
        referenced_ids.update(
            session.scalars(select(model.question_id).where(model.question_id.in_(question_ids))).all()
        )

    unreferenced_ids = set(question_ids) - referenced_ids
    if referenced_ids:
        session.execute(
            Question.__table__.update()
            .where(Question.id.in_(referenced_ids))
            .values(
                raw_text="",
                topic=None,
                subtopic=None,
                command_word=None,
                difficulty=None,
                marks=None,
            )
        )
    if unreferenced_ids:
        session.execute(delete(Question).where(Question.id.in_(unreferenced_ids)))


def delete_student_data(session: Session, user_id: int) -> None:
    """Erase app-held user records in dependency order, preserving shared content."""
    diagnostic_ids = select(Diagnostic.id).where(Diagnostic.user_id == user_id)
    practice_session_ids = select(PracticeSession.id).where(PracticeSession.user_id == user_id)
    paper_ids = select(Paper.id).where(Paper.user_id == user_id)
    generated_question_ids = list(
        session.scalars(
            select(PaperQuestion.question_id)
            .join(Paper, Paper.id == PaperQuestion.paper_id)
            .join(Question, Question.id == PaperQuestion.question_id)
            .where(
                Paper.user_id == user_id,
                or_(
                    PaperQuestion.source_type == "ai_generated",
                    Question.paper == "ai_generated",
                ),
            )
            .distinct()
        ).all()
    )

    session.execute(
        delete(DiagnosticResponse).where(DiagnosticResponse.diagnostic_id.in_(diagnostic_ids))
    )
    session.execute(delete(PracticeAnswer).where(PracticeAnswer.session_id.in_(practice_session_ids)))
    session.execute(delete(DiagnosticEvidence).where(DiagnosticEvidence.user_id == user_id))
    session.execute(delete(PracticeSession).where(PracticeSession.user_id == user_id))
    session.execute(delete(Diagnostic).where(Diagnostic.user_id == user_id))
    session.execute(delete(Recommendation).where(Recommendation.user_id == user_id))
    session.execute(delete(Mastery).where(Mastery.user_id == user_id))
    session.execute(delete(Attempt).where(Attempt.user_id == user_id))
    session.execute(delete(PaperQuestion).where(PaperQuestion.paper_id.in_(paper_ids)))
    session.execute(delete(Paper).where(Paper.user_id == user_id))
    session.execute(delete(User).where(User.id == user_id))
    _erase_generated_question_content(session, generated_question_ids)
