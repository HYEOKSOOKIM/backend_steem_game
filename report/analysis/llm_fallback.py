"""Selective LLM fallback helpers for offline preprocessing."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from report.models.schemas import ProcessedReview
from report.services.llm_classifier import LLMClassificationResult


@dataclass(slots=True)
class LLMFallbackConfig:
    """Operational safeguards for fallback invocation."""

    enabled: bool = True
    max_llm_reviews: int = 50
    timeout_seconds: int = 20
    retry_limit: int = 2
    min_confidence: float = 0.70


@dataclass(slots=True)
class LLMFallbackStats:
    """Execution stats for one offline fallback run."""

    considered: int = 0
    invoked: int = 0
    success: int = 0
    schema_invalid: int = 0
    low_confidence: int = 0
    cache_hits: int = 0
    skipped_hard_exclusion: int = 0
    skipped_no_semantic_signal: int = 0
    skipped_no_uncertainty_signal: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "considered": self.considered,
            "invoked": self.invoked,
            "success": self.success,
            "schema_invalid": self.schema_invalid,
            "low_confidence": self.low_confidence,
            "cache_hits": self.cache_hits,
            "skipped_hard_exclusion": self.skipped_hard_exclusion,
            "skipped_no_semantic_signal": self.skipped_no_semantic_signal,
            "skipped_no_uncertainty_signal": self.skipped_no_uncertainty_signal,
        }


class LLMClassifierProtocol(Protocol):
    """Classifier interface used by fallback orchestration."""

    @property
    def available(self) -> bool: ...

    def classify(
        self,
        review: ProcessedReview,
        *,
        timeout_seconds: int = 20,
        retry_limit: int = 2,
    ) -> LLMClassificationResult | None: ...


def apply_selective_llm_fallback(
    processed_reviews: list[ProcessedReview],
    *,
    classifier: LLMClassifierProtocol | None,
    config: LLMFallbackConfig,
) -> tuple[list[ProcessedReview], LLMFallbackStats]:
    """Run selective fallback for ambiguous reviews with strict safeguards."""
    stats = LLMFallbackStats()
    if not config.enabled or classifier is None or not classifier.available:
        return [_ensure_final_fields(review) for review in processed_reviews], stats

    candidate_indexes: list[int] = []
    for index, review in enumerate(processed_reviews):
        stats.considered += 1
        if _is_hard_exclusion_zone(review):
            stats.skipped_hard_exclusion += 1
            continue
        if not _has_semantic_signal(review):
            stats.skipped_no_semantic_signal += 1
            continue
        if not _has_uncertainty_signal(review):
            stats.skipped_no_uncertainty_signal += 1
            continue
        candidate_indexes.append(index)

    capped_indexes = candidate_indexes[: max(config.max_llm_reviews, 0)]
    cache: dict[str, LLMClassificationResult | None] = {}
    updated_reviews = list(processed_reviews)

    for index in capped_indexes:
        review = updated_reviews[index]
        cache_key = review.normalized_text.strip().lower()
        stats.invoked += 1

        if cache_key in cache:
            decision = cache[cache_key]
            stats.cache_hits += 1
        else:
            decision = classifier.classify(
                review,
                timeout_seconds=config.timeout_seconds,
                retry_limit=config.retry_limit,
            )
            cache[cache_key] = decision

        if decision is None:
            stats.schema_invalid += 1
            updated_reviews[index] = _mark_rule_fallback(review, llm_attempted=True)
            continue

        if decision.confidence < config.min_confidence:
            stats.low_confidence += 1
            updated_reviews[index] = _mark_rule_fallback(
                review,
                llm_attempted=True,
                llm_decision=_decision_label(decision.included_in_analysis),
                llm_confidence=decision.confidence,
            )
            continue

        stats.success += 1
        final_include = bool(decision.included_in_analysis)
        final_tags = decision.category_tags if final_include else []
        final_theme = decision.canonical_theme if final_include else None
        updated_reviews[index] = replace(
            review,
            included_in_analysis=final_include,
            llm_invoked=True,
            llm_decision=_decision_label(final_include),
            llm_confidence=decision.confidence,
            final_decision_source="llm",
            final_decision=_decision_label(final_include),
            category_tags=final_tags,
            canonical_theme=final_theme,
        )

    return [_ensure_final_fields(review) for review in updated_reviews], stats


def _is_hard_exclusion_zone(review: ProcessedReview) -> bool:
    stripped = review.normalized_text.strip()
    if not stripped:
        return True
    if all(not char.isalnum() and not _is_hangul_char(char) for char in stripped):
        return True
    if review.hangul_ratio < 0.20:
        return True
    if review.is_low_quality:
        return True
    if review.is_profanity_only:
        return True
    return False


def _has_semantic_signal(review: ProcessedReview) -> bool:
    if review.category_tags:
        return True
    compact = review.normalized_text.replace(" ", "")
    if len(compact) >= 15 and review.hangul_ratio >= 0.20:
        return True
    return False


def _has_uncertainty_signal(review: ProcessedReview) -> bool:
    if review.ambiguity_flags:
        return True
    if not review.category_tags and review.included_in_analysis:
        return True
    if review.rule_confidence < 0.70:
        return True
    return False


def _is_hangul_char(char: str) -> bool:
    return "가" <= char <= "힣"


def _decision_label(included: bool) -> str:
    return "include" if included else "exclude"


def _mark_rule_fallback(
    review: ProcessedReview,
    *,
    llm_attempted: bool,
    llm_decision: str | None = None,
    llm_confidence: float | None = None,
) -> ProcessedReview:
    return replace(
        review,
        llm_invoked=llm_attempted,
        llm_decision=llm_decision,
        llm_confidence=llm_confidence,
        final_decision_source="rule",
        final_decision=_decision_label(review.included_in_analysis),
    )


def _ensure_final_fields(review: ProcessedReview) -> ProcessedReview:
    if review.final_decision in {"include", "exclude"}:
        return review
    return replace(
        review,
        final_decision=_decision_label(review.included_in_analysis),
    )

