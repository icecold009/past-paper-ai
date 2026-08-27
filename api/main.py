from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Iterator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.build_prompt import build_prompt
from api.grading import GeminiGrade, grade_answer
from api.auth import AuthContext, get_auth_context
from api.papers import generate_weak_spot_paper
from api.personalization import build_guidance, dismiss_recommendation, approved_chapters
from api.schemas import (
    AttemptCreate,
    CurriculumChapterResponse,
    DiagnosticResponseResult,
    DiagnosticResponseSave,
    DiagnosticStartRequest,
    DiagnosticStartResponse,
    GuidanceChapter,
    GuidanceResponse,
    GradingResult,
    MasteryCell,
    MasteryGridResponse,
    PaperGenerateRequest,
    GeneratedPaperResponse,
    PracticeAnswerResponse,
    PracticeSessionCreate,
    PracticeSessionResponse,
    QuestionResponse,
    RecommendationDismissRequest,
    RecommendationResponse,
    SubjectResponse,
)
from src.db.models import (
    Attempt,
    CurriculumChapter,
    Diagnostic,
    DiagnosticResponse,
    Mastery,
    Paper,
    PracticeAnswer,
    PracticeSession,
    Question,
    QuestionChapterMapping,
    Recommendation,
    Subject,
    User,
)
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


def _chapter_response(chapter: CurriculumChapter) -> CurriculumChapterResponse:
    return CurriculumChapterResponse(
        id=chapter.id,
        subject=_subject_response(chapter.subject),
        grade_stage=chapter.grade_stage,
        syllabus_revision=chapter.syllabus_revision,
        map_version=chapter.map_version,
        chapter_code=chapter.chapter_code,
        name=chapter.name,
        position=chapter.position,
        review_status="approved",
    )


def _guidance_chapter(state: object) -> GuidanceChapter:
    return GuidanceChapter(
        id=state.chapter.id,
        chapter_code=state.chapter.chapter_code,
        name=state.chapter.name,
        grade_stage=state.chapter.grade_stage,
        syllabus_revision=state.chapter.syllabus_revision,
        evidence_count=state.evidence_count,
        score=state.score,
        confidence=state.confidence,
        state=state.state,
    )


def _recommendation_response(recommendation: Recommendation, state: object | None = None) -> RecommendationResponse:
    chapter = state.chapter if state is not None else recommendation.chapter
    return RecommendationResponse(
        id=recommendation.id,
        chapter=GuidanceChapter(
            id=chapter.id,
            chapter_code=chapter.chapter_code,
            name=chapter.name,
            grade_stage=chapter.grade_stage,
            syllabus_revision=chapter.syllabus_revision,
            map_version=chapter.map_version,
            evidence_count=recommendation.evidence_count,
            score=state.score if state is not None else None,
            confidence=recommendation.confidence,
            state=recommendation.state,
        ),
        state=recommendation.state,
        reason=recommendation.reason,
        evidence_count=recommendation.evidence_count,
        confidence=recommendation.confidence,
        activity_type=recommendation.activity_type,
        rule_version=recommendation.rule_version,
        curriculum_version=recommendation.curriculum_version,
        dismissed_at=recommendation.dismissed_at,
    )


def _require_user_access(session: Session, context: AuthContext, user_id: int) -> User:
    if context.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only access your own student data")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} was not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This user is inactive")
    if user.school_id != context.school_id:
        raise HTTPException(status_code=403, detail="The authenticated school scope does not match the user")
    return user


