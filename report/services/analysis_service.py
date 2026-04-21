"""Service helpers that assemble and persist analysis results."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from report.analysis.preprocess import preprocess_reviews
from report.analysis.summarize import build_summary
from report.analysis.themes import collect_top_themes, extract_review_themes
from report.analysis.trends import (
    build_weekly_category_counts,
    calculate_sample_size_tier,
    detect_category_trend,
)
from report.models.schemas import AnalysisResult, IssueSignal, ProcessedReview, RawReview
from report.storage.file_store import FileStore

WARNING_MESSAGES = {
    "base": "이 결과는 수집된 한국어 리뷰 표본을 기준으로 합니다.",
    "small_sample": "분석 포함 리뷰 수가 적어 해석에 주의가 필요합니다.",
    "limited_trend": "최근 리뷰 수가 적어 추세 해석이 제한됩니다.",
}


def enrich_processed_reviews(processed_reviews: list[ProcessedReview]) -> list[ProcessedReview]:
    """Attach canonical theme hints to already processed reviews."""
    enriched_reviews: list[ProcessedReview] = []

    for review in processed_reviews:
        if not review.included_in_analysis:
            enriched_reviews.append(review)
            continue
        if review.canonical_theme is not None:
            enriched_reviews.append(review)
            continue

        review_themes = extract_review_themes(review)
        canonical_theme = next(iter(review_themes.values()), None)
        enriched_reviews.append(replace(review, canonical_theme=canonical_theme))

    return enriched_reviews


def _collect_warnings(sample_size_tier: str, issue_signals: dict[str, IssueSignal]) -> list[str]:
    warnings = [WARNING_MESSAGES["base"]]

    if sample_size_tier in {"very_small", "small"}:
        warnings.append(WARNING_MESSAGES["small_sample"])

    if any(signal.recent_trend == "limited" for signal in issue_signals.values()):
        warnings.append(WARNING_MESSAGES["limited_trend"])

    return warnings


def _build_issue_signals(processed_reviews: list[ProcessedReview]) -> dict[str, IssueSignal]:
    included_reviews = [review for review in processed_reviews if review.included_in_analysis]
    weekly_counts = build_weekly_category_counts(included_reviews)

    categories = sorted(
        {
            category
            for review in included_reviews
            for category in review.category_tags
        }
    )

    issue_signals: dict[str, IssueSignal] = {}
    for category in categories:
        tagged_reviews = [
            review for review in included_reviews if category in review.category_tags
        ]
        negative_count = sum(1 for review in tagged_reviews if not review.voted_up)
        experienced_count = sum(
            1
            for review in tagged_reviews
            if (review.playtime_at_review_hours or 0.0) >= 2.0
        )
        top_themes = collect_top_themes(included_reviews, category=category, limit=3)
        trend = detect_category_trend(weekly_counts, category)

        issue_signals[category] = IssueSignal(
            mention_count=len(tagged_reviews),
            negative_ratio=(
                negative_count / len(tagged_reviews) if tagged_reviews else 0.0
            ),
            recent_trend=str(trend["recent_trend"]),
            experienced_player_share=(
                experienced_count / len(tagged_reviews) if tagged_reviews else 0.0
            ),
            themes=top_themes,
            sample_reviews=[review.review_text for review in tagged_reviews[:2]],
        )

    return issue_signals


def build_analysis_result_from_processed(
    processed_reviews: list[ProcessedReview],
    *,
    appid: int,
) -> AnalysisResult:
    """Assemble a final analysis snapshot from processed reviews."""
    included_reviews = [review for review in processed_reviews if review.included_in_analysis]
    sample_size_tier = calculate_sample_size_tier(len(included_reviews))
    issue_signals = _build_issue_signals(processed_reviews)

    overall_trend_status = (
        "limited"
        if any(signal.recent_trend == "limited" for signal in issue_signals.values())
        else "ready"
    )
    trend_reason = (
        "insufficient_recent_volume" if overall_trend_status == "limited" else None
    )
    warnings = _collect_warnings(sample_size_tier, issue_signals)
    summary = build_summary(
        issue_signals,
        sample_size_tier=sample_size_tier,
        trend_status=overall_trend_status,
    )

    return AnalysisResult(
        appid=appid,
        sample_size_tier=sample_size_tier,
        trend_status=overall_trend_status,
        trend_reason=trend_reason,
        warnings=warnings,
        issue_signals=issue_signals,
        summary=summary,
    )


def analyze_reviews(raw_reviews: list[RawReview], appid: int) -> tuple[AnalysisResult, list[ProcessedReview]]:
    """Run the deterministic pipeline and assemble an analysis result."""
    processed_reviews = enrich_processed_reviews(preprocess_reviews(raw_reviews))
    result = build_analysis_result_from_processed(processed_reviews, appid=appid)

    return result, processed_reviews


def run_and_persist_analysis(
    raw_reviews: list[RawReview],
    appid: int,
    data_root: str | Path,
    game_name: str | None = None,
) -> tuple[AnalysisResult, list[ProcessedReview]]:
    """Persist raw, processed, and analysis artifacts for one appid."""
    result, processed_reviews = analyze_reviews(raw_reviews, appid=appid)
    store = FileStore(data_root)

    store.write_raw_reviews(
        appid,
        [review.to_dict() for review in raw_reviews],
        game_name=game_name,
    )
    store.write_processed_reviews(
        appid,
        [review.to_dict() for review in processed_reviews],
        game_name=game_name,
    )
    store.write_analysis_result(appid, result.to_dict(), game_name=game_name)

    return result, processed_reviews

