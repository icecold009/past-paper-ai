from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Iterator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.build_prompt import build_prompt
from api.grading import GeminiGrade, grade_answer
from api.auth import AuthContext, get_auth_context
from api.papers import generate_weak_spot_paper
from api.privacy import (
    delete_student_data,
    export_student_data,
    generated_question_owner_ids,
    is_generated_question,
)
from api.personalization import build_guidance, dismiss_recommendation, approved_chapters
from api.recommendation_selection import RecommendationSelector
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
    PrivacyDeletionRequest,
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
    PaperQuestion,
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
        map_version=state.chapter.map_version,
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
        decision_source=recommendation.decision_source,
        decision_version=recommendation.decision_version,
        decision_confidence=recommendation.decision_confidence,
        provider_model=recommendation.provider_model,
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


def _require_privacy_owner(session: Session, context: AuthContext, user_id: int) -> User:
    """Allow an authenticated owner to export or erase data even if the profile is inactive."""
    if context.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only access your own student data")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} was not found")
    if user.school_id != context.school_id:
        raise HTTPException(status_code=403, detail="The authenticated school scope does not match the user")
    return user


def _require_generated_question_owner(session: Session, question: Question, user_id: int) -> None:
    if not is_generated_question(session, question):
        return
    if generated_question_owner_ids(session, question.id) != {user_id}:
        raise HTTPException(status_code=404, detail="Question was not found")


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
    guidance_selector: RecommendationSelector | None = None,
) -> FastAPI:
    app = FastAPI(title="past-paper-ai API", version="0.1.0")
    app.state.engine = engine
    app.state.grader = grader or grade_answer
    app.state.auth_secret = auth_secret or os.getenv("AUTH_SECRET", "").strip()
    app.state.paper_model = None
    app.state.paper_prompt_builder = None
    app.state.guidance_selector = guidance_selector
    # There is no approved provider for the intended 14-18 audience yet.
    # Keep student-data egress disabled until a provider and school policy are approved.
    app.state.student_data_ai_approved = False
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
    chapter_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(_session_for_request),
) -> list[QuestionResponse]:
    effective_subject = subject.strip() if isinstance(subject, str) else None
    effective_topic = topic.strip() if isinstance(topic, str) else None
    effective_command_word = command_word.strip() if isinstance(command_word, str) else None
    effective_limit = limit if isinstance(limit, int) else 50
    generated_link = (
        select(PaperQuestion.question_id)
        .where(
            PaperQuestion.question_id == Question.id,
            PaperQuestion.source_type == "ai_generated",
        )
        .exists()
    )
    query = (
        select(Question)
        .join(Subject)
        .where(Question.paper != "ai_generated", ~generated_link)
        .order_by(Subject.code, Question.id)
        .limit(effective_limit)
    )
    if effective_subject:
        query = query.where(Subject.code == effective_subject)
    if effective_topic:
        query = query.where(Question.topic == effective_topic)
    if effective_command_word:
        query = query.where(Question.command_word == effective_command_word)
    if isinstance(chapter_id, int) and chapter_id > 0:
        query = query.join(
            QuestionChapterMapping,
            QuestionChapterMapping.question_id == Question.id,
        ).where(
            QuestionChapterMapping.chapter_id == chapter_id,
            QuestionChapterMapping.review_status == "approved",
        )
    questions = session.scalars(query).all()
    return [_question_response(question) for question in questions]


