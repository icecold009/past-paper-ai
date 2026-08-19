from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    Attempt,
    CurriculumChapter,
    DiagnosticEvidence,
    Question,
    QuestionChapterMapping,
    Recommendation,
)


RULE_VERSION = "deterministic-v1"
MIN_EVIDENCE = 2
NEEDS_PRACTICE_THRESHOLD = 0.60
STRONG_THRESHOLD = 0.80


@dataclass(frozen=True)
class ChapterState:
    chapter: CurriculumChapter
    evidence_count: int
    score: float | None
    confidence: float | None
    state: str
    latest_attempt_id: int | None


@dataclass(frozen=True)
class Guidance:
    state: str
    explanation: str
    selected: ChapterState | None
    chapters: list[ChapterState]
    recommendation: Recommendation | None


def _score(attempt: Attempt) -> float | None:
    if attempt.marks_earned is None or attempt.marks_possible in (None, 0):
        return None
    return max(0.0, min(1.0, float(attempt.marks_earned) / float(attempt.marks_possible)))


def _state(evidence_count: int, score: float | None) -> str:
    if evidence_count < MIN_EVIDENCE or score is None:
        return "not_enough_evidence"
    if score < NEEDS_PRACTICE_THRESHOLD:
        return "needs_practice"
    if score < STRONG_THRESHOLD:
        return "developing"
    return "strong"


def approved_chapters(
    session: Session,
    *,
    subject_id: int,
    grade_stage: str | None = None,
) -> list[CurriculumChapter]:
    query = select(CurriculumChapter).where(
        CurriculumChapter.subject_id == subject_id,
        CurriculumChapter.review_status == "approved",
    )
    if grade_stage:
        query = query.where(CurriculumChapter.grade_stage == grade_stage)
    return list(
        session.scalars(
            query.order_by(
                CurriculumChapter.position,
                CurriculumChapter.chapter_code,
                CurriculumChapter.id,
            )
        ).all()
    )


def chapter_attempts(session: Session, *, user_id: int, chapter_id: int) -> list[Attempt]:
    return list(
        session.scalars(
            select(Attempt)
            .join(Question, Attempt.question_id == Question.id)
            .join(QuestionChapterMapping, QuestionChapterMapping.question_id == Question.id)
            .where(
                Attempt.user_id == user_id,
                QuestionChapterMapping.chapter_id == chapter_id,
                QuestionChapterMapping.review_status == "approved",
            )
            .order_by(Attempt.attempted_at.desc(), Attempt.id.desc())
            .limit(20)
        ).all()
    )


def summarize_chapter(session: Session, *, user_id: int, chapter: CurriculumChapter) -> ChapterState:
    attempts = chapter_attempts(session, user_id=user_id, chapter_id=chapter.id)
    scored = [(attempt, _score(attempt)) for attempt in attempts]
    scored = [(attempt, score) for attempt, score in scored if score is not None]
    scores = [score for _, score in scored]
    score = sum(scores) / len(scores) if scores else None
    evidence_count = len(scores)
    confidence = min(1.0, evidence_count / 5) if evidence_count else None
    return ChapterState(
        chapter=chapter,
        evidence_count=evidence_count,
        score=score,
        confidence=confidence,
        state=_state(evidence_count, score),
        latest_attempt_id=scored[0][0].id if scored else None,
    )


def _latest_evidence(session: Session, *, user_id: int, chapter_id: int) -> DiagnosticEvidence | None:
    return session.scalar(
        select(DiagnosticEvidence)
        .where(
            DiagnosticEvidence.user_id == user_id,
            DiagnosticEvidence.chapter_id == chapter_id,
            DiagnosticEvidence.source_type == "attempts",
        )
        .order_by(DiagnosticEvidence.observed_at.desc(), DiagnosticEvidence.id.desc())
    )


