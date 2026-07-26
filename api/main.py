from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.build_prompt import build_prompt
from api.grading import GeminiGrade, grade_answer
from api.papers import generate_weak_spot_paper
from api.schemas import (
    AttemptCreate,
    GradingResult,
    MasteryCell,
    MasteryGridResponse,
    PaperGenerateRequest,
    GeneratedPaperResponse,
    QuestionResponse,
    SubjectResponse,
)
from src.db.models import Attempt, Mastery, Question, Subject, User
from src.db.session import create_db_engine


Grader = Callable[..., GeminiGrade]


def _subject_response(subject: Subject) -> SubjectResponse:
    return SubjectResponse(id=subject.id, code=subject.code, name=subject.name)


def _question_response(question: Question) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        subject=_subject_response(question.subject),
        paper=question.paper,
        year=question.year,
        session=question.session,
        variant=question.variant,
        question_number=question.question_number,
        sub_label=question.sub_label,
        topic=question.topic,
        subtopic=question.subtopic,
        command_word=question.command_word,
        difficulty=question.difficulty,
        marks=question.marks,
        raw_text=question.raw_text,
    )


def _marks_possible(question: Question) -> float:
    if question.marks is not None:
        return float(question.marks)
    marked_points = [point.marks_value for point in question.mark_scheme_points if point.marks_value]
    return float(sum(marked_points) or len(question.mark_scheme_points))


def _score(attempt: Attempt) -> float | None:
    if attempt.marks_earned is None or not attempt.marks_possible:
        return None
    return max(0.0, min(1.0, float(attempt.marks_earned) / float(attempt.marks_possible)))


def _recompute_mastery(session: Session, *, user_id: int, question: Question, now: datetime) -> bool:
    if not question.topic or not question.command_word:
        return False

    subtopic = question.subtopic or ""
    attempts = list(
        session.scalars(
            select(Attempt)
            .join(Question, Attempt.question_id == Question.id)
            .where(
                Attempt.user_id == user_id,
                Question.subject_id == question.subject_id,
                Question.topic == question.topic,
                func.coalesce(Question.subtopic, "") == subtopic,
                Question.command_word == question.command_word,
            )
            .order_by(Attempt.attempted_at.desc(), Attempt.id.desc())
            .limit(20)
        )
    )
    scored_attempts = [(index, _score(attempt)) for index, attempt in enumerate(attempts)]
    scored_attempts = [(index, value) for index, value in scored_attempts if value is not None]
    if not scored_attempts:
        return False

    # Recent attempts have more influence while the formula remains transparent for v1.
    weighted_total = sum(value / (index + 1) for index, value in scored_attempts)
    weight_total = sum(1 / (index + 1) for index, _ in scored_attempts)
    score = weighted_total / weight_total

    mastery = session.scalar(
        select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.topic == question.topic,
            Mastery.subtopic == subtopic,
            Mastery.command_word == question.command_word,
        )
    )
    if mastery is None:
        mastery = Mastery(
            user_id=user_id,
            topic=question.topic,
            subtopic=subtopic,
            command_word=question.command_word,
        )
        session.add(mastery)
    mastery.score = score
    mastery.last_reviewed_at = now
    return True


def _session_for_request(request: Request) -> Iterator[Session]:
    engine: Engine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        try:
            engine = create_db_engine()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        request.app.state.engine = engine
    with Session(engine) as session:
        yield session


def create_app(*, engine: Engine | None = None, grader: Grader | None = None) -> FastAPI:
    app = FastAPI(title="past-paper-ai API", version="0.1.0")
    app.state.engine = engine
    app.state.grader = grader or grade_answer
    app.state.paper_model = None
    app.state.paper_prompt_builder = None
    return app


app = create_app()


@app.get("/subjects", response_model=list[SubjectResponse])
def list_subjects(session: Session = Depends(_session_for_request)) -> list[SubjectResponse]:
    subjects = session.scalars(select(Subject).order_by(Subject.code)).all()
    return [_subject_response(subject) for subject in subjects]


@app.get("/questions", response_model=list[QuestionResponse])
def list_questions(
    subject: str | None = Query(default=None, min_length=1, max_length=16),
    topic: str | None = Query(default=None, min_length=1, max_length=255),
    command_word: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(_session_for_request),
) -> list[QuestionResponse]:
    query = select(Question).join(Subject).order_by(Subject.code, Question.id).limit(limit)
    if subject:
        query = query.where(Subject.code == subject.strip())
    if topic:
        query = query.where(Question.topic == topic.strip())
    if command_word:
        query = query.where(Question.command_word == command_word.strip())
    questions = session.scalars(query).all()
    return [_question_response(question) for question in questions]


