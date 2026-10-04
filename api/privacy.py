from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.db.models import (
    Attempt,
    Diagnostic,
    DiagnosticEvidence,
    DiagnosticResponse,
    Mastery,
    Paper,
    PaperQuestion,
    PracticeAnswer,
    PracticeSession,
    Recommendation,
    User,
)


def _records(rows: Iterable[object], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: getattr(row, field) for field in fields} for row in rows]


def export_student_data(session: Session, user: User) -> dict[str, object]:
    """Return the authenticated user's app-held records without copying shared content."""
    user_id = user.id
    diagnostics = select(Diagnostic).where(Diagnostic.user_id == user_id)
    sessions = select(PracticeSession).where(PracticeSession.user_id == user_id)
    papers = select(Paper).where(Paper.user_id == user_id)

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
            "paper_questions": _records(
                session.scalars(
                    select(PaperQuestion)
                    .join(Paper, Paper.id == PaperQuestion.paper_id)
                    .where(Paper.user_id == user_id)
                    .order_by(PaperQuestion.paper_id, PaperQuestion.position)
                ).all(),
                ("paper_id", "question_id", "position", "source_type"),
            ),
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
        "shared_content_note": "Question text and other shared source content are referenced by ID and are not included in this personal-data export.",
    }


def delete_student_data(session: Session, user_id: int) -> None:
    """Erase app-held user records in dependency order, preserving shared content."""
    diagnostic_ids = select(Diagnostic.id).where(Diagnostic.user_id == user_id)
    practice_session_ids = select(PracticeSession.id).where(PracticeSession.user_id == user_id)
    paper_ids = select(Paper.id).where(Paper.user_id == user_id)

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
