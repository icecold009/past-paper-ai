from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Mapping


GuidanceMode = Literal["off", "shadow", "active"]


def _bounded_int(value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: str | None, *, default: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return default
    return max(0.0, min(1.0, parsed))


@dataclass(frozen=True)
class RecommendationConfig:
    """Server-only configuration for optional adaptive selection."""

    api_key: str | None = None
    endpoint: str | None = None
    model: str = "jev"
    timeout_ms: int = 1200
    max_candidates: int = 5
    mode: GuidanceMode = "off"
    min_confidence: float = 0.55

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RecommendationConfig:
        values = environ if environ is not None else os.environ
        raw_mode = values.get("TYPESAFE_GUIDANCE_MODE", "off").strip().lower()
        mode: GuidanceMode = raw_mode if raw_mode in {"off", "shadow", "active"} else "off"  # type: ignore[assignment]
        return cls(
            api_key=values.get("TYPESAFE_API_KEY", "").strip() or None,
            endpoint=values.get("TYPESAFE_API_URL", "").strip() or None,
            model=values.get("TYPESAFE_MODEL", "jev").strip() or "jev",
            timeout_ms=_bounded_int(
                values.get("TYPESAFE_TIMEOUT_MS"),
                default=1200,
                minimum=100,
                maximum=30_000,
            ),
            max_candidates=_bounded_int(
                values.get("TYPESAFE_MAX_CANDIDATES"),
                default=5,
                minimum=1,
                maximum=50,
            ),
            mode=mode,
            min_confidence=_bounded_float(
                values.get("TYPESAFE_MIN_CONFIDENCE"),
                default=0.55,
            ),
        )
