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
    MistakeDraftSave,
    MistakeQueueItem,
    MistakeQueueResponse,
    MistakeReviewConfirm,
    MistakeReviewStateUpdate,
    MistakeRevealResponse,
    MistakeRetryCreate,
    MistakeRetryResponse,
    MistakeRevealedRetry,
    MistakeSessionCreate,
    MistakeSessionItem,
    MistakeSessionResponse,
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
    MistakeReview,
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
MISTAKE_REVIEW_SUBJECT = "9618"


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


def _is_recorded_mistake(attempt: Attempt) -> bool:
    return (
        attempt.retry_of_attempt_id is None
        and attempt.grading_status in {"graded", "corrected"}
        and attempt.marks_earned is not None
        and attempt.marks_possible is not None
        and attempt.marks_possible > 0
        and 0 <= attempt.marks_earned < attempt.marks_possible
    )


def _mistake_queue_response(
    session: Session,
    *,
    user: User,
    subject: Subject,
) -> MistakeQueueResponse:
    attempts = session.scalars(
        select(Attempt)
        .join(Question, Question.id == Attempt.question_id)
        .where(
            Attempt.user_id == user.id,
            Attempt.retry_of_attempt_id.is_(None),
            Question.subject_id == subject.id,
        )
        .order_by(Attempt.attempted_at.desc(), Attempt.id.desc())
    ).all()
    attempt_ids = [attempt.id for attempt in attempts]
    reviews_by_attempt = {
        review.original_attempt_id: review
        for review in session.scalars(
            select(MistakeReview).where(
                MistakeReview.user_id == user.id,
                MistakeReview.original_attempt_id.in_(attempt_ids),
            )
        ).all()
    } if attempt_ids else {}
    retry_counts: dict[int, int] = {}
    if attempt_ids:
        for original_attempt_id in session.scalars(
            select(Attempt.retry_of_attempt_id).where(Attempt.retry_of_attempt_id.in_(attempt_ids))
        ).all():
            if original_attempt_id is not None:
                retry_counts[original_attempt_id] = retry_counts.get(original_attempt_id, 0) + 1

    items: list[MistakeQueueItem] = []
    seen_question_ids: set[int] = set()
    for attempt in attempts:
        review = reviews_by_attempt.get(attempt.id)
        scored_miss = _is_recorded_mistake(attempt)
        user_confirmed = review is not None and review.source == "user_confirmed"
        if review is not None and review.state == "resolved":
            continue
        if not user_confirmed and not scored_miss:
            continue
        if attempt.question_id in seen_question_ids:
            continue
        question = session.get(Question, attempt.question_id)
        if question is None:
            continue
        _require_generated_question_owner(session, question, user.id)
        seen_question_ids.add(attempt.question_id)
        items.append(
            MistakeQueueItem(
                review_id=review.id if review is not None else None,
                original_attempt_id=attempt.id,
                source=review.source if review is not None else "scored_miss",
                state=review.state if review is not None else "open",
                attempted_at=attempt.attempted_at,
                retry_count=retry_counts.get(attempt.id, 0),
                question=_question_response(question),
            )
        )
    return MistakeQueueResponse(
        user_id=user.id,
        subject=_subject_response(subject),
        items=items,
    )