def _persist_evidence(session: Session, *, user_id: int, state: ChapterState, now: datetime) -> DiagnosticEvidence:
    evidence = _latest_evidence(session, user_id=user_id, chapter_id=state.chapter.id)
    if evidence is None:
        evidence = DiagnosticEvidence(
            user_id=user_id,
            chapter_id=state.chapter.id,
            source_type="attempts",
        )
        session.add(evidence)
    evidence.attempt_id = state.latest_attempt_id
    evidence.evidence_count = state.evidence_count
    evidence.score = state.score
    evidence.confidence = state.confidence
    evidence.state = state.state
    evidence.observed_at = now
    return evidence


def _recommendation_for(
    session: Session,
    *,
    user_id: int,
    state: ChapterState,
    now: datetime,
) -> Recommendation:
    recommendation = session.scalar(
        select(Recommendation)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.chapter_id == state.chapter.id,
            Recommendation.dismissed_at.is_(None),
        )
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
    )
    score_text = f"{state.score:.0%}" if state.score is not None else "limited"
    if state.state == "needs_practice":
        reason = (
            f"{state.evidence_count} marked attempts in {state.chapter.name} averaged {score_text}; "
            "targeted practice is recommended."
        )
    else:
        reason = (
            f"{state.evidence_count} marked attempts in {state.chapter.name} averaged {score_text}; "
            "more practice will build confidence before moving on."
        )
    if recommendation is None:
        recommendation = Recommendation(
            user_id=user_id,
            chapter_id=state.chapter.id,
            state=state.state,
            reason=reason,
            evidence_count=state.evidence_count,
            confidence=state.confidence,
            activity_type="targeted_practice",
            rule_version=RULE_VERSION,
            curriculum_version=state.chapter.map_version,
            created_at=now,
        )
        session.add(recommendation)
    else:
        recommendation.state = state.state
        recommendation.reason = reason
        recommendation.evidence_count = state.evidence_count
        recommendation.confidence = state.confidence
        recommendation.rule_version = RULE_VERSION
        recommendation.curriculum_version = state.chapter.map_version
    return recommendation


def build_guidance(
    session: Session,
    *,
    user_id: int,
    subject_id: int,
    grade_stage: str | None = None,
    now: datetime | None = None,
) -> Guidance:
    now = now or datetime.now(timezone.utc)
    chapters = approved_chapters(session, subject_id=subject_id, grade_stage=grade_stage)
    if not chapters:
        return Guidance(
            state="no_content",
            explanation="There is no approved curriculum content for this subject yet.",
            selected=None,
            chapters=[],
            recommendation=None,
        )

    states = [summarize_chapter(session, user_id=user_id, chapter=chapter) for chapter in chapters]
    for state in states:
        _persist_evidence(session, user_id=user_id, state=state, now=now)

    candidates = [
        state
        for state in states
        if state.state in {"needs_practice", "developing"} and state.score is not None
    ]
    selected = min(candidates, key=lambda state: (state.score or 0.0, state.chapter.position, state.chapter.id)) if candidates else None
    if selected is not None:
        recommendation = _recommendation_for(session, user_id=user_id, state=selected, now=now)
        return Guidance(
            state="needs_practice",
            explanation=recommendation.reason,
            selected=selected,
            chapters=states,
            recommendation=recommendation,
        )

    if any(state.state == "not_enough_evidence" for state in states):
        return Guidance(
            state="start_diagnostic",
            explanation="There is not enough marked evidence to identify a reliable weak chapter yet.",
            selected=None,
            chapters=states,
            recommendation=None,
        )

    return Guidance(
        state="on_track",
        explanation="Current marked evidence is at or above the practice threshold across the approved chapters.",
        selected=None,
        chapters=states,
        recommendation=None,
    )


def dismiss_recommendation(session: Session, *, recommendation: Recommendation, now: datetime | None = None) -> None:
    recommendation.dismissed_at = now or datetime.now(timezone.utc)
