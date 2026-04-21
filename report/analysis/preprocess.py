"""Preprocessing pipeline for raw Steam reviews."""

from __future__ import annotations

from report.analysis.categorize import extract_category_tags
from report.analysis.rules import (
    calculate_hangul_ratio,
    calculate_rule_confidence,
    clean_markup_text,
    detect_ambiguity_flags,
    is_low_quality_review,
    is_profanity_only_review,
    normalize_text,
)
from report.models.schemas import ProcessedReview, RawReview


def preprocess_review(raw_review: RawReview) -> ProcessedReview:
    """Run deterministic preprocessing on a single raw review."""
    cleaned_text = clean_markup_text(raw_review.review_text)
    normalized_text = normalize_text(cleaned_text)
    hangul_ratio = calculate_hangul_ratio(normalized_text)
    low_quality = is_low_quality_review(normalized_text)
    profanity_only = is_profanity_only_review(normalized_text)
    ambiguity_flags = detect_ambiguity_flags(
        normalized_text,
        hangul_ratio=hangul_ratio,
        is_low_quality=low_quality,
        is_profanity_only=profanity_only,
    )

    if low_quality:
        rule_decision = "exclude_low_quality"
        included_in_analysis = False
    elif profanity_only:
        rule_decision = "exclude_profanity_only"
        included_in_analysis = False
    elif hangul_ratio < 0.20:
        rule_decision = "exclude_non_korean"
        included_in_analysis = False
    else:
        rule_decision = "include"
        included_in_analysis = True

    category_tags = extract_category_tags(normalized_text) if included_in_analysis else []
    if included_in_analysis and not category_tags and "unclassified_included" not in ambiguity_flags:
        ambiguity_flags.append("unclassified_included")
    rule_confidence = calculate_rule_confidence(
        text=normalized_text,
        hangul_ratio=hangul_ratio,
        is_low_quality=low_quality,
        is_profanity_only=profanity_only,
        category_tags=category_tags,
        ambiguity_flags=ambiguity_flags,
    )
    final_decision = "include" if included_in_analysis else "exclude"

    return ProcessedReview(
        review_id=raw_review.review_id,
        appid=raw_review.appid,
        review_text=raw_review.review_text,
        normalized_text=normalized_text,
        voted_up=raw_review.voted_up,
        timestamp_created=raw_review.timestamp_created,
        timestamp_updated=raw_review.timestamp_updated,
        playtime_forever=raw_review.playtime_forever,
        playtime_at_review_hours=raw_review.playtime_at_review_hours,
        num_reviews=raw_review.num_reviews,
        author_steamid=raw_review.author_steamid,
        hangul_ratio=hangul_ratio,
        is_low_quality=low_quality,
        is_profanity_only=profanity_only,
        ambiguity_flags=ambiguity_flags,
        included_in_analysis=included_in_analysis,
        rule_decision=rule_decision,
        rule_confidence=rule_confidence,
        llm_invoked=False,
        llm_decision=None,
        llm_confidence=None,
        final_decision_source="rule",
        final_decision=final_decision,
        category_tags=category_tags,
        canonical_theme=None,
    )


def preprocess_reviews(raw_reviews: list[RawReview]) -> list[ProcessedReview]:
    """Process a batch of raw reviews."""
    return [preprocess_review(raw_review) for raw_review in raw_reviews]

