from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import GuidanceRecommendation, GuidanceResponse, SubjectResponse
from src.db.models import Attempt, Mastery, Question, Subject, User


def _subject_response(subject: Subject) -> SubjectResponse:
    return SubjectResponse(id=subject.id, code=subject.code, name=subject.name)


def get_guidance(session: Session, *, user_id: int, subject_code: str) -> GuidanceResponse:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} was not found")
    subject = session.scalar(select(Subject).where(Subject.code == subject_code.strip()))
    if subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject_code} was not found")

    questions = list(
        session.scalars(
            select(Question)
            .where(
                Question.subject_id == subject.id,
                Question.topic.is_not(None),
                Question.command_word.is_not(None),
            )
            .order_by(Question.id)
        )
    )
    if not questions:
        return GuidanceResponse(
            user_id=user_id,
            subject=_subject_response(subject),
            status="no_content",
            summary="This subject has no tagged question content yet. Load a reviewed content pack to begin guidance.",
        )

    attempted_ids = set(session.scalars(select(Attempt.question_id).where(Attempt.user_id == user_id)).all())
    mastery_rows = session.scalars(select(Mastery).where(Mastery.user_id == user_id)).all()
    mastery_by_dimension = {(row.topic, row.subtopic, row.command_word): row for row in mastery_rows}

    cells: dict[tuple[str, str], dict[str, object]] = {}
    for question in questions:
        key = (question.topic or "", question.command_word or "")
        cell = cells.setdefault(key, {"scores": [], "has_evidence": False, "subtopic": question.subtopic or ""})
        row = mastery_by_dimension.get((question.topic, question.subtopic or "", question.command_word))
        if row is not None:
            cell["scores"].append(float(row.score))
            cell["has_evidence"] = True

    ranked_cells = []
    for (topic, command_word), cell in cells.items():
        scores = cell["scores"]
        ranked_cells.append(
            (
                0 if not cell["has_evidence"] else 1,
                min(scores) if scores else 0.0,
                topic,
                command_word,
                str(cell["subtopic"]),
                bool(cell["has_evidence"]),
            )
        )
    ranked_cells.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    _, score, topic, command_word, subtopic, has_evidence = ranked_cells[0]

    recommended_question = next(
        (
            question
            for question in questions
            if question.id not in attempted_ids
            and question.topic == topic
            and question.command_word == command_word
        ),
        None,
    )
    if recommended_question is None:
        recommended_question = next((question for question in questions if question.id not in attempted_ids), questions[0])

    if not has_evidence:
        status = "start_diagnostic"
        action = "start_diagnostic"
        summary = f"Start with a short diagnostic in {topic} using the {command_word} command word."
    elif score < 0.7:
        status = "needs_practice"
        action = "practice_weak_cell"
        summary = f"Your next useful step is practice in {topic} with the {command_word} command word ({score:.0%} mastery)."
    else:
        status = "on_track"
        action = "review"
        summary = f"You are on track. Keep your momentum with a {command_word} question in {topic} ({score:.0%} mastery)."

    return GuidanceResponse(
        user_id=user_id,
        subject=_subject_response(subject),
        status=status,
        summary=summary,
        recommendation=GuidanceRecommendation(
            action=action,
            reason=summary,
            question_id=recommended_question.id,
            topic=recommended_question.topic,
            subtopic=recommended_question.subtopic,
            command_word=recommended_question.command_word,
        ),
    )
