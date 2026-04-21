"""LLM-assisted report material refinement for offline pipeline."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from math import log1p
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

from report.models.schemas import AnalysisResult, ProcessedReview

_CANDIDATE_SCORE_WEIGHTS = {
    "has_tags": 0.33,
    "has_theme": 0.18,
    "playtime": 0.24,
    "author_reviews": 0.10,
    "length": 0.10,
    "recency": 0.05,
}


@dataclass(slots=True)
class ReportMaterialRefinerConfig:
    """Operational guardrails for report material refinement."""

    enabled: bool = True
    max_llm_reviews: int = 50
    timeout_seconds: int = 20
    retry_limit: int = 2
    min_confidence: float = 0.70


@dataclass(slots=True)
class ReportMaterialRefinerStats:
    """Execution stats for one refinement batch."""

    considered: int = 0
    selected: int = 0
    invoked: int = 0
    success: int = 0
    schema_invalid: int = 0
    low_confidence: int = 0
    cache_hits: int = 0
    fallback_used: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "considered": self.considered,
            "selected": self.selected,
            "invoked": self.invoked,
            "success": self.success,
            "schema_invalid": self.schema_invalid,
            "low_confidence": self.low_confidence,
            "cache_hits": self.cache_hits,
            "fallback_used": self.fallback_used,
        }


@dataclass(slots=True)
class RefinedReviewMaterial:
    """One review material record passed to report generation."""

    review_id: str
    appid: int
    voted_up: bool
    category_tags: list[str]
    canonical_theme: str | None
    source_text: str
    refined_text: str
    stance: str
    confidence: float
    llm_used: bool
    utility_rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "appid": self.appid,
            "voted_up": self.voted_up,
            "category_tags": list(self.category_tags),
            "canonical_theme": self.canonical_theme,
            "source_text": self.source_text,
            "refined_text": self.refined_text,
            "stance": self.stance,
            "confidence": round(self.confidence, 4),
            "llm_used": self.llm_used,
            "utility_rank": int(self.utility_rank),
        }


@dataclass(slots=True)
class RefinedMaterialOutput:
    """Validated LLM output schema."""

    refined_text: str
    stance: str
    confidence: float


class OpenAIReportMaterialRefiner:
    """JSON-only OpenAI adapter for report material refinement."""

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

    def refine(
        self,
        *,
        review: ProcessedReview,
        timeout_seconds: int = 20,
        retry_limit: int = 2,
    ) -> RefinedMaterialOutput | None:
        """Refine one review into buyer-facing evidence material."""
        if self._client is None:
            return None

        user_payload = {
            "task": "refine_report_material",
            "review": {
                "review_id": review.review_id,
                "text": review.review_text,
                "normalized_text": review.normalized_text,
                "voted_up": review.voted_up,
                "category_tags": list(review.category_tags),
                "canonical_theme": review.canonical_theme,
                "playtime_at_review_hours": review.playtime_at_review_hours,
                "num_reviews": review.num_reviews,
            },
            "rules": [
                "요약이 아니라 근거 재료를 만든다.",
                "의미를 바꾸지 않는다.",
                "핵심 경험 + 감정 반응을 유지한다.",
                "1~4문장, 자연스러운 한국어로 작성한다.",
                "JSON만 반환한다.",
            ],
            "output_schema": {
                "refined_text": "string(1~4문장)",
                "stance": "positive|negative|mixed",
                "confidence": "number(0.0~1.0)",
            },
        }

        for _ in range(retry_limit + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You rewrite Korean Steam reviews into concise buyer-facing evidence "
                                "without changing meaning. Return strict JSON only."
                            ),
                        },
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    continue
                parsed = json.loads(content)
                validated = _validate_refined_material_output(parsed)
                if validated is not None:
                    return validated
            except Exception:
                continue
        return None


def build_report_materials(
    processed_reviews: list[ProcessedReview],
    *,
    analysis: AnalysisResult,
    config: ReportMaterialRefinerConfig,
    refiner: OpenAIReportMaterialRefiner | None,
) -> tuple[list[dict[str, Any]], ReportMaterialRefinerStats]:
    """Select high-utility reviews and refine them for report generation."""
    del analysis  # Reserved for future deterministic selection tuning.
    stats = ReportMaterialRefinerStats()
    if not config.enabled:
        return [], stats
    material_rewrite_enabled = _is_llm_material_rewrite_enabled()

    candidates = _select_candidates(processed_reviews, max_count=max(config.max_llm_reviews, 0))
    stats.considered = sum(1 for review in processed_reviews if review.included_in_analysis)
    stats.selected = len(candidates)

    cache: dict[str, RefinedMaterialOutput | None] = {}
    materials: list[RefinedReviewMaterial] = []
    llm_available = bool(refiner and refiner.available)

    for rank, review in enumerate(candidates, start=1):
        source_text = _normalize_review_text(review.review_text)
        cache_key = review.normalized_text.strip().lower()
        decision: RefinedMaterialOutput | None = None
        llm_used = False

        if cache_key and cache_key in cache:
            decision = cache[cache_key]
            stats.cache_hits += 1
            llm_used = decision is not None
        elif llm_available and refiner is not None:
            stats.invoked += 1
            decision = refiner.refine(
                review=review,
                timeout_seconds=config.timeout_seconds,
                retry_limit=config.retry_limit,
            )
            cache[cache_key] = decision
            llm_used = decision is not None

        if decision is None:
            stats.schema_invalid += 1 if llm_available else 0
            stats.fallback_used += 1
            materials.append(
                RefinedReviewMaterial(
                    review_id=review.review_id,
                    appid=review.appid,
                    voted_up=bool(review.voted_up),
                    category_tags=list(review.category_tags),
                    canonical_theme=review.canonical_theme,
                    source_text=source_text,
                    refined_text=source_text,
                    stance=_fallback_stance(review),
                    confidence=0.0,
                    llm_used=False,
                    utility_rank=rank,
                )
            )
            continue

        if decision.confidence < config.min_confidence:
            stats.low_confidence += 1
            stats.fallback_used += 1
            materials.append(
                RefinedReviewMaterial(
                    review_id=review.review_id,
                    appid=review.appid,
                    voted_up=bool(review.voted_up),
                    category_tags=list(review.category_tags),
                    canonical_theme=review.canonical_theme,
                    source_text=source_text,
                    refined_text=source_text,
                    stance=_fallback_stance(review),
                    confidence=round(decision.confidence, 4),
                    llm_used=llm_used,
                    utility_rank=rank,
                )
            )
            continue

        stats.success += 1
        materials.append(
            RefinedReviewMaterial(
                review_id=review.review_id,
                appid=review.appid,
                voted_up=bool(review.voted_up),
                category_tags=list(review.category_tags),
                canonical_theme=review.canonical_theme,
                source_text=source_text,
                refined_text=(
                    decision.refined_text
                    if material_rewrite_enabled
                    else source_text
                ),
                stance=decision.stance,
                confidence=round(decision.confidence, 4),
                llm_used=llm_used,
                utility_rank=rank,
            )
        )

    return [material.to_dict() for material in materials], stats


def _select_candidates(processed_reviews: list[ProcessedReview], *, max_count: int) -> list[ProcessedReview]:
    included = [review for review in processed_reviews if review.included_in_analysis]
    if not included or max_count <= 0:
        return []

    score_map = _build_candidate_score_map(included)
    positives = [review for review in included if review.voted_up]
    negatives = [review for review in included if not review.voted_up]
    positives.sort(key=lambda review: _candidate_sort_key(review, score_map), reverse=True)
    negatives.sort(key=lambda review: _candidate_sort_key(review, score_map), reverse=True)

    target_half = max_count // 2
    selected: list[ProcessedReview] = []
    selected_ids: set[str] = set()

    for review in negatives[:target_half]:
        if review.review_id in selected_ids:
            continue
        selected.append(review)
        selected_ids.add(review.review_id)

    for review in positives[:target_half]:
        if review.review_id in selected_ids:
            continue
        selected.append(review)
        selected_ids.add(review.review_id)

    if len(selected) < max_count:
        remaining = sorted(
            included,
            key=lambda review: _candidate_sort_key(review, score_map),
            reverse=True,
        )
        for review in remaining:
            if review.review_id in selected_ids:
                continue
            selected.append(review)
            selected_ids.add(review.review_id)
            if len(selected) >= max_count:
                break

    return selected[:max_count]


def _candidate_sort_key(
    review: ProcessedReview,
    score_map: dict[str, float],
) -> tuple[float, int]:
    return (
        score_map.get(review.review_id, 0.0),
        int(review.timestamp_created or 0),
    )


def _is_llm_material_rewrite_enabled() -> bool:
    return os.getenv("USE_LLM_MATERIAL_REWRITE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_candidate_score_map(processed_reviews: list[ProcessedReview]) -> dict[str, float]:
    if not processed_reviews:
        return {}

    created_values = [int(review.timestamp_created or 0) for review in processed_reviews]
    min_created = min(created_values)
    max_created = max(created_values)
    created_range = max(max_created - min_created, 1)

    score_map: dict[str, float] = {}
    for review in processed_reviews:
        score_map[review.review_id] = _candidate_score(
            review,
            min_created=min_created,
            created_range=created_range,
        )
    return score_map


def _candidate_score(
    review: ProcessedReview,
    *,
    min_created: int,
    created_range: int,
) -> float:
    text = review.normalized_text.strip()
    has_tags = 1.0 if review.category_tags else 0.0
    has_theme = 1.0 if review.canonical_theme else 0.0
    playtime = min(log1p(max(float(review.playtime_at_review_hours or 0.0), 0.0)) / log1p(100.0), 1.0)
    author_reviews = min(log1p(max(float(review.num_reviews or 0), 0.0)) / log1p(50.0), 1.0)
    length = min(len(text) / 300.0, 1.0)
    created = int(review.timestamp_created or 0)
    recency = min(max((created - min_created) / float(created_range), 0.0), 1.0)

    weights = _CANDIDATE_SCORE_WEIGHTS
    return (
        weights["has_tags"] * has_tags
        + weights["has_theme"] * has_theme
        + weights["playtime"] * playtime
        + weights["author_reviews"] * author_reviews
        + weights["length"] * length
        + weights["recency"] * recency
    )


def _fallback_stance(review: ProcessedReview) -> str:
    return "positive" if review.voted_up else "negative"


def _validate_refined_material_output(payload: Any) -> RefinedMaterialOutput | None:
    if not isinstance(payload, dict):
        return None
    refined_text = payload.get("refined_text")
    stance = payload.get("stance")
    confidence = payload.get("confidence")

    if not isinstance(refined_text, str):
        return None
    if stance not in {"positive", "negative", "mixed"}:
        return None
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        return None
    if confidence_value < 0.0 or confidence_value > 1.0:
        return None

    normalized = _normalize_review_text(refined_text)
    sentence_len = _sentence_count(normalized)
    if not normalized:
        return None
    if sentence_len < 1 or sentence_len > 4:
        return None
    return RefinedMaterialOutput(
        refined_text=normalized,
        stance=str(stance),
        confidence=round(confidence_value, 4),
    )


def _normalize_review_text(text: str) -> str:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return ""
    return normalized


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _sentence_count(text: str) -> int:
    return len(_split_sentences(text))