@app.post("/attempts", response_model=GradingResult, status_code=status.HTTP_201_CREATED)
def create_attempt(
    payload: AttemptCreate,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> GradingResult:
    user = _require_user_access(session, auth, payload.user_id)
    if not getattr(request.app.state, "student_data_ai_approved", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Student-answer AI grading is unavailable until an age-eligible provider and school data policy are approved",
        )

    question = session.scalar(select(Question).where(Question.id == payload.question_id))
    if question is None:
        raise HTTPException(status_code=404, detail=f"Question {payload.question_id} was not found")
    _require_generated_question_owner(session, question, user.id)
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
        user_id=user.id,
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
        session, user_id=user.id, question=question, now=now
    )
    session.commit()

    return GradingResult(
        attempt_id=attempt.id,
        user_id=user.id,
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
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MasteryGridResponse:
    user = _require_user_access(session, auth, user_id)

    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")

    generated_link = (
        select(PaperQuestion.question_id)
        .where(
            PaperQuestion.question_id == Question.id,
            PaperQuestion.source_type == "ai_generated",
        )
        .exists()
    )
    owned_generated_link = (
        select(PaperQuestion.question_id)
        .join(Paper, Paper.id == PaperQuestion.paper_id)
        .where(
            PaperQuestion.question_id == Question.id,
            PaperQuestion.source_type == "ai_generated",
            Paper.user_id == user.id,
        )
        .exists()
    )
    other_generated_owner = (
        select(PaperQuestion.question_id)
        .join(Paper, Paper.id == PaperQuestion.paper_id)
        .where(
            PaperQuestion.question_id == Question.id,
            PaperQuestion.source_type == "ai_generated",
            Paper.user_id != user.id,
        )
        .exists()
    )
    dimensions = session.execute(
        select(Question.topic, Question.subtopic, Question.command_word)
        .where(
            Question.subject_id == db_subject.id,
            Question.topic.is_not(None),
            Question.command_word.is_not(None),
            or_(
                and_(Question.paper != "ai_generated", ~generated_link),
                and_(owned_generated_link, ~other_generated_owner),
            ),
        )
        .distinct()
    ).all()
    mastery_rows = session.scalars(select(Mastery).where(Mastery.user_id == user.id)).all()
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
        user_id=user.id,
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


def _guidance_selector(request: Request) -> RecommendationSelector | None:
    if not getattr(request.app.state, "student_data_ai_approved", False):
        return None
    return getattr(request.app.state, "guidance_selector", None)


@app.get("/guidance/{user_id}", response_model=GuidanceResponse)
def get_guidance(
    user_id: int,
    subject: str = Query(min_length=1, max_length=16),
    grade_stage: str | None = Query(default=None, min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context),
    selector: RecommendationSelector | None = Depends(_guidance_selector),
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
        subject_code=db_subject.code,
        selector=selector,
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


def _diagnostic_response(session: Session, diagnostic: Diagnostic) -> DiagnosticStartResponse:
    return DiagnosticStartResponse(
        id=diagnostic.id,
        user_id=diagnostic.user_id,
        subject=_subject_response(diagnostic.subject),
        grade_stage=diagnostic.grade_stage,
        state=diagnostic.state,
        questions=[
            _question_response(response.question)
            for response in diagnostic.responses
            if not is_generated_question(session, response.question)
            or genes^úãkh‘éì¶»§q«^t€€€€€€€€€€€€€€À°(€€€€€€€€€€€€€€€€€€€µ½‘•°¹}}¹…µ•}|°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€‘¥…¹½ÍÑ¥}¥‘Ì€ôÍ•±•Ð¡¥…¹½ÍÑ¥Œ¹¥¤¹Ý¡•É”¡¥…¹½ÍÑ¥Œ¹ÕÍ•É}¥€ôô€Ü¤(€€€€€€€€€€€ÁÉ…Ñ¥•}Í•ÍÍ¥½¹}¥‘Ì€ôÍ•±•Ð¡AÉ…Ñ¥•M•ÍÍ¥½¸¹¥¤¹Ý¡•É”¡AÉ…Ñ¥•M•ÍÍ¥½¸¹ÕÍ•É}¥€ôô€Ü¤(€€€€€€€€€€€ÕÍ•É}Á…Á•É}¥‘Ì€ôÍ•±•Ð¡A…Á•È¹¥¤¹Ý¡•É”¡A…Á•È¹ÕÍ•É}¥€ôô€Ü¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡¥…¹½ÍÑ¥I•ÍÁ½¹Í”¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€¥…¹½ÍÑ¥I•ÍÁ½¹Í”¹‘¥…¹½ÍÑ¥}¥¹¥¹|¡‘¥…¹½ÍÑ¥}¥‘Ì¤(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€À°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡AÉ…Ñ¥•¹ÍÝ•È¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€AÉ…Ñ¥•¹ÍÝ•È¹Í•ÍÍ¥½¹}¥¹¥¹|¡ÁÉ…Ñ¥•}Í•ÍÍ¥½¹}¥‘Ì¤(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€À°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡A…Á•ÉEÕ•ÍÑ¥½¸¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€A…Á•ÉEÕ•ÍÑ¥½¸¹Á…Á•É}¥¹¥¹|¡ÕÍ•É}Á…Á•É}¥‘Ì¤(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€À°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡Í•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡ÑÑ•µÁÐ¤¹Ý¡•É”¡ÑÑ•µÁÐ¹ÕÍ•É}¥€ôô€à¤¤°€Ä¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡Í•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡A…Á•ÉEÕ•ÍÑ¥½¸¤¤°€Ä¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½Ñ9½¹”¡Í•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÄ¤¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½Ñ9½¹”¡Í•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡5…É­M¡•µ•A½¥¹Ð¤¹Ý¡•É”¡5…É­M¡•µ•A½¥¹Ð¹ÅÕ•ÍÑ¥½¹}¥€ôô€ÄÄ¤¤¤((€€€‘•˜Ñ•ÍÑ}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¹Í}…É•}¡¥‘‘•¹}…¹‘}½Ý¹•É}Í½Á•‘}™½É}…ÑÑ•µÁÑÍ}…¹‘}Í•ÍÍ¥½¹Ì¡Í•±˜¤€´ø9½¹”è(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÈ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰AÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸™½ÈÍÑÕ‘•¹Ð€Üˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÌ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰=ÉÁ¡…¹•ÁÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€€€€±¥¹­•õ…±Í”°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÔ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰µ‰¥Õ½ÕÍ±ä½Ý¹••¹•É…Ñ•ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€¤(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€ÁÉ¥Ù…Ñ•}ÅÕ•ÍÑ¥½¸€ôÍ•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÈ¤(€€€€€€€€€€€…ÍÍ•ÉÐÁÉ¥Ù…Ñ•}ÅÕ•ÍÑ¥½¸¥Ì¹½Ð9½¹”(€€€€€€€€€€€ÁÉ¥Ù…Ñ•}ÅÕ•ÍÑ¥½¸¹Ñ½Á¥Œ€ô€‰AÉ¥Ù…Ñ”•¹•É…Ñ•‘¥µ•¹Í¥½¸ˆ(€€€€€€€€€€€ÁÉ¥Ù…Ñ•}ÅÕ•ÍÑ¥½¸¹ÍÕ‰Ñ½Á¥Œ€ô€‰MÑÕ‘•¹Ð€Ü½¹±äˆ(€€€€€€€€€€€ÁÉ¥Ù…Ñ•}ÅÕ•ÍÑ¥½¸¹½µµ…¹‘}Ý½É€ô€‰±…ÍÍ¥™äˆ(€€€€€€€€€€€¡…ÁÑ•È€ôÍ•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡ÕÉÉ¥Õ±Õµ¡…ÁÑ•È¤¤(€€€€€€€€€€€ÍÕ‰©•Ð€ôÍ•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡MÕ‰©•Ð¤¹Ý¡•É”¡MÕ‰©•Ð¹½‘”€ôô€ˆäØÄàˆ¤¤(€€€€€€€€€€€…ÍÍ•ÉÐ¡…ÁÑ•È¥Ì¹½Ð9½¹”…¹ÍÕ‰©•Ð¥Ì¹½Ð9½¹”(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€EÕ•ÍÑ¥½¹¡…ÁÑ•É5…ÁÁ¥¹œ (€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÈ°(€€€€€€€€€€€€€€€€€€€¡…ÁÑ•É}¥õ¡…ÁÑ•È¹¥°(€€€€€€€€€€€€€€€€€€€½¹™¥‘•¹”ôÄ¸À°(€€€€€€€€€€€€€€€€€€€É•Ù¥•Ý}ÍÑ…ÑÕÌô‰…ÁÁÉ½Ù•ˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€¤(€€€€€€€€€€€½Ñ¡•É}Á…Á•È€ôA…Á•È¡ÕÍ•É}¥ôà°ÍÕ‰©•Ñ}¥õÍÕ‰©•Ð¹¥°µ½‘”ô‰Ý•…­}ÍÁ½Ðˆ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡½Ñ¡•É}Á…Á•È¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€A…Á•ÉEÕ•ÍÑ¥½¸ (€€€€€€€€€€€€€€€€€€€Á…Á•É}¥õ½Ñ¡•É}Á…Á•È¹¥°(€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÔ°(€€€€€€€€€€€€€€€€€€€Á½Í¥Ñ¥½¸ôÄ°(€€€€€€€€€€€€€€€€€€€Í½ÕÉ•}ÑåÁ”ô‰…¥}•¹•É…Ñ•ˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€¤(€€€€€€€€€€€±•…å}‘¥…¹½ÍÑ¥Œ€ô¥…¹½ÍÑ¥Œ (€€€€€€€€€€€€€€€ÕÍ•É}¥ôà°(€€€€€€€€€€€€€€€ÍÕ‰©•Ñ}¥õÍÕ‰©•Ð¹¥°(€€€€€€€€€€€€€€€É…‘•}ÍÑ…”ô‰Lˆ°(€€€€€€€€€€€€€€€ÍÑ…Ñ”ô‰…Ñ¥Ù”ˆ°(€€€€€€€€€€€€€€€¥‘•µÁ½Ñ•¹å}­•äô‰±•…äµÁÉ¥Ù…Ñ”µÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡±•…å}‘¥…¹½ÍÑ¥Œ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€±•…å}‘¥…¹½ÍÑ¥}¥€ô±•…å}‘¥…¹½ÍÑ¥Œ¹¥(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡¥…¹½ÍÑ¥I•ÍÁ½¹Í”¡‘¥…¹½ÍÑ¥}¥õ±•…å}‘¥…¹½ÍÑ¥Œ¹¥°ÅÕ•ÍÑ¥½¹}¥ôÄÈ¤¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹½µµ¥Ð ¤((€€€€€€€½Ñ¡•É}µ…ÍÑ•Éä€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰Pˆ°(€€€€€€€€€€€€ˆ½µ…ÍÑ•Éä¼àýÍÕ‰©•ÐôäØÄàˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È à¤°(€€€€€€€€¤(€€€€€€€½Ý¹•É}µ…ÍÑ•Éä€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰Pˆ°(€€€€€€€€€€€€ˆ½µ…ÍÑ•Éä¼ÜýÍÕ‰©•ÐôäØÄàˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸ (€€€€€€€€€€€€‰AÉ¥Ù…Ñ”•¹•É…Ñ•‘¥µ•¹Í¥½¸ˆ°(€€€€€€€€€€€©Í½¸¹‘ÕµÁÌ¡½Ñ¡•É}µ…ÍÑ•Éä¹©Í½¸ ¥l‰•±±Ì‰t¤°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸ (€€€€€€€€€€€€‰AÉ¥Ù…Ñ”•¹•É…Ñ•‘¥µ•¹Í¥½¸ˆ°(€€€€€€€€€€€©Í½¸¹‘ÕµÁÌ¡½Ý¹•É}µ…ÍÑ•Éä¹©Í½¸ ¥l‰•±±Ì‰t¤°(€€€€€€€€¤((€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹Ì€ô±¥ÍÑ}ÅÕ•ÍÑ¥½¹Ì¡ÍÕ‰©•ÐôˆäØÄàˆ°±¥µ¥ÐôÄÀ°Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡mÅÕ•ÍÑ¥½¸¹¥™½ÈÅÕ•ÍÑ¥½¸¥¸ÅÕ•ÍÑ¥½¹Ít°lÄÅt¤((€€€€€€€‘¥…¹½ÍÑ¥Œ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½‘¥…¹½ÍÑ¥Ìˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÍÕ‰©•Ðˆè€ˆäØÄàˆ°€‰É…‘•}ÍÑ…”ˆè€‰Lˆ°€‰ÅÕ•ÍÑ¥½¹}±¥µ¥Ðˆè€ÄÁô°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡‘¥…¹½ÍÑ¥Œ¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÄ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡mÅÕ•ÍÑ¥½¹l‰¥‰t™½ÈÅÕ•ÍÑ¥½¸¥¸‘¥…¹½ÍÑ¥Œ¹©Í½¸ ¥l‰ÅÕ•ÍÑ¥½¹Ì‰ut°lÄÅt¤(€€€€€€€±•…å}‘¥…¹½ÍÑ¥Œ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€˜ˆ½‘¥…¹½ÍÑ¥Ì½í±•…å}‘¥…¹½ÍÑ¥}¥‘ô½ÍÕ‰µ¥ÐýÕÍ•É}¥ôàˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È à¤°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•…å}‘¥…¹½ÍÑ¥Œ¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÀ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•…å}‘¥…¹½ÍÑ¥Œ¹©Í½¸ ¥l‰ÅÕ•ÍÑ¥½¹Ì‰t°mt¤((€€€€€€€½Ý¹•É}…ÑÑ•µÁÐ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½…ÑÑ•µÁÑÌˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÅÕ•ÍÑ¥½¹}¥ˆè€ÄÈ°€‰ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐˆè€‰5ä…¹ÍÝ•È‰ô°(€€€€€€€€¤(€€€€€€€½Ñ¡•É}…ÑÑ•µÁÐ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½…ÑÑ•µÁÑÌˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È à¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€à°€‰ÅÕ•ÍÑ¥½¹}¥ˆè€ÄÈ°€‰ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐˆè€‰QÉäÑ¼É•…¥Ð‰ô°(€€€€€€€€¤(€€€€€€€½ÉÁ¡…¹}…ÑÑ•µÁÐ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½…ÑÑ•µÁÑÌˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÅÕ•ÍÑ¥½¹}¥ˆè€ÄÌ°€‰ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐˆè€‰9¼½Ý¹•È‰ô°(€€€€€€€€¤(€€€€€€€…µ‰¥Õ½ÕÍ}½Ý¹•É}…ÑÑ•µÁÐ€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½…ÑÑ•µÁÑÌˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÅÕ•ÍÑ¥½¹}¥ˆè€ÄÔ°€‰ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐˆè€‰µ‰¥Õ½ÕÌ½Ý¹•È‰ô°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Ý¹•É}…ÑÑ•µÁÐ¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÄ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Ñ¡•É}…ÑÑ•µÁÐ¹ÍÑ…ÑÕÍ}½‘”°€ÐÀÐ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½ÉÁ¡…¹}…ÑÑ•µÁÐ¹ÍÑ…ÑÕÍ}½‘”°€ÐÀÐ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…µ‰¥Õ½ÕÍ}½Ý¹•É}…ÑÑ•µÁÐ¹ÍÑ…ÑÕÍ}½‘”°€ÐÀÐ¤((€€€€€€€½Ý¹•É}Í•ÍÍ¥½¸€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½ÁÉ…Ñ¥”½Í•ÍÍ¥½¹Ìˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÍÕ‰©•Ðˆè€ˆäØÄàˆ°€‰ÅÕ•ÍÑ¥½¹}¥‘ÌˆèlÄÉuô°(€€€€€€€€¤(€€€€€€€½Ñ¡•É}Í•ÍÍ¥½¸€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½ÁÉ…Ñ¥”½Í•ÍÍ¥½¹Ìˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È à¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€à°€‰ÍÕ‰©•Ðˆè€ˆäØÄàˆ°€‰ÅÕ•ÍÑ¥½¹}¥‘ÌˆèlÄÉuô°(€€€€€€€€¤(€€€€€€€½ÉÁ¡…¹}Í•ÍÍ¥½¸€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½ÁÉ…Ñ¥”½Í•ÍÍ¥½¹Ìˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÍÕ‰©•Ðˆè€ˆäØÄàˆ°€‰ÅÕ•ÍÑ¥½¹}¥‘ÌˆèlÄÍuô°(€€€€€€€€¤(€€€€€€€…µ‰¥Õ½ÕÍ}½Ý¹•É}Í•ÍÍ¥½¸€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰A=MPˆ°(€€€€€€€€€€€€ˆ½ÁÉ…Ñ¥”½Í•ÍÍ¥½¹Ìˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰ÕÍ•É}¥ˆè€Ü°€‰ÍÕ‰©•Ðˆè€ˆäØÄàˆ°€‰ÅÕ•ÍÑ¥½¹}¥‘ÌˆèlÄÕuô°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Ý¹•É}Í•ÍÍ¥½¸¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÄ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Ñ¡•É}Í•ÍÍ¥½¸¹ÍÑ…ÑÕÍ}½‘”°€ÐÈÈ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½ÉÁ¡…¹}Í•ÍÍ¥½¸¹ÍÑ…ÑÕÍ}½‘”°€ÐÈÈ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡…µ‰¥Õ½ÕÍ}½Ý¹•É}Í•ÍÍ¥½¸¹ÍÑ…ÑÕÍ}½‘”°€ÐÈÈ¤((€€€‘•˜Ñ•ÍÑ}ÁÉ¥Ù…å}•áÁ½ÉÑ}¥¹±Õ‘•Í}½¹±å}Ñ¡•}½Ý¹•ÉÍ}•¹•É…Ñ•‘}½¹Ñ•¹Ð¡Í•±˜¤€´ø9½¹”è(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÈ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰AÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸™½ÈÍÑÕ‘•¹Ð€Üˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôà°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÌ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰AÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸™½ÈÍÑÕ‘•¹Ð€àˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÐ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰µ‰¥Õ½ÕÍ±ä½Ý¹•ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€¤(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€ÍÕ‰©•Ð€ôÍ•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡MÕ‰©•Ð¤¹Ý¡•É”¡MÕ‰©•Ð¹½‘”€ôô€ˆäØÄàˆ¤¤(€€€€€€€€€€€…ÍÍ•ÉÐÍÕ‰©•Ð¥Ì¹½Ð9½¹”(€€€€€€€€€€€½Ñ¡•É}Á…Á•È€ôA…Á•È¡ÕÍ•É}¥ôà°ÍÕ‰©•Ñ}¥õÍÕ‰©•Ð¹¥°µ½‘”ô‰Ý•…­}ÍÁ½Ðˆ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡½Ñ¡•É}Á…Á•È¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€A…Á•ÉEÕ•ÍÑ¥½¸ (€€€€€€€€€€€€€€€€€€€Á…Á•É}¥õ½Ñ¡•É}Á…Á•È¹¥°(€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÐ°(€€€€€€€€€€€€€€€€€€€Á½Í¥Ñ¥½¸ôÄ°(€€€€€€€€€€€€€€€€€€€Í½ÕÉ•}ÑåÁ”ô‰…¥}•¹•É…Ñ•ˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹½µµ¥Ð ¤((€€€€€€€É•ÍÁ½¹Í”€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰Pˆ°(€€€€€€€€€€€€ˆ½ÁÉ¥Ù…ä½•áÁ½ÉÐˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É•ÍÁ½¹Í”¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÀ¤(€€€€€€€Á…Á•É}ÅÕ•ÍÑ¥½¹Ì€ôÉ•ÍÁ½¹Í”¹©Í½¸ ¥l‰É•½É‘Ì‰ul‰Á…Á•É}ÅÕ•ÍÑ¥½¹Ì‰t(€€€€€€€•áÁ½ÉÑ•‘}‰å}ÅÕ•ÍÑ¥½¸€ôíÉ½Ýl‰ÅÕ•ÍÑ¥½¹}¥‰tèÉ½Ü™½ÈÉ½Ü¥¸Á…Á•É}ÅÕ•ÍÑ¥½¹Íô(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡Í•Ð¡•áÁ½ÉÑ•‘}‰å}ÅÕ•ÍÑ¥½¸¤°ìÄÈ°€ÄÑô¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€•áÁ½ÉÑ•‘}‰å}ÅÕ•ÍÑ¥½¹lÄÉul‰•¹•É…Ñ•‘}½¹Ñ•¹Ð‰t°(€€€€€€€€€€€ì(€€€€€€€€€€€€€€€€‰É…Ý}Ñ•áÐˆè€‰AÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸™½ÈÍÑÕ‘•¹Ð€Üˆ°(€€€€€€€€€€€€€€€€‰µ…É­Ìˆè€È°(€€€€€€€€€€€€€€€€‰µ…É­}Í¡•µ•}Á½¥¹ÑÌˆèl(€€€€€€€€€€€€€€€€€€€ì‰Á½¥¹Ñ}Ñ•áÐˆè€‰AÉ¥Ù…Ñ”µ…É¬Á½¥¹Ð™½È€Üˆ°€‰µ…É­Í}Ù…±Õ”ˆè€Åô(€€€€€€€€€€€€€€€t°(€€€€€€€€€€€ô°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½¹”¡•áÁ½ÉÑ•‘}‰å}ÅÕ•ÍÑ¥½¹lÄÑul‰•¹•É…Ñ•‘}½¹Ñ•¹Ð‰t¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€•áÁ½ÉÑ•‘}‰å}ÅÕ•ÍÑ¥½¹lÄÑul‰•¹•É…Ñ•‘}½¹Ñ•¹Ñ}ÍÑ…ÑÕÌ‰t°(€€€€€€€€€€€€‰Õ¹…Ù…¥±…‰±•}…µ‰¥Õ½ÕÍ}½É}µ¥ÍÍ¥¹}½Ý¹•Èˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸ ‰AÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸™½ÈÍÑÕ‘•¹Ð€àˆ°©Í½¸¹‘ÕµÁÌ¡Á…Á•É}ÅÕ•ÍÑ¥½¹Ì¤¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ9½Ñ%¸ ‰AÉ¥Ù…Ñ”µ…É¬Á½¥¹Ð™½È€àˆ°©Í½¸¹‘ÕµÁÌ¡Á…Á•É}ÅÕ•ÍÑ¥½¹Ì¤¤((€€€‘•˜Ñ•ÍÑ}…½Õ¹Ñ}‘•±•Ñ¥½¹}•É…Í•Í}½Ý¹•‘}•¹•É…Ñ•‘}½¹Ñ•¹Ñ}…¹‘}É•‘…ÑÍ}É•™•É•¹•‘}½¹Ñ•¹Ð¡Í•±˜¤€´ø9½¹”è(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÈ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰•±•Ñ”Ñ¡¥ÌÁÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôà°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÌ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰-••ÀÑ¡”½Ñ¡•ÈÍÑÕ‘•¹ÐÌÁÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€¤(€€€€€€€Í•±˜¹}Í••‘}•¹•É…Ñ•‘}ÅÕ•ÍÑ¥½¸ (€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÐ°(€€€€€€€€€€€É…Ý}Ñ•áÐô‰I•‘…ÐÑ¡¥ÌÉ½ÍÌµÉ•™•É•¹•ÅÕ•ÍÑ¥½¸ˆ°(€€€€€€€€¤(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€ÑÑ•µÁÐ (€€€€€€€€€€€€€€€€€€€ÕÍ•É}¥ôà°(€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÐ°(€€€€€€€€€€€€€€€€€€€ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐô‰1•…äÉ½ÍÌµ½Ý¹•È…¹ÍÝ•Èˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹½µµ¥Ð ¤((€€€€€€€É•ÍÁ½¹Í”€ô}É•ÅÕ•ÍÐ (€€€€€€€€€€€Í•±˜¹…ÁÀ°(€€€€€€€€€€€€‰1Qˆ°(€€€€€€€€€€€€ˆ½ÁÉ¥Ù…ä½…½Õ¹Ðˆ°(€€€€€€€€€€€¡•…‘•ÉÌõÍ•±˜¹}¡•…‘•ÉÍ}™½È Ü¤°(€€€€€€€€€€€©Í½¹}‰½‘äõì‰½¹™¥Éµ…Ñ¥½¸ˆè€‰1Q5dQ‰ô°(€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É•ÍÁ½¹Í”¹ÍÑ…ÑÕÍ}½‘”°€ÈÀÐ¤((€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½¹”¡Í•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÈ¤¤(€€€€€€€€€€€½Ñ¡•É}½Ý¹•É}ÅÕ•ÍÑ¥½¸€ôÍ•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÌ¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½Ñ9½¹”¡½Ñ¡•É}½Ý¹•É}ÅÕ•ÍÑ¥½¸¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡½Ñ¡•É}½Ý¹•É}ÅÕ•ÍÑ¥½¸¹É…Ý}Ñ•áÐ°€‰-••ÀÑ¡”½Ñ¡•ÈÍÑÕ‘•¹ÐÌÁÉ¥Ù…Ñ”ÅÕ•ÍÑ¥½¸ˆ¤(€€€€€€€€€€€É•™•É•¹•‘}ÅÕ•ÍÑ¥½¸€ôÍ•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÐ¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½Ñ9½¹”¡É•™•É•¹•‘}ÅÕ•ÍÑ¥½¸¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É•™•É•¹•‘}ÅÕ•ÍÑ¥½¸¹É…Ý}Ñ•áÐ°€ˆˆ¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½¹”¡É•™•É•¹•‘}ÅÕ•ÍÑ¥½¸¹Ñ½Á¥Œ¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%Í9½¹”¡É•™•É•¹•‘}ÅÕ•ÍÑ¥½¸¹µ…É­Ì¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡5…É­M¡•µ•A½¥¹Ð¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€5…É­M¡•µ•A½¥¹Ð¹ÅÕ•ÍÑ¥½¹}¥¹¥¹|¡lÄÈ°€ÄÑt¤(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€À°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½Õ¹Ð ¤¤¹Í•±•Ñ}™É½´¡5…É­M¡•µ•A½¥¹Ð¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€5…É­M¡•µ•A½¥¹Ð¹ÅÕ•ÍÑ¥½¹}¥€ôô€ÄÌ(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€Ä°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡Í•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÄ¤¹É…Ý}Ñ•áÐ°€‰áÁ±…¥¸½¹”‰•¹•™¥Ð½˜…¡”µ•µ½Éä¸ˆ¤((€€€‘•˜Ñ•ÍÑ}•µ¥¹¥}É…‘¥¹}Ù…±¥‘…Ñ•Í}©Í½¹}…¹‘}É•ÑÉ¥•Í}½¹”¡Í•±˜¤€´ø9½¹”è(€€€€€€€µ½‘•°€ô}…­••µ¥¹¥5½‘•° (€€€€€€€€€€€l(€€€€€€€€€€€€€€€€‰¹½Ð©Í½¸ˆ°(€€€€€€€€€€€€€€€€©Í½¹q¹ì‰Á½¥¹ÑÍ}¡¥Ðˆél‰UÍ•Ì„…¡”‰t°‰Á½¥¹ÑÍ}µ¥ÍÍ•ˆémt°‰µ…É­Í}•…É¹•ˆèÄ°‰™••‘‰…¬ˆè‰½ÉÉ•Ð¸‰õq¹€œ°(€€€€€€€€€€€t(€€€€€€€€¤((€€€€€€€É•ÍÕ±Ð€ôÉ…‘•}…¹ÍÝ•È (€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}Ñ•áÐô‰áÁ±…¥¸…¡”µ•µ½Éä¸ˆ°(€€€€€€€€€€€µ…É­}Í¡•µ•}Á½¥¹ÑÌõmì‰Á½¥¹Ñ}Ñ•áÐˆè€‰UÍ•Ì„…¡”ˆ°€‰µ…É­Í}Ù…±Õ”ˆè€Åõt°(€€€€€€€€€€€ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐô‰%ÐÍÑ½É•Ì™É•ÅÕ•¹Ñ±äÕÍ•‘…Ñ„¸ˆ°(€€€€€€€€€€€µ…É­Í}Á½ÍÍ¥‰±”ôÈ°(€€€€€€€€€€€µ½‘•°õµ½‘•°°(€€€€€€€€¤((€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É•ÍÕ±Ð¹µ…É­Í}•…É¹•°€Ä¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•¸¡µ½‘•°¹ÁÉ½µÁÑÌ¤°€È¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑ%¸ ‰UÍ•Ì„…¡”ˆ°µ½‘•°¹ÁÉ½µÁÑÍlÁt¤((€€€‘•˜Ñ•ÍÑ}ÍÕ‰©•Ñ}…¹‘}™¥±Ñ•É•‘}ÅÕ•ÍÑ¥½¹}É•…‘Ì¡Í•±˜¤€´ø9½¹”è(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€ÍÕ‰©•ÑÌ€ô±¥ÍÑ}ÍÕ‰©•ÑÌ¡Í•ÍÍ¥½¸¤(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹Ì€ô±¥ÍÑ}ÅÕ•ÍÑ¥½¹Ì (€€€€€€€€€€€€€€€ÍÕ‰©•ÐôˆäØÄàˆ°(€€€€€€€€€€€€€€€Ñ½Á¥Œô‰…Ñ„É•ÁÉ•Í•¹Ñ…Ñ¥½¸ˆ°(€€€€€€€€€€€€€€€½µµ…¹‘}Ý½Éô‰áÁ±…¥¸ˆ°(€€€€€€€€€€€€€€€±¥µ¥ÐôÄÀ°(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸°(€€€€€€€€€€€€¤((€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡ÍÕ‰©•ÑÍlÁt¹½‘”°€ˆäØÄàˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡ÅÕ•ÍÑ¥½¹ÍlÁt¹¥°€ÄÄ¤((€€€‘•˜Ñ•ÍÑ}¡…ÁÑ•É}™¥±Ñ•É}ÕÍ•Í}½¹±å}…ÁÁÉ½Ù•‘}µ…ÁÁ¥¹œ¡Í•±˜¤€´ø9½¹”è(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€¡…ÁÑ•È€ôÍ•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡ÕÉÉ¥Õ±Õµ¡…ÁÑ•È¤¤(€€€€€€€€€€€…ÍÍ•ÉÐ¡…ÁÑ•È¥Ì¹½Ð9½¹”(€€€€€€€€€€€ÅÕ•ÍÑ¥½¹Ì€ô±¥ÍÑ}ÅÕ•ÍÑ¥½¹Ì (€€€€€€€€€€€€€€€ÍÕ‰©•ÐôˆäØÄàˆ°(€€€€€€€€€€€€€€€¡…ÁÑ•É}¥õ¡…ÁÑ•È¹¥°(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸°(€€€€€€€€€€€€¤((€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡mÅÕ•ÍÑ¥½¸¹¥™½ÈÅÕ•ÍÑ¥½¸¥¸ÅÕ•ÍÑ¥½¹Ít°lÄÅt¤((€€€‘•˜Ñ•ÍÑ}…ÑÑ•µÁÑ}¥Í}ÍÑ½É•‘}…¹‘}ÕÁ‘…Ñ•Í}µ…ÍÑ•Éä¡Í•±˜¤€´ø9½¹”è(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€É•ÍÕ±Ð€ôÉ•…Ñ•}…ÑÑ•µÁÐ (€€€€€€€€€€€€€€€ÑÑ•µÁÑÉ•…Ñ” (€€€€€€€€€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÄ°(€€€€€€€€€€€€€€€€€€€ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐô‰%ÐÍÑ½É•Ì™É•ÅÕ•¹Ñ±äÕÍ•‘…Ñ„¸ˆ°(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€Í•±˜¹É•ÅÕ•ÍÐ°(€€€€€€€€€€€€€€€…ÕÑ õÍ•±˜¹…ÕÑ °(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸°(€€€€€€€€€€€€¤((€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É•ÍÕ±Ð¹µ…É­Í}•…É¹•°€Ä¸À¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑQÉÕ”¡É•ÍÕ±Ð¹µ…ÍÑ•Éå}ÕÁ‘…Ñ•¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•¸¡Í•±˜¹É…‘•È¹…±±Ì¤°€Ä¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…° (€€€€€€€€€€€Í•±˜¹É…‘•È¹…±±ÍlÁul‰µ…É­}Í¡•µ•}Á½¥¹ÑÌ‰t°(€€€€€€€€€€€mì‰Á½¥¹Ñ}Ñ•áÐˆè€‰UÍ•Ì„…¡”ˆ°€‰µ…É­Í}Ù…±Õ”ˆè€Åõt°(€€€€€€€€¤((€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€µ…ÍÑ•Éä€ô•Ñ}µ…ÍÑ•Éä¡ÕÍ•É}¥ôÜ°ÍÕ‰©•ÐôˆäØÄàˆ°…ÕÑ õÍ•±˜¹…ÕÑ °Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸¤(€€€€€€€•±°€ôµ…ÍÑ•Éä¹•±±ÍlÁt(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡•±°¹Ñ½Á¥Œ°€‰…Ñ„É•ÁÉ•Í•¹Ñ…Ñ¥½¸ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡•±°¹½µµ…¹‘}Ý½É°€‰áÁ±…¥¸ˆ¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡•±°¹Í½É”°€À¸Ô¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑQÉÕ”¡•±°¹¡…Í}•Ù¥‘•¹”¤((€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•¸¡Í•ÍÍ¥½¸¹Í…±…ÉÌ¡Í•±•Ð¡ÑÑ•µÁÐ¤¤¹…±° ¤¤°€Ä¤(€€€€€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡±•¸¡Í•ÍÍ¥½¸¹Í…±…ÉÌ¡Í•±•Ð¡5…ÍÑ•Éä¤¤¹…±° ¤¤°€Ä¤((€€€‘•˜Ñ•ÍÑ}…ÑÑ•µÁÑ}É•©•ÑÍ}µ¥ÍÍ¥¹}µ…É­}Í¡•µ”¡Í•±˜¤€´ø9½¹”è(€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€ÅÕ•ÍÑ¥½¸€ôÍ•ÍÍ¥½¸¹•Ð¡EÕ•ÍÑ¥½¸°€ÄÄ¤(€€€€€€€€€€€…ÍÍ•ÉÐÅÕ•ÍÑ¥½¸¥Ì¹½Ð9½¹”(€€€€€€€€€€€ÅÕ•ÍÑ¥½¸¹µ…É­}Í¡•µ•}Á½¥¹ÑÌ¹±•…È ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹½µµ¥Ð ¤((€€€€€€€Ý¥Ñ M•ÍÍ¥½¸¡Í•±˜¹•¹¥¹”¤…ÌÍ•ÍÍ¥½¸è(€€€€€€€€€€€Ý¥Ñ Í•±˜¹…ÍÍ•ÉÑI…¥Í•Ì¡!QQAá•ÁÑ¥½¸¤…ÌÉ…¥Í•è(€€€€€€€€€€€€€€€É•…Ñ•}…ÑÑ•µÁÐ (€€€€€€€€€€€€€€€€€€€ÑÑ•µÁÑÉ•…Ñ” (€€€€€€€€€€€€€€€€€€€€€€€ÕÍ•É}¥ôÜ°(€€€€€€€€€€€€€€€€€€€€€€€ÅÕ•ÍÑ¥½¹}¥ôÄÄ°(€€€€€€€€€€€€€€€€€€€€€€€ÍÕ‰µ¥ÑÑ•‘}…¹ÍÝ•É}Ñ•áÐô‰…¹ÍÝ•Èˆ°(€€€€€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€€€€Í•±˜¹É•ÅÕ•ÍÐ°(€€€€€€€€€€€€€€€€€€€…ÕÑ õÍ•±˜¹…ÕÑ °(€€€€€€€€€€€€€€€€€€€Í•ÍÍ¥½¸õÍ•ÍÍ¥½¸°(€€€€€€€€€€€€€€€€¤(€€€€€€€Í•±˜¹…ÍÍ•ÉÑÅÕ…°¡É…¥Í•¹•á•ÁÑ¥½¸¹ÍÑ…ÑÕÍ}½‘”°€ÐÈÈ¤(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€Õ¹¥ÑÑ•ÍÐ¹µ…¥¸ ¤(