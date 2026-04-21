"""Optional OpenAI-backed classifier used by the offline pipeline only."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

from report.models.schemas import ProcessedReview


@dataclass(slots=True)
class LLMClassificationResult:
    """Structured fallback decision returned by the LLM adapter."""

    included_in_analysis: bool
    category_tags: list[str]
    canonical_theme: str | None
    confidence: float


class OpenAILLMClassifier:
    """Minimal JSON-only classifier adapter for ambiguous review fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = (
            OpenAI(api_key=self.api_key)
            if OpenAI is not None and self.api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def classify(
        self,
        review: ProcessedReview,
        *,
        timeout_seconds: int = 20,
        retry_limit: int = 2,
    ) -> LLMClassificationResult | None:
        """Return one structured fallback decision or None on failure."""
        if self._client is None:
            return None

        system_prompt = (
            "You are a Korean Steam review fallback classifier. "
            "Return strict JSON only."
        )
        user_prompt = (
            "Classify one ambiguous Korean game review.\n"
            "Output JSON with keys:\n"
            "- included_in_analysis: boolean\n"
            "- category_tags: string[]\n"
            "- canonical_theme: string|null\n"
            "- confidence: number(0.0~1.0)\n"
            "Review text:\n"
            f"{review.review_text}"
        )

        for _attempt in range(retry_limit + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    continue
                parsed = json.loads(content)
                normalized = _validate_llm_payload(parsed)
                if normalized is not None:
                    return normalized
            except Exception:
                continue
        return None


def _validate_llm_payload(payload: Any) -> LLMClassificationResult | None:
    if not isinstance(payload, dict):
        return None
    included = payload.get("included_in_analysis")
    category_tags = payload.get("category_tags")
    canonical_theme = payload.get("canonical_theme")
    confidence = payload.get("confidence")

    if not isinstance(included, bool):
        return None
    if not isinstance(category_tags, list) or any(
        not isinstance(item, str) for item in category_tags
    ):
        return None
    if canonical_theme is not None and not isinstance(canonical_theme, str):
        return None
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        return None
    if confidence_value < 0.0 or confidence_value > 1.0:
        return None

    deduped = list(dict.fromkeys(tag.strip() for tag in category_tags if tag.strip()))
    canonical = canonical_theme.strip() if isinstance(canonical_theme, str) else None
    return LLMClassificationResult(
        included_in_analysis=included,
        category_tags=deduped,
        canonical_theme=canonical,
        confidence=round(confidence_value, 4),
    )

