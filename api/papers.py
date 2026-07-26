from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import (
    GeneratedPaperQuestion,
    GeneratedPaperResponse,
    PaperGenerateRequest,
    SubjectResponse,
)
from src.build_prompt import build_prompt
from src.db.models import Attempt, MarkSchemePoint, Mastery, Paper, PaperQuestion, Question, Subject, User
from src.generate_paper import generate_text
from src.subject_plan import SUBJECT_PAPER_MARKS


PromptBuilder = Callable[[str], str]


def _marks_possible(question: Question) -> int:
    if question.marks is not None:
        return max(1, int(question.marks))
    point_marks = [point.marks_value or 0 for point in question.mark_scheme_points]
    return max(1, int(sum(point_marks) or len(question.mark_scheme_points) or 1))


def _extract_json(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Gemini did not return a JSON object")
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Gemini paper question response must be a JSON object")
    return payload


def _build_target_prompt(base_prompt: str, *, subject: str, topic: str, command_word: str, marks: int) -> str:
    return f"""{base_prompt}

Create one additional practice question for subject {subject!r} focused exactly on:
- topic: {topic!r}
- command word: {command_word!r}
- maximum marks: {marks}

Return JSON only, with this shape:
{{"question_text":"...", "marks": {marks}, "mark_scheme_points":["..."]}}
The question must be original, answerable without diagrams, and suitable for the subject.
The mark_scheme_points array must contain concise, independently gradeable points.
"""


def _make_ai_question(
    *,
    subject: str,
    topic: str,
    command_word: str,
    marks: int,
    model: object | None,
    prompt_builder: PromptBuilder,
) -> dict[str, object]:
    try:
        try:
            base_prompt = prompt_builder(subject)
        except FileNotFoundError:
            base_prompt = "Use the reviewed Cambridge-style syllabus and concise exam wording."
        prompt = _build_target_prompt(
            base_prompt,
            subject=subject,
            topic=topic,
            command_word=command_word,
            marks=marks,
        )
        last_error: Exception | None = None
        for _ in range(2):
            try:
                payload = _extract_json(generate_text(prompt, model_name="gemini-2.5-flash", model=model))
                question_text = str(payload.get("question_text", "")).strip()
                points = payload.get("mark_scheme_points", [])
                if not question_text or not isinstance(points, list) or not points:
                    raise ValueError("Gemini response needs question_text and mark_scheme_points")
                generated_marks = min(marks, max(1, int(payload.get("marks", marks))))
                return {
                    "question_text": question_text,
                    "marks": generated_marks,
                    "mark_scheme_points": [str(point).strip() for point in points if str(point).strip()],
                }
            except Exception as exc:  # retry once with the same strict JSON contract
                last_error = exc
        raise ValueError(str(last_error or "invalid Gemini response"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI weak-spot question generation failed: {exc}") from exc


def _subject_response(subject: Subject) -> SubjectResponse:
    return SubjectResponse(id=subject.id, code=subject.code, name=subject.name)


def _paper_question_response(
    question: Question,
    *,
    position: int,
    source_type: str,
) -> GeneratedPaperQuestion:
    return GeneratedPaperQuestion(
        id=question.id,
        position=position,
        source_type=source_type,
        paper=question.paper,
        year=question.year,
        session=question.session,
        variant=question.variant,
        question_number=question.question_number,
        sub_label=question.sub_label,
        topic=question.topic,
        subtopic=question.subtopic,
        command_word=question.command_word,
        marks=_marks_possible(question),
        raw_text=question.raw_text,
    )


def generate_weak_spot_paper(
    session: Session,
    payload: PaperGenerateRequest,
    *,
    model: object | None = None,
    prompt_builder: PromptBuilder = build_prompt,
) -> GeneratedPaperResponse:
    subject_code = payload.subject.strip()
    configured_papers = SUBJECT_PAPER_MARKS.get(subject_code)
    if not configured_papers:
        raise HTTPException(status_code=404, detail=f"No paper configuration was found for subject {subject_code}")

    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id} was not found")
    subject = session.scalar(select(Subject).where(Subject.code == subject_code))
    if subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject_code} was not found")

    paper_code = (payload.paper or next(iter(configured_papers))).strip().lower()
    if paper_code not in configured_papers:
        raise HTTPException(status_code=422, detail=f"Paper {paper_code} is not configured for subject {subject_code}")
    target_marks = payload.target_marks or configured_papers[paper_code]

    all_questions = list(
        session.scalars(
            select(Question)
            .where(
                Question.subject_id == subject.id,
                Question.paper == paper_code,
                Question.topic.is_not(None),
                Question.command_word.is_not(None),
                Question.paper != "ai_generated",
            )
            .order_by(Question.id)
        )
    )
    attempted_ids = set(
        session.scalars(select(Attempt.question_id).where(Attempt.user_id == payload.user_id)).all()
    )
    unseen = [question for question in all_questions if question.id not in attempted_ids]
    questions_by_cell: dict[tuple[str, str], list[Question]] = {}
    for question in unseen:
        questions_by_cell.setdefault((question.topic or "", question.command_word or ""), []).append(question)

    dimensions = {(question.topic or "", question.subtopic or "", question.command_word or "") for question in all_questions}
    mastery_rows = session.scalars(select(Mastery).where(Mastery.user_id == payload.user_id)).all()
    mastery_by_dimension = {(row.topic, row.subtopic, row.command_word): row for row in mastery_rows}
    cells: dict[tuple[str, str], dict[str, object]] = {}
    for topic, subtopic, command_word in dimensions:
        cell = cells.setdefault((topic, command_word), {"scores": [], "has_evidence": False})
        row = mastery_by_dimension.get((topic, subtopic, command_word))
        if row is not None:
            cell["scores"].append(float(row.score))
            cell["has_evidence"] = True

    ranked_cells = []
    for (topic, command_word), cell in cells.items():
        scores = cell["scores"]
        score = min(scores) if scores else 0.0
        ranked_cells.append((score, topic, command_word))
    ranked_cells.sort(key=lambda item: (item[0], item[1], item[2]))
    weak_cells = ranked_cells[:4]

    # The deterministic seed keeps a repeated local demo explainable while still
    # distributing a larger real-question pool over the weakest cells.
    rng = random.Random(f"{payload.user_id}:{subject_code}:{paper_code}")
    selected: list[tuple[Question | None, str, dict[str, object] | None, str, str]] = []
    remaining = target_marks
    for _, topic, command_word in weak_cells:
        candidates = questions_by_cell.get((topic, command_word), [])
        fallback_count = max(0, payload.min_real_questions_per_cell - len(candidates))
        for _ in range(fallback_count):
            if remaining <= 0:
                break
            generated = _make_ai_question(
                subject=subject_code,
                topic=topic,
                command_word=command_word,
                marks=min(5, remaining),
                model=model,
                prompt_builder=prompt_builder,
            )
            selected.append((None, "ai_generated", generated, topic, command_word))
            remaining -= int(generated["marks"])

    while remaining > 0:
        weighted_candidates = [
            (question, score, topic, command_word)
            for score, topic, command_word in weak_cells
            for question in questions_by_cell.get((topic, command_word), [])
            if _marks_possible(question) <= remaining
        ]
        if not weighted_candidates:
            break
        chosen = rng.choices(
            weighted_candidates,
            weights=[1.0 + (1.0 - score) * 4.0 for _, score, _, _ in weighted_candidates],
            k=1,
        )[0]
        question, _, topic, command_word = chosen
        questions_by_cell[(topic, command_word)].remove(question)
        selected.append((question, "real", None, topic, command_word))
        remaining -= _marks_possible(question)

    if not selected:
        raise HTTPException(status_code=422, detail="No unseen real questions or AI fallback questions were available")

    paper = Paper(user_id=payload.user_id, subject_id=subject.id, mode="weak_spot")
    session.add(paper)
    session.flush()
    responses: list[GeneratedPaperQuestion] = []
    total_marks = 0
    now_year = datetime.now(timezone.utc).year
    for position, (question, source_type, generated, topic, command_word) in enumerate(selected, start=1):
        if question is None:
            assert generated is not None
            question = Question(
                subject_id=subject.id,
                paper="ai_generated",
                year=now_year,
                session="AI generated",
                variant=str(paper.id),
                question_number=f"AI-{position}",
                sub_label="",
                topic=topic,
                subtopic="",
                command_word=command_word,
                difficulty="medium",
                marks=int(generated["marks"]),
                raw_text=str(generated["question_text"]),
            )
            session.add(question)
            session.flush()
            for point_text in generated["mark_scheme_points"]:
                session.add(MarkSchemePoint(question_id=question.id, point_text=str(point_text), marks_value=1))
        session.add(PaperQuestion(paper_id=paper.id, question_id=question.id, position=position, source_type=source_type))
        total_marks += _marks_possible(question)
        responses.append(_paper_question_response(question, position=position, source_type=source_type))

    session.commit()
    return GeneratedPaperResponse(
        id=paper.id,
        user_id=payload.user_id,
        subject=_subject_response(subject),
        mode="weak_spot",
        paper=paper_code,
        target_marks=target_marks,
        total_marks=total_marks,
        questions=responses,
    )