@app.post("/attempts", response_model=GradingResult, status_code=status.HTTP_201_CREATED)
def create_attempt(
    payload: AttemptCreate,
    request: Request,
    session: Session = Depends(_session_for_request),
) -> GradingResult:
    user = session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id} was not found")

    question = session.scalar(select(Question).where(Question.id == payload.question_id))
    if question is None:
        raise HTTPException(status_code=404, detail=f"Question {payload.question_id} was not found")
    if not question.mark_scheme_points:
        raise HTTPException(
            status_code=422,
            detail="This question has no mark-scheme points available for grading",
        )

    marks_possible = _marks_possible(question)
    point_payload = [
        {"point_text": point.point_text, "marks_value": point.marks_value}
        for point in question.mark_scheme_points
    ]
    try:
        result = request.app.state.grader(
            question_text=question.raw_text,
            mark_scheme_points=point_payload,
            submitted_answer_text=payload.submitted_answer_text,
            marks_possible=marks_possible,
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Answer grading failed: {exc}") from exc

    now = datetime.now(timezone.utc)
    attempt = Attempt(
        user_id=payload.user_id,
        question_id=payload.question_id,
        submitted_answer_text=payload.submitted_answer_text,
        points_awarded={
            "points_hit": result.points_hit,
            "points_missed": result.points_missed,
            "feedback": result.feedback,
        },
        marks_earned=result.marks_earned,
        marks_possible=marks_possible,
        attempted_at=now,
    )
    session.add(attempt)
    session.flush()
    mastery_updated = _recompute_mastery(
        session, user_id=payload.user_id, question=question, now=now
    )
    session.commit()

    return GradingResult(
        attempt_id=attempt.id,
        user_id=payload.user_id,
        question_id=payload.question_id,
        points_hit=result.points_hit,
        points_missed=result.points_missed,
        marks_earned=result.marks_earned,
        marks_possible=marks_possible,
        feedback=result.feedback,
        mastery_updated=mastery_updated,
    )


@app.get("/mastery/{user_id}", response_model=MasteryGridResponse)
def get_mastery(
    user_id: int,
    subject: str = Query(min_length=1, max_length=16),
    session: Session = Depends(_session_for_request),
) -> MasteryGridResponse:
    if user_id < 1:
        raise HTTPException(status_code=422, detail="user_id must be positive")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} was not found")

    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")

    dimensions = session.execute(
        select(Question.topic, Question.subtopic, Question.command_word)
        .where(
            Question.subject_id == db_subject.id,
            Question.topic.is_not(None),
            Question.command_word.is_not(None),
        )
        .distinct()
    ).all()
    mastery_rows = session.scalars(select(Mastery).where(Mastery.user_id == user_id)).all()
    mastery_by_dimension = {
        (row.topic, row.subtopic, row.command_word): row for row in mastery_rows
    }

    cells: list[MasteryCell] = []
    for topic, subtopic, command_word in sorted(
        dimensions, key=lambda item: (item[0] or "", item[1] or "", item[2] or "")
    ):
        key = (topic, subtopic or "", command_word)
        row = mastery_by_dimension.get(key)
        cells.append(
            MasteryCell(
                subject=db_subject.code,
                topic=topic,
                subtopic=subtopic or "",
                command_word=command_word,
                score=row.score if row else 0.0,
                has_evidence=row is not None,
                last_reviewed_at=row.last_reviewed_at if row else None,
            )
        )

    return MasteryGridResponse(
        user_id=user_id,
        subject=_subject_response(db_subject),
        cells=cells,
    )


@app.post("/papers/generate", response_model=GeneratedPaperResponse, status_code=status.HTTP_201_CREATED)
def create_paper(
    payload: PaperGenerateRequest,
    request: Request,
    session: Session = Depends(_session_for_request),
) -> GeneratedPaperResponse:
    prompt_builder = request.app.state.paper_prompt_builder
    return generate_weak_spot_paper(
        session,
        payload,
        model=request.app.state.paper_model,
        prompt_builder=prompt_builder or build_prompt,
    )
