from __future__ import annotations

import unittest
from types import SimpleNamespace

from api.recommendation_config import RecommendationConfig
from api.recommendation_selection import (
    SelectionContext,
    build_candidates,
    build_selection_context,
    choose_with_fallback,
)
from api.typesafe_client import TypeSafeChoiceClient


def _state(
    chapter_id: int,
    *,
    position: int,
    state: str = "needs_practice",
    score: float | None = 0.4,
) -> SimpleNamespace:
    return SimpleNamespace(
        chapter=SimpleNamespace(id=chapter_id, position=position, map_version="approved-v1"),
        state=state,
        score=score,
        evidence_count=3,
        confidence=0.6,
    )


class _FakeSelector:
    def __init__(self, decision) -> None:
        self.decision = decision
        self.calls = 0

    def choose(self, context: SelectionContext):
        self.calls += 1
        return self.decision


class TypeSafeSelectionTests(unittest.TestCase):
    def test_candidates_are_stable_and_bounded(self) -> None:
        states = [
            _state(3, position=3, score=0.52),
            _state(1, position=1, score=0.31),
            _state(2, position=2, score=0.31),
            _state(4, position=4, state="strong", score=0.95),
            _state(5, position=5, state="not_enough_evidence", score=None),
        ]

        candidates = build_candidates(states, max_candidates=2)

        self.assertEqual([candidate.candidate_id for candidate in candidates], [
            "chapter:1:practice",
            "chapter:2:practice",
        ])
        self.assertEqual(candidates[0].activity_type, "targeted_practice")

    def test_unknown_provider_candidate_falls_back(self) -> None:
        states = [_state(1, position=1), _state(2, position=2, score=0.5)]
        candidates = build_candidates(states)
        context = build_selection_context(
            states,
            candidates,
            subject_code="9618",
            grade_stage="A Level",
        )
        selector = _FakeSelector(
            decision=SimpleNamespace(
                candidate_id="chapter:999:practice",
                source="typesafe",
                confidence=0.99,
                probabilities={"chapter:999:practice": 1.0},
                version="typesafe-choice-v1",
                provider_model="jev",
            )
        )

        decision = choose_with_fallback(
            context,
            selector=selector,
            mode="active",
            min_confidence=0.55,
        )

        self.assertEqual(decision.source, "deterministic")
        self.assertEqual(decision.candidate_id, "chapter:1:practice")
        self.assertEqual(selector.calls, 1)

    def test_low_confidence_and_shadow_mode_use_deterministic_choice(self) -> None:
        states = [_state(1, position=1), _state(2, position=2, score=0.5)]
        candidates = build_candidates(states)
        context = build_selection_context(
            states,
            candidates,
            subject_code="9618",
            grade_stage="A Level",
        )
        provider_decision = SimpleNamespace(
            candidate_id="chapter:2:practice",
            source="typesafe",
            confidence=0.2,
            probabilities={"chapter:2:practice": 0.2},
            version="typesafe-choice-v1",
            provider_model="jev",
        )

        low_confidence = choose_with_fallback(
            context,
            selector=_FakeSelector(provider_decision),
            mode="active",
            min_confidence=0.55,
        )
        shadow = choose_with_fallback(
            context,
            selector=_FakeSelector(
                SimpleNamespace(
                    **{**provider_decision.__dict__, "confidence": 0.9}
                )
            ),
            mode="shadow",
            min_confidence=0.55,
        )

        self.assertEqual(low_confidence.source, "deterministic")
        self.assertEqual(shadow.source, "deterministic")

    def test_provider_timeout_falls_back(self) -> None:
        states = [_state(1, position=1), _state(2, position=2, score=0.5)]
        candidates = build_candidates(states)
        context = build_selection_context(
            states,
            candidates,
            subject_code="9618",
            grade_stage="A Level",
        )

        class TimeoutSelector:
            def choose(self, context):
                raise TimeoutError("provider timeout")

        decision = choose_with_fallback(
            context,
            selector=TimeoutSelector(),
            mode="active",
            min_confidence=0.55,
        )

        self.assertEqual(decision.source, "deterministic")
        self.assertEqual(decision.candidate_id, "chapter:1:practice")

    def test_malformed_provider_response_falls_back(self) -> None:
        states = [_state(1, position=1)]
        candidates = build_candidates(states)
        context = build_selection_context(
            states,
            candidates,
            subject_code="9618",
            grade_stage="A Level",
        )
        client = TypeSafeChoiceClient(
            RecommendationConfig(
                api_key="test-key",
                endpoint="https://typesafe.invalid/choice",
                mode="active",
            ),
            transport=lambda *args: {"unexpected": "shape"},
        )

        decision = choose_with_fallback(
            context,
            selector=client,
            mode="active",
            min_confidence=0.55,
        )

        self.assertEqual(decision.source, "deterministic")
        self.assertEqual(decision.candidate_id, "chapter:1:practice")

    def test_http_adapter_keeps_request_to_derived_state(self) -> None:
        states = [_state(1, position=1)]
        candidates = build_candidates(states)
        context = build_selection_context(
            states,
            candidates,
            subject_code="9618",
            grade_stage="A Level",
        )
        captured: dict[str, object] = {}

        def transport(endpoint, headers, body, timeout_seconds):
            captured["endpoint"] = endpoint
            captured["headers"] = headers
            captured["body"] = body
            captured["timeout_seconds"] = timeout_seconds
            return {
                "candidate_id": "chapter:1:practice",
                "confidence": 0.91,
                "probabilities": {"chapter:1:practice": 0.91},
                "model": "jev",
            }

        decision = TypeSafeChoiceClient(
            RecommendationConfig(
                api_key="test-key",
                endpoint="https://typesafe.invalid/choice",
                model="jev",
                mode="active",
            ),
            transport=transport,
        ).choose(context)

        self.assertEqual(decision.candidate_id, "chapter:1:practice")
        self.assertEqual(decision.source, "typesafe")
        self.assertIn("chapter:1:practice", captured["body"].decode("utf-8"))
        self.assertNotIn("answer", captured["body"].decode("utf-8").lower())

    def test_default_configuration_is_off(self) -> None:
        config = RecommendationConfig.from_env({})
        self.assertEqual(config.mode, "off")
        self.assertIsNone(config.api_key)
        self.assertEqual(config.max_candidates, 5)


if __name__ == "__main__":
    unittest.main()