def _mistake_session_response(session: Session, practice: PracticeSession) -> MistakeSessionResponse:
    answers = sorted(practice.answers, key=lambda answer: answer.id)
    original_attempt_ids = [answer.original_attempt_id for answer in answers if answer.original_attempt_id]
    review_by_attempt = {
        review.original_attempt_id: review
        for review in session.scalars(
            select(MistakeReview).where(
                MistakeReview.user_id == practice.user_id,
                MistakeReview.original_attempt_id.in_(original_attempt_ids),
            )
        ).all()
    } if original_attempt_ids else {}
    retry_counts: dict[int, int] = {}
    if original_attempt_ids:
        for original_attempt_id in session.scalars(
            select(Attempt.retry_of_attempt_id).where(Attempt.retry_of_attempt_id.in_(original_attempt_ids))
        ).all():
            if original_attempt_id is not None:
                retry_counts[original_attempt_id] = retry_counts.get(original_attempt_id, 0) + 1

    items: list[MistakeSessionItem] = []
    for answer in answers:
        original_attempt_id = answer.original_attempt_id
        if original_attempt_id is None:
            continue
        review = review_by_attempt.get(original_attempt_id)
        question = session.get(Question, answer.question_id)
        if review is None or question is None:
            continue
        _require_generated_question_owner(session, question, practice.user_id)
        retry = session.get(Attempt, answer.attempt_id) if answer.attempt_id is not None else None
        items.append(
            MistakeSessionItem(
                review_id=review.id,
                original_attempt_id=original_attempt_id,
                review_state=review.state,
                source=review.source,
                question=_question_response(question),
                answer_text=answer.answer_text,
                answer_status=answer.status,
                retry_attempt_id=answer.attempt_id if answer.status == "submitted" else None,
                retry_self_assessment=retry.self_assessment if retry is not None else None,
                retry_count=retry_counts.get(original_attempt_id, 0),
            )
        )
    return MistakeSessionResponse(
        id=practice.id,
        user_id=practice.user_id,
        subject=_subject_response(practice.subject),
        state=practice.state,
        items=items,
        completed_count=sum(item.retry_attempt_id is not None for item in items),
        total_count=len(items),
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
            or generated_question_owner_ids(session, response.question.id) == {diagnostic.user_id}
        ],
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
            return _diagnostic_response(session, existing)

    query = (
        select(Question)
        .join(QuestionChapterMapping, QuestionChapterMapping.question_id == Question.id)
        .join(CurriculumChapter, CurriculumChapter.id == QuestionChapterMapping.chapter_id)
        .where(
            Question.subject_id == db_subject.id,
            Question.paper != "ai_generated",
            QuestionChapterMapping.review_status == "approved",
            CurriculumChapter.review_status == "approved",
            ~select(PaperQuestion.question_id)
            .where(
                PaperQuestion.question_id == Question.id,
                PaperQuestion.source_type == "ai_generated",
            )
            .exists(),
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
    return _diagnostic_response(session, diagnostic)


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
    user = _require_user_access(session, auth, diagnostic.user_id)
    if payload.user_id != user.id:
        raise HTTPException(status_code=403, detail="You may only save answers for your own diagnostic")
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
    _require_generated_question_owner(session, response.question, user.id)
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
    return _diagnostic_response(session, diagnostic)


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
    missing.extend(
        question_id
        for question_id, question in question_by_id.items()
        if is_generated_question(session, question)
        and generated_question_owner_ids(session, question_id) != {user.id}
    )
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
    user = _require_user_access(session, auth, practice.user_id)
    if payload.user_id != user.id:
        raise HTTPException(status_code=403, detail="You may only save answers for your own practice session")
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


@app.get("/mistakes/queue/{user_id}", response_model=MistakeQueueResponse)
def get_mistake_queue(
    user_id: int,
    subject: str = Query(min_length=1, max_length=16),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeQueueResponse:
    user = _require_user_access(session, auth, user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")
    if db_subject.code != MISTAKE_REVIEW_SUBJECT:
        raise HTTPException(status_code=422, detail=f"Mistake review is currently limited to subject {MISTAKE_REVIEW_SUBJECT}")
    return _mistake_queue_response(session, user=user, subject=db_subject)


@app.post("/mistakes/reviews/confirm", response_model=MistakeQueueItem, status_code=status.HTTP_201_CREATED)
def confirm_mistake_for_review(
    payload: MistakeReviewConfirm,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeQueueItem:
    user = _require_user_access(session, auth, payload.user_id)
    attempt = session.get(Attempt, payload.attempt_id)
    if attempt is None or attempt.user_id != user.id or attempt.retry_of_attempt_id is not None:
        raise HTTPException(status_code=404, detail="Original attempt was not found")
    question = session.get(Question, attempt.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question was not found")
    if question.subject.code != MISTAKE_REVIEW_SUBJECT:
        raise HTTPException(status_code=422, detail=f"Mistake review is currently limited to subject {MISTAKE_REVIEW_SUBJECT}")
    _require_generated_question_owner(session, question, user.id)

    review = session.scalar(
        select(MistakeReview).where(
            MistakeReview.user_id == user.id,
            MistakeReview.original_attempt_id == attempt.id,
        )
    )
    if review is None:
        review = MistakeReview(
            user_id=user.id,
            original_attempt_id=attempt.id,
            source="user_confirmed",
            state="open",
            updated_at=datetime.now(timezone.utc),
        )
        session.add(review)
        session.flush()
    elif review.state == "resolved":
        raise HTTPException(status_code=409, detail="Reopen this resolved review explicitly before adding it again")

    queue = _mistake_queue_response(
        session,
        user=user,
        subject=question.subject,
    )
    item = next((candidate for candidate in queue.items if candidate.original_attempt_id == attempt.id), None)
    if item is None:
        session.rollback()
        raise HTTPException(status_code=409, detail="This attempt is already superseded by a newer review for the question")
    session.commit()
    return item


@app.post("/mistakes/sessions", response_model=MistakeSessionResponse, status_code=status.HTTP_201_CREATED)
def create_mistake_review_session(
    payload: MistakeSessionCreate,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeSessionResponse:
    user = _require_user_access(session, auth, payload.user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == payload.subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {payload.subject} was not found")
    if db_subject.code != MISTAKE_REVIEW_SUBJECT:
        raise HTTPException(status_code=422, detail=f"Mistake review is currently limited to subject {MISTAKE_REVIEW_SUBJECT}")

    attempt_ids = list(dict.fromkeys(payload.attempt_ids))
    existing = session.scalar(
        select(PracticeSession).where(
            PracticeSession.user_id == user.id,
            PracticeSession.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.session_type != "mistake_review" or existing.subject_id != db_subject.id:
            raise HTTPException(status_code=409, detail="This idempotency key belongs to another session")
        existing_attempt_ids = {answer.original_attempt_id for answer in existing.answers}
        if existing_attempt_ids != set(attempt_ids):
            raise HTTPException(status_code=409, detail="This idempotency key was used for a different review queue")
        return _mistake_session_response(session, existing)

    attempts = list(
        session.scalars(
            select(Attempt)
            .join(Question, Question.id == Attempt.question_id)
            .where(
                Attempt.id.in_(attempt_ids),
                Attempt.user_id == user.id,
                Attempt.retry_of_attempt_id.is_(None),
                Question.subject_id == db_subject.id,
            )
        ).all()
    )
    attempts_by_id = {attempt.id: attempt for attempt in attempts}
    if len(attempts_by_id) != len(attempt_ids):
        raise HTTPException(status_code=404, detail="One or more original attempts are unavailable")
    if len({attempt.question_id for attempt in attempts}) != len(attempts):
        raise HTTPException(status_code=422, detail="Choose at most one original attempt per question in a session")
    attempts = [attempts_by_id[attempt_id] for attempt_id in attempt_ids]

    reviews_by_attempt = {
        review.original_attempt_id: review
        for review in session.scalars(
            select(MistakeReview).where(
                MistakeReview.user_id == user.id,
                MistakeReview.original_attempt_id.in_(attempt_ids),
            )
        ).all()
    }
    for attempt in attempts:
        review = reviews_by_attempt.get(attempt.id)
        if review is not None and review.state == "resolved":
            raise HTTPException(status_code=409, detail="Reopen a resolved review before starting it again")
        if review is None and not _is_recorded_mistake(attempt):
            raise HTTPException(status_code=422, detail="Only a recorded miss or an explicitly confirmed attempt can be reviewed")
        question = session.get(Question, attempt.question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="Question was not found")
        _require_generated_question_owner(session, question, user.id)
        if review is None:
            review = MistakeReview(
                user_id=user.id,
                original_attempt_id=attempt.id,
                source="scored_miss",
                state="open",
                updated_at=datetime.now(timezone.utc),
            )
            session.add(review)
            reviews_by_attempt[attempt.id] = review

    active_session_ids = select(PracticeSession.id).where(
        PracticeSession.user_id == user.id,
        PracticeSession.session_type == "mistake_review",
        PracticeSession.state.in_({"draft", "active"}),
    )
    already_active = session.scalar(
        select(PracticeAnswer.original_attempt_id)
        .where(
            PracticeAnswer.session_id.in_(active_session_ids),
            PracticeAnswer.original_attempt_id.in_(attempt_ids),
        )
        .limit(1)
    )
    if already_active is not None:
        raise HTTPException(status_code=409, detail="Resume the active session before starting another")

    now = datetime.now(timezone.utc)
    practice = PracticeSession(
        user_id=user.id,
        subject_id=db_subject.id,
        state="active",
        session_type="mistake_review",
        idempotency_key=payload.idempotency_key,
        created_at=now,
        started_at=now,
    )
    session.add(practice)
    session.flush()
    practice.answers = [
        PracticeAnswer(question_id=attempt.question_id, original_attempt_id=attempt.id)
        for attempt in attempts
    ]
    session.commit()
    return _mistake_session_response(session, practice)


@app.get("/mistakes/sessions/active/{user_id}", response_model=MistakeSessionResponse | None)
def get_active_mistake_review_session(
    user_id: int,
    subject: str = Query(min_length=1, max_length=16),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeSessionResponse | None:
    user = _require_user_access(session, auth, user_id)
    db_subject = session.scalar(select(Subject).where(Subject.code == subject.strip()))
    if db_subject is None:
        raise HTTPException(status_code=404, detail=f"Subject {subject} was not found")
    if db_subject.code != MISTAKE_REVIEW_SUBJECT:
        raise HTTPException(status_code=422, detail=f"Mistake review is currently limited to subject {MISTAKE_REVIEW_SUBJECT}")
    practice = session.scalar(
        select(PracticeSession)
        .where(
            PracticeSession.user_id == user.id,
            PracticeSession.subject_id == db_subject.id,
            PracticeSession.session_type == "mistake_review",
            PracticeSession.state.in_({"draft", "active"}),
        )
        .order_by(PracticeSession.created_at.desc(), PracticeSession.id.desc())
        .limit(1)
    )
    return _mistake_session_response(session, practice) if practice is not None else None


@app.get("/mistakes/sessions/{session_id}", response_model=MistakeSessionResponse)
def get_mistake_review_session(
    session_id: int,
    user_id: int = Query(ge=1),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeSessionResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None or practice.session_type != "mistake_review":
        raise HTTPException(status_code=404, detail="Mistake review session was not found")
    _require_user_access(session, auth, user_id)
    if practice.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only access your own mistake review session")
    return _mistake_session_response(session, practice)


@app.put("/mistakes/sessions/{session_id}/answers/{review_id}", response_model=MistakeSessionResponse)
def save_mistake_review_draft(
    session_id: int,
    review_id: int,
    payload: MistakeDraftSave,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeSessionResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None or practice.session_type != "mistake_review":
        raise HTTPException(status_code=404, detail="Mistake review session was not found")
    user = _require_user_access(session, auth, practice.user_id)
    if payload.user_id != user.id:
        raise HTTPException(status_code=403, detail="You may only save your own review answer")
    if practice.state not in {"draft", "active"}:
        raise HTTPException(status_code=409, detail="This review session is no longer editable")
    review = session.get(MistakeReview, review_id)
    answer = session.scalar(
        select(PracticeAnswer).where(
            PracticeAnswer.session_id == session_id,
            PracticeAnswer.original_attempt_id == review.original_attempt_id if review is not None else False,
        )
    )
    if review is None or review.user_id != user.id or answer is None:
        raise HTTPException(status_code=404, detail="Review item is not part of this session")
    if answer.status == "submitted":
        raise HTTPException(status_code=409, detail="This answer has already been submitted")
    answer.answer_text = payload.answer_text
    answer.updated_at = datetime.now(timezone.utc)
    session.commit()
    return _mistake_session_response(session, practice)


@app.post("/mistakes/sessions/{session_id}/items/{review_id}/retry", response_model=MistakeRetryResponse, status_code=status.HTTP_201_CREATED)
def submit_mistake_retry(
    session_id: int,
    review_id: int,
    payload: MistakeRetryCreate,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeRetryResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None or practice.session_type != "mistake_review":
        raise HTTPException(status_code=404, detail="Mistake review session was not found")
    user = _require_user_access(session, auth, practice.user_id)
    if payload.user_id != user.id:
        raise HTTPException(status_code=403, detail="You may only submit your own review answer")
    review = session.get(MistakeReview, review_id)
    answer = session.scalar(
        select(PracticeAnswer).where(
            PracticeAnswer.session_id == session_id,
            PracticeAnswer.original_attempt_id == review.original_attempt_id if review is not None else False,
        )
    )
    if review is None or review.user_id != user.id or answer is None:
        raise HTTPException(status_code=404, detail="Review item is not part of this session")
    original = session.get(Attempt, review.original_attempt_id)
    if original is None or original.user_id != user.id or original.retry_of_attempt_id is not None:
        raise HTTPException(status_code=404, detail="Original attempt was not found")

    existing_retry = session.scalar(
        select(Attempt).where(
            Attempt.user_id == user.id,
            Attempt.retry_submission_key == payload.idempotency_key,
        )
    )
    if existing_retry is not None:
        if (
            existing_retry.retry_of_attempt_id != original.id
            or existing_retry.submitted_answer_text != payload.answer_text
            or existing_retry.self_assessment != payload.self_assessment
        ):
            raise HTTPException(status_code=409, detail="This idempotency key belongs to a different retry")
        answer.answer_text = existing_retry.submitted_answer_text
        answer.status = "submitted"
        answer.attempt_id = existing_retry.id
        answer.updated_at = datetime.now(timezone.utc)
        session.commit()
        return MistakeRetryResponse(
            attempt_id=existing_retry.id,
            user_id=user.id,
            question_id=existing_retry.question_id,
            retry_of_attempt_id=original.id,
            self_assessment=existing_retry.self_assessment,
            grading_status="self_assessed",
        )

    if practice.state not in {"draft", "active"}:
        raise HTTPException(status_code=409, detail="This review session is no longer active")
    if answer.status == "submitted" or answer.attempt_id is not None:
        raise HTTPException(status_code=409, detail="This item already has a retry in this session")
    if not payload.answer_text.strip():
        raise HTTPException(status_code=422, detail="Write a retry answer before submitting")
    question = session.get(Question, original.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question was not found")
    _require_generated_question_owner(session, question, user.id)

    retry = Attempt(
        user_id=user.id,
        question_id=original.question_id,
        submitted_answer_text=payload.answer_text,
        points_awarded={},
        marks_earned=None,
        marks_possible=None,
        grading_model=None,
        grading_policy_version="self-assessment-v1",
        grading_status="self_assessed",
        retry_of_attempt_id=original.id,
        retry_submission_key=payload.idempotency_key,
        self_assessment=payload.self_assessment,
        attempted_at=datetime.now(timezone.utc),
    )
    session.add(retry)
    session.flush()
    answer.answer_text = payload.answer_text
    answer.status = "submitted"
    answer.attempt_id = retry.id
    answer.updated_at = datetime.now(timezone.utc)
    session.commit()
    return MistakeRetryResponse(
        attempt_id=retry.id,
        user_id=user.id,
        question_id=retry.question_id,
        retry_of_attempt_id=original.id,
        self_assessment=payload.self_assessment,
        grading_status="self_assessed",
    )


@app.get("/mistakes/sessions/{session_id}/items/{review_id}/reveal", response_model=MistakeRevealResponse)
def reveal_previous_mistake_attempt(
    session_id: int,
    review_id: int,
    user_id: int = Query(ge=1),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeRevealResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None or practice.session_type != "mistake_review":
        raise HTTPException(status_code=404, detail="Mistake review session was not found")
    _require_user_access(session, auth, user_id)
    if practice.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only reveal your own review history")
    review = session.get(MistakeReview, review_id)
    answer = session.scalar(
        select(PracticeAnswer).where(
            PracticeAnswer.session_id == session_id,
            PracticeAnswer.original_attempt_id == review.original_attempt_id if review is not None else False,
        )
    )
    if review is None or review.user_id != user_id or answer is None:
        raise HTTPException(status_code=404, detail="Review item is not part of this session")
    if answer.attempt_id is None:
        raise HTTPException(status_code=409, detail="Submit a fresh retry before revealing the previous answer")
    original = session.get(Attempt, review.original_attempt_id)
    if original is None or original.user_id != user_id:
        raise HTTPException(status_code=404, detail="Original attempt was not found")
    retry_rows = session.scalars(
        select(Attempt)
        .where(
            Attempt.user_id == user_id,
            Attempt.retry_of_attempt_id == original.id,
            Attempt.grading_status == "self_assessed",
        )
        .order_by(Attempt.attempted_at, Attempt.id)
    ).all()
    if not retry_rows:
        raise HTTPException(status_code=409, detail="Submit a fresh retry before revealing the previous answer")

    answer.previous_answer_revealed_at = datetime.now(timezone.utc)
    session.commit()
    prior_result = original.points_awarded if isinstance(original.points_awarded, dict) else {}
    return MistakeRevealResponse(
        review_id=review.id,
        original_attempt_id=original.id,
        original_answer_text=original.submitted_answer_text,
        marks_earned=original.marks_earned,
        marks_possible=original.marks_possible,
        points_hit=prior_result.get("points_hit", []) if isinstance(prior_result.get("points_hit", []), list) else [],
        points_missed=prior_result.get("points_missed", []) if isinstance(prior_result.get("points_missed", []), list) else [],
        feedback=prior_result.get("feedback") if isinstance(prior_result.get("feedback"), str) else None,
        retries=[
            MistakeRevealedRetry(
                attempt_id=retry.id,
                answer_text=retry.submitted_answer_text,
                self_assessment=retry.self_assessment,
                attempted_at=retry.attempted_at,
            )
            for retry in retry_rows
            if retry.self_assessment is not None
        ],
    )


@app.patch("/mistakes/reviews/{review_id}", response_model=MistakeQueueItem)
def update_mistake_review_state(
    review_id: int,
    payload: MistakeReviewStateUpdate,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeQueueItem:
    user = _require_user_access(session, auth, payload.user_id)
    review = session.get(MistakeReview, review_id)
    if review is None or review.user_id != user.id:
        raise HTTPException(status_code=404, detail="Mistake review was not found")
    allowed = {
        "open": {"resolved", "revisit"},
        "reopened": {"resolved", "revisit", "reopened"},
        "revisit": {"resolved", "revisit"},
        "resolved": {"resolved", "reopened"},
    }
    if payload.state not in allowed[review.state]:
        raise HTTPException(status_code=409, detail=f"Cannot change review state from {review.state} to {payload.state}")
    review.state = payload.state
    review.updated_at = datetime.now(timezone.utc)
    original = session.get(Attempt, review.original_attempt_id)
    if original is None or original.user_id != user.id:
        raise HTTPException(status_code=404, detail="Original attempt was not found")
    question = session.get(Question, original.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question was not found")
    _require_generated_question_owner(session, question, user.id)
    retry_count = session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.retry_of_attempt_id == original.id)
    ) or 0
    session.commit()
    return MistakeQueueItem(
        review_id=review.id,
        original_attempt_id=original.id,
        source=review.source,
        state=review.state,
        attempted_at=original.attempted_at,
        retry_count=retry_count,
        question=_question_response(question),
    )


@app.post("/mistakes/sessions/{session_id}/submit", response_model=MistakeSessionResponse)
def submit_mistake_review_session(
    session_id: int,
    user_id: int = Query(ge=1),
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> MistakeSessionResponse:
    practice = session.get(PracticeSession, session_id)
    if practice is None or practice.session_type != "mistake_review":
        raise HTTPException(status_code=404, detail="Mistake review session was not found")
    _require_user_access(session, auth, user_id)
    if practice.user_id != user_id:
        raise HTTPException(status_code=403, detail="You may only submit your own mistake review session")
    if practice.state == "submitted":
        return _mistake_session_response(session, practice)
    if practice.state not in {"draft", "active"}:
        raise HTTPException(status_code=409, detail="This review session cannot be submitted")
    incomplete = [
        answer.id
        for answer in practice.answers
        if answer.attempt_id is None
        or answer.original_attempt_id is None
        or (
            (review := session.scalar(
                select(MistakeReview).where(
                    MistakeReview.user_id == user_id,
                    MistakeReview.original_attempt_id == answer.original_attempt_id,
                )
            )) is None
            or review.state not in {"resolved", "revisit"}
        )
    ]
    if incomplete:
        raise HTTPException(status_code=422, detail="Retry every item and choose resolved or revisit before finishing")
    now = datetime.now(timezone.utc)
    practice.state = "submitted"
    practice.submitted_at = now
    for answer in practice.answers:
        answer.status = "submitted"
        answer.updated_at = now
    session.commit()
    return _mistake_session_response(session, practice)


@app.post("/papers/generate", response_model=GeneratedPaperResponse, status_code=status.HTTP_201_CREATED)
def create_paper(
    payload: PaperGenerateRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> GeneratedPaperResponse:
    _require_user_access(session, auth, payload.user_id)
    prompt_builder = request.app.state.paper_prompt_builder
    return generate_weak_spot_paper(
        session,
        payload,
        model=request.app.state.paper_model,
        prompt_builder=prompt_builder or build_prompt,
        allow_ai_generation=(
            getattr(request.app.state, "student_data_ai_approved", False)
            and request.app.state.paper_model is not None
        ),
    )


@app.get("/privacy/export")
def export_own_student_data(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> JSONResponse:
    user = _require_privacy_owner(session, auth, auth.user_id)
    response = JSONResponse(
        content=jsonable_encoder(export_student_data(session, user)),
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Content-Disposition": 'attachment; filename="student-data-export.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
    return response


@app.delete("/privacy/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_student_data(
    payload: PrivacyDeletionRequest,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(_session_for_request),
) -> Response:
    user = session.get(User, auth.user_id)
    if user is not None:
        _require_privacy_owner(session, auth, user.id)
        delete_student_data(session, user.id)
        session.commit()
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
    )