def _practice_response(session: Session, practice: PracticeSession) -> PracticeSessionResponse:
    answers_by_question = {answer.question_id: answer for answer in practice.answers}
    question_ids = [answer.question_id for answer in practice.answers]
    return PracticeSessionResponse(
        id=practice.id,
        user_id=practice.user_id,
        subject=_subject_response(practice.subject),
        state=practice.state,
        question_ids=question_ids,
        answers=[
            PracticeAnswerResponse(
                question_id=question_id,
                answer_text=answers_by_question[question_id].answer_text,
                status=answers_by_question[question_id].status,
            )
            for question_id in question_ids
        ],
        created_at=practice.created_at,
        started_at=practice.started_at,
        submitted_at=practice.submitted_at,
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


def create_app(
    *,
    engine: Engine | None = None,
    grader: Grader | None = None,
    auth_secret: str | None = None,
) -> FastAPI:
    app = FastAPI(title="past-paper-ai API", version="0.1.0")
    app.state.engine = engine
    app.state.grader = grader or grade_answer
    app.state.auth_secret = auth_secret or os.getenv("AUTH_SECRET", "").strip()
    app.state.paper_model = None
    app.state.paper_prompt_builder = None
    return app


app = create_app()


@app.middleware("http")
async def add_request_id(request: Request, call_next: Callable[..., object]) -> object:
    request_id = request.headers.get("X-Request-ID", "").strip() or uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness_check(session: Session = Depends(_session_for_request)) -> dict[str, str]:
    try:
        session.execute(select(1))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready"}


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
        grading_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        grading_policy_version=os.getenv("GRADING_POLICY_VERSION", "gemini-json-v1"),
        grading_status="graded",
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
        grading_model=attempt.grading_model,
        grading_policy_version=attempt.grading_policy_version,
        grading_status=attempt.grading_status,
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


@app.get("/curriculum/{subject}", response_model=list[CurriculumChapterResponse])
def list_curriculum(
    subject: str,
    grade_stage: str | None = Query(default=None, min_length=1, max_length=64),
    session: Session = Depends(_session_for_request),
) -> list[CurriculumChapterResponse]:
    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")
    chapters = approved_chapters(session, subject_id=db_subject.id, grade_stage=grade_stage)
    return [_chapter_response(chapter) for chapter in chapters]


@app.get("/guidance/{user_id}", response_model=GuidanceResponse)
def get_guidance(
    user_id: int,
    subject: str = Query(min_length=1, max_length=16),
    grade_stage: str | None = Query(default=None, min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> GuidanceResponse:
    if user_id < 1:
        raise HTTPException(status_code=422, detail="user_id must be positive")
    user = _require_user_access(session, auth, user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")

    guidance = build_guidance(
        session,
        user_id=user.id,
        subject_id=db_subject.id,
        grade_stage=grade_stage or user.grade_stage,
    )
    session.commit()
    return GuidanceResponse(
        user_id=user.id,
        subject=_subject_response(db_subject),
        state=guidance.state,
        explanation=guidance.explanation,
        chapters=[_guidance_chapter(state) for state in guidance.chapters],
        recommendation=(
            _recommendation_response(guidance.recommendation, guidance.selected)
            if guidance.recommendation is not None
            else None
        ),
    )


@app.post("/recommendations/{recommendation_id}/dismiss", response_model=RecommendationResponse)
def dismiss_recommendation_endpoint(
    recommendation_id: int,
    payload: RecommendationDismissRequest,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> RecommendationResponse:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} was not found")
    _require_user_access(session, auth, payload.user_id)
    if recommendation.user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="You may only dismiss your own recommendation")
    dismiss_recommendation(recommendation=recommendation, session=session)
    session.commit()
    return _recommendation_response(recommendation)


def _diagnostic_response(diagnostic: Diagnostic) -> DiagnosticStartResponse:
    return DiagnosticStartResponse(
        id=diagnostic.id,
        user_id=diagnostic.user_id,
        subject=_subject_response(diagnostic.subject),
        grade_stage=diagnostic.grade_stage,
        state=diagnostic.state,
        questions=[_question_response(response.question) for response in diagnostic.responses],
    )


@app.post("/diagnostics", response_model=DiagnosticStartResponse, status_code=status.HTTP_201_CREATED)
def start_diagnostic(
    payload: DiagnosticStartRequest,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> DiagnosticStartResponse:
    user = _require_user_access(session, auth, payload.user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == payload.subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {payload.subject} was not found")
    if payload.idempotency_key:
        existing = session.scalar(
            select(Diagnostic).where(
                Diagnostic.user_id == user.id,
                Diagnostic.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            return _diagnostic_response(existing)

    query = (
        select(Question)
        .join(QuestionChapterMapping, QuestionChapterMapping.question_id == Question.id)
        .join(CurriculumChapter, CurriculumChapter.id == QuestionChapterMapping.chapter_id)
        .where(
            Question.subject_id == db_subject.id,
            QuestionChapterMapping.review_status == "approved",
            CurriculumChapter.review_status == "approved",
        )
        .distinct()
        .order_by(Question.id)
        .limit(payload.question_limit)
    )
    questions = list(session.scalars(query).all())
    if not questions:
        raise HTTPException(status_code=422, detail="No approved mapped questions are available for this diagnostic")

    now = datetime.now(timezone.utc)
    diagnostic = Diagnostic(
        user_id=user.id,
        subject_id=db_subject.id,
        grade_stage=payload.grade_stage or user.grade_stage,
        state="active",
        idempotency_key=payload.idempotency_key,
        created_at=now,
    )
    session.add(diagnostic)
    session.flush()
    diagnostic.responses = [DiagnosticResponse(question_id=question.id) for question in questions]
    session.commit()
    return _diagnostic_response(diagnostic)


@app.put("/diagnostics/{diagnostic_id}/responses/{question_id}", response_model=DiagnosticResponseResult)
def save_diagnostic_response(
    diagnostic_id: int,
    question_id: int,
    payload: DiagnosticResponseSave,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> DiagnosticResponseResult:
    diagnostic = session.get(Diagnostic, diagnostic_id)
    if diagnostic is None:
        raise HTTPException(status_code=404, detail=f"Diagnostic {diagnostic_id} was not found")
    _require_user_access(session, auth, diagnostic.user_id)
    if diagnostic.state != "active":
        raise HTTPException(status_code=409, detail="This diagnostic is no longer active")
    response = session.scalar(
        select(DiagnosticResponse).where(
            DiagnosticResponse.diagnostic_id == diagnostic_id,
            DiagnosticResponse.question_id == question_id,
        )
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Question is not part of this diagnostic")
    response.answer_text = payload.answer_text
    response.answered_at = datetime.now(timezone.utc)
    session.commit()
    return DiagnosticResponseResult(
        diagnostic_id=diagnostic.id,
        question_id=question_id,
        answer_text=response.answer_text or "",
        state=diagnostic.state,
    )


@app.post("/diagnostics/{diagnostic_id}/submit", response_model=DiagnosticStartResponse)
def submit_diagnostic(
    diagnostic_id: int,
    user_id: int = Query(ge=1),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> DiagnosticStartResponse:
    diagnostic = session.get(Diagnostic, diagnostic_id)
    if diagnostic is None:
        raise HTTPException(status_code=404, detail=f"Diagnostic {diagnostic_id} was not found")
    _require_user_access(session, auth, user_id)
    if diagnostic.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only submit your own diagnostic")
    if diagnostic.state == "active":
        diagnostic.state = "submitted"
        diagnostic.submitted_at = datetime.now(timezone.utc)
        session.commit()
    return _diagnostic_response(diagnostic)


@app.post("/practice/sessions", response_model=PracticeSessionResponse, status_code=status.HTTP_201_CREATED)
def create_practice_session(
    payload: PracticeSessionCreate,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> PracticeSessionResponse:
    user = _require_user_access(session, auth, payload.user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == payload.subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {payload.subject} was not found")
    if payload.idempotency_key:
        existing = session.scalar(
            select(PracticeSession).where(
                PracticeSession.user_id == user.id,
                PracticeSession.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            return _practice_response(session, existing)

    question_ids = list(dict.fromkeys(payload.question_ids))
    questions = list(
        session.scalars(
            select(Question).where(
                Question.id.in_(question_ids),
                Question.subject_id == db_subject.id,
            )
        ).all()
    )
    question_by_id = {question.id: question for question in questions}
    missing = [question_id for question_id in question_ids if question_id not in question_by_id]
    if missing:
        raise HTTPException(status_code=422, detail=f"Questions are unavailable for this subject: {missing}")

    if payload.paper_id is not None:
        paper = session.get(Paper, payload.paper_id)
        if paper is None or paper.user_id != user.id or paper.subject_id != db_subject.id:
            raise HTTPException(status_code=403, detail="The paper is not owned by this user or subject")
    if payload.recommendation_id is not None:
        recommendation = session.get(Recommendation, payload.recommendation_id)
        if recommendation is None or recommendation.user_id != user.id:
            raise HTTPException(status_code=403, detail="The recommendation is not owned by this user")

    now = datetime.now(timezone.utc)
    practice = PracticeSession(
        user_id=user.id,
        subject_id=db_subject.id,
        paper_id=payload.paper_id,
        recommendation_id=payload.recommendation_id,
        state="active",
        idempotency_key=payload.idempotency_key,
        created_at=now,
        started_at=now,
    )
    session.add(practice)
    session.flush()
    practice.answers = [PracticeAnswer(question_id=question_id) for question_id in question_ids]
    session.commit()
    return _practice_response(session, practice)


@app.put("/practice/sessions/{session_id}/answers/{question_id}", response_model=PracticeAnswerResponse)
def save_practice_answer(
    session_id: int,
    question_id: int,
    payload: DiagnosticResponseSave,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> PracticeAnswerResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None:
        raise HTTPException(status_code=404, detail=f"Practice session {session_id} was not found")
    _require_user_access(session, auth, practice.user_id)
    if practice.state not in {"draft", "active"}:
        raise HTTPException(status_code=409, detail="This practice session is no longer editable")
    answer = session.scalar(
        select(PracticeAnswer).where(
            PracticeAnswer.session_id == session_id,
            PracticeAnswer.question_id == question_id,
        )
    )
    if answer is None:
        raise HTTPException(status_code=404, detail="Question is not part of this practice session")
    answer.answer_text = payload.answer_text
    answer.updated_at = datetime.now(timezone.utc)
    session.commit()
    return PracticeAnswerResponse(question_id=question_id, answer_text=answer.answer_text, status=answer.status)


@app.post("/practice/sessions/{session_id}/submit", response_model=PracticeSessionResponse)
def submit_practice_session(
    session_id: int,
    user_id: int = Query(ge=1),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> PracticeSessionResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None:
        raise HTTPException(status_code=404, detail=f"Practice session {session_id} was not found")
    _require_user_access(session, auth, user_id)
    if practice.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only submit your own practice session")
    if practice.state == "submitted":
        return _practice_response(session, practice)
    if practice.state not in {"draft", "active"}:
        raise HTTPException(status_code=409, detail="This practice session cannot be submitted")
    missing_answers = [answer.question_id for answer in practice.answers if not answer.answer_text.strip()]
    if missing_answers:
        raise HTTPException(status_code=422, detail=f"Answer every question before submitting: {missing_answers}")
    now = datetime.now(timezone.utc)
    practice.state = "submitted"
    practice.submitted_at = now
    for answer in practice.answers:
        answer.status = "submitted"
        answer.updated_at = now
    session.commit()
    return _practice_response(session, practice)


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
