from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api.recommendation_config import RecommendationConfig
from api.recommendation_selection import (
    RecommendationDecision,
    SelectionContext,
    TYPESAFE_VERSION,
)


logger = logging.getLogger(__name__)
Transport = Callable[[str, Mapping[str, str], bytes, float], object]


class TypeSafeProviderError(RuntimeError):
    """A safe, non-content-bearing provider error."""


class TypeSafeChoiceClient:
    """Small HTTP adapter kept behind the provider-neutral selector contract.

    The endpoint and response adapter are configurable because live TypeSafe API
    details were not available in this environment. Tests should inject a
    transport and never call the live provider.
    """

    def __init__(self, config: RecommendationConfig, *, transport: Transport | None = None) -> None:
        self.config = config
        self.transport = transport or self._post_json

    def choose(self, context: SelectionContext) -> RecommendationDecision:
        if not self.config.api_key or not self.config.endpoint:
            raise TypeSafeProviderError("TypeSafe provider is not configured")

        payload = {
            "model": self.config.model,
            "judgment": {
                "type": "choice",
                "question": (
                    "Which application-generated candidate is the most useful next study activity "
                    "given the approved chapter states and evidence? Choose only one candidate."
                ),
                "state": context.to_payload(),
            },
        }
        try:
            raw_response = self.transport(
                self.config.endpoint,
                {
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                self.config.timeout_ms / 1000,
            )
            response = self._coerce_mapping(raw_response)
            return self._parse_response(response)
        except TypeSafeProviderError:
            raise
        except (TimeoutError, HTTPError, URLError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("TypeSafe choice request failed: %s", type(exc).__name__)
            raise TypeSafeProviderError("TypeSafe choice request failed") from exc

    def _post_json(
        self,
        endpoint: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> object:
        request = Request(endpoint, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - configured server endpoint
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            logger.warning("TypeSafe choice HTTP failure: %s", exc.code)
            raise TypeSafeProviderError("TypeSafe choice request failed") from exc
        except (TimeoutError, URLError, OSError, json.JSONDecodeError) as exc:
            logger.warning("TypeSafe choice transport failure: %s", type(exc).__name__)
            raise TypeSafeProviderError("TypeSafe choice request failed") from exc

    @staticmethod
    def _coerce_mapping(value: object) -> Mapping[str, Any]:
        if isinstance(value, (bytes, str)):
            value = json.loads(value)
        if not isinstance(value, Mapping):
            raise TypeSafeProviderError("TypeSafe response was not an object")
        return value

    @staticmethod
    def _parse_response(response: Mapping[str, Any]) -> RecommendationDecision:
        choice: object = response.get("candidate_id")
        if choice is None:
            choice = response.get("choice", response.get("answer", response.get("result")))
        if isinstance(choice, Mapping):
            choice = choice.get("candidate_id", choice.get("id", choice.get("value")))
        if not isinstance(choice, str) or not choice.strip():
            raise TypeSafeProviderError("TypeSafe response did not contain a candidate")

        raw_probabilities = response.get("probabilities", response.get("distribution", {}))
        if not isinstance(raw_probabilities, Mapping):
            raise TypeSafeProviderError("TypeSafe response distribution was invalid")
        probabilities: dict[str, float] = {}
        for candidate_id, probability in raw_probabilities.items():
            if not isinstance(candidate_id, str):
                raise TypeSafeProviderError("TypeSafe response distribution was invalid")
            try:
                probabilities[candidate_id] = float(probability)
            except (TypeError, ValueError) as exc:
                raise TypeSafeProviderError("TypeSafe response distribution was invalid") from exc

        confidence = response.get("confidence")
        if confidence is None and choice in probabilities:
            confidence = probabilities[choice]
        try:
            parsed_confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError) as exc:
            raise TypeSafeProviderError("TypeSafe response confidence was invalid") from exc

        return RecommendationDecision(
            candidate_id=choice.strip(),
            source="typesafe",
            confidence=parsed_confidence,
            probabilities=probabilities,
            version=TYPESAFE_VERSION,
            provider_model=str(response.get("model") or "") or None,
        )
