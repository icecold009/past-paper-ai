from __future__ import annotations

import logging
from dataclasses import dataclass
from math import isfinite
from typing import Any, Protocol, Sequence


logger = logging.getLogger(__name__)

DETERMINISTIC_VERSION = "deterministic-v1"
TYPESAFE_VERSION = "typesafe-choice-v1"


@dataclass(frozen=True)
class RecommendationCandidate:
    candidate_id: str
    chapter_id: int | None
    action: str
    activity_type: str

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.candidate_id,
            "action": self.action,
            "activity_type": self.activity_type,
            "chapter_id": self.chapter_id,
        }


@dataclass(frozen=True)
class RecommendationDecision:
    candidate_id: str | None
    source: str
    confidence: float | None
    probabilities: dict[str, float]
    version: str
    provider_model: str | None = None


@dataclass(frozen=True)
class SelectionContext:
    subject_code: str
    grade_stage: str | None
    curriculum_version: str
    chapters: tuple[dict[str, object], ...]
    candidates: tuple[RecommendationCandidate, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "subject": self.subject_code,
            "grade_stage": self.grade_stage,
            "curriculum_version": self.curriculum_version,
            "chapters": [dict(chapter) for chapter in self.chapters],
            "candidates": [candidate.to_payload() for candidate in self.candidates],
        }


class RecommendationSelector(Protocol):
    def choose(self, context: SelectionContext) -> RecommendationDecision:
        """Select one application-generated candidate."""


def build_candidates(states: Sequence[object], *, max_candidates: int = 5) -> list[RecommendationCandidate]:
    """Build a bounded, stable candidate set from deterministic chapter states."""
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")

    eligible = [
        state
        for state in states
        if getattr(state, "state", None) in {"needs_practice", "developing"}
        and getattr(state, "score", None) is not None
    ]
    eligible.sort(
        key=lambda state: (
            float(getattr(state, "score", 1.0)),
            getattr(getattr(state, "chapter", None), "position", 0),
            getattr(getattr(state, "chapter", None), "id", 0),
        )
    )

    candidates: list[RecommendationCandidate] = []
    for state in eligible[:max_candidates]:
        chapter = state.chapter
        candidates.append(
            RecommendationCandidate(
                candidate_id=f"chapter:{chapter.id}:practice",
                chapter_id=chapter.id,
                action="practice",
                activity_type="targeted_practice",
            )
        )
    return candidates


def build_selection_context(
    states: Sequence[object],
    candidates: Sequence[RecommendationCandidate],
    *,
    subject_code: str,
    grade_stage: str | None,
) -> SelectionContext:
    versions = {getattr(state.chapter, "map_version", "unversioned") for state in states}
    curriculum_version = next(iter(versions)) if len(versions) == 1 else "mixed"
    chapters = tuple(
        {
            "id": state.chapter.id,
            "position": state.chapter.position,
            "state": state.state,
            "evidence_count": state.evidence_count,
            "score": state.score,
            "confidence": state.confidence,
        }
        for state in states
    )
    return SelectionContext(
        subject_code=subject_code,
        grade_stage=grade_stage,
        curriculum_version=curriculum_version,
        chapters=chapters,
        candidates=tuple(candidates),
    )


def deterministic_decision(candidates: Sequence[RecommendationCandidate]) -> RecommendationDecision:
    selected = candidates[0] if candidates else None
    return RecommendationDecision(
        candidate_id=selected.candidate_id if selected else None,
        source="deterministic",
        confidence=None,
        probabilities={selected.candidate_id: 1.0} if selected else {},
        version=DETERMINISTIC_VERSION,
    )


class DeterministicSelector:
    def choose(self, context: SelectionContext) -> RecommendationDecision:
        return deterministic_decision(context.candidates)


def validate_decision(
    decision: RecommendationDecision,
    candidates: Sequence[RecommendationCandidate],
    *,
    min_confidence: float = 0.0,
) -> RecommendationDecision:
    """Reject provider output unless it names a bounded, sufficiently certain choice."""
    allowed_ids = {candidate.candidate_id for candidate in candidates}
    if decision.source != "typesafe":
        raise ValueError("provider decision must have source=typesafe")
    if decision.candidate_id not in allowed_ids:
        raise ValueError("provider selected an unknown candidate")
    if decision.confidence is None or not isfinite(decision.confidence):
        raise ValueError("provider decision confidence is missing or invalid")
    if not 0.0 <= decision.confidence <= 1.0:
        raise ValueError("provider decision confidence is outside [0, 1]")
    if decision.confidence < min_confidence:
        raise ValueError("provider decision confidence is below the configured threshold")
    if any(
        candidate_id not in allowed_ids
        or not isfinite(probability)
        or not 0.0 <= probability <= 1.0
        for candidate_id, probability in decision.probabilities.items()
    ):
        raise ValueError("provider returned an invalid candidate distribution")
    return decision


def choose_with_fallback(
    context: SelectionContext,
    *,
    selector: RecommendationSelector | None,
    mode: str,
    min_confidence: float,
) -> RecommendationDecision:
    deterministic = deterministic_decision(context.candidates)
    if selector is None or mode == "off":
        return deterministic

    try:
        provider_decision = selector.choose(context)
        provider_decision = validate_decision(
            provider_decision,
            context.candidates,
            min_confidence=min_confidence,
        )
    except Exception as exc:  # Provider failures are deliberately fail-safe.
        logger.warning("adaptive recommendation unavailable: %s", type(exc).__name__)
        return deterministic

    if mode == "shadow":
        return deterministic
    return provider_decision
