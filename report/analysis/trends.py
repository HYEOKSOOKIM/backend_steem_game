"""Trend analysis helpers for processed review data."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from report.models.schemas import ProcessedReview

MIN_WINDOW_REVIEW_COUNT = 5
MIN_ABSOLUTE_DELTA = 3
WINDOW_SIZE_WEEKS = 4


def calculate_sample_size_tier(review_count: int) -> str:
    """Return the sample size tier defined in the analysis policy."""
    if review_count <= 0:
        return "empty"
    if review_count <= 29:
        return "very_small"
    if review_count <= 99:
        return "small"
    if review_count <= 499:
        return "medium"
    return "large"


def week_bucket_from_timestamp(timestamp_created: int) -> str:
    """Convert a UNIX timestamp into an ISO week bucket."""
    dt = datetime.fromtimestamp(timestamp_created, tz=UTC)
    iso_year, iso_week, _weekday = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def build_weekly_category_counts(
    processed_reviews: list[ProcessedReview],
) -> list[dict[str, int | str]]:
    """Aggregate multi-label category mentions by ISO week bucket."""
    buckets: dict[str, Counter[str]] = defaultdict(Counter)

    for review in processed_reviews:
        if not review.included_in_analysis:
            continue

        bucket = week_bucket_from_timestamp(review.timestamp_created)
        for category in review.category_tags:
            buckets[bucket][category] += 1

    weekly_points: list[dict[str, int | str]] = []
    for bucket in sorted(buckets):
        point: dict[str, int | str] = {"bucket": bucket}
        point.update(buckets[bucket])
        weekly_points.append(point)

    return weekly_points


def _window_counts(
    weekly_counts: list[dict[str, int | str]],
    category: str,
) -> tuple[int, int, int, int]:
    if not weekly_counts:
        return 0, 0, 0, 0

    recent_points = weekly_counts[-WINDOW_SIZE_WEEKS:]
    previous_points = weekly_counts[-(WINDOW_SIZE_WEEKS * 2) : -WINDOW_SIZE_WEEKS]

    recent_count = sum(int(point.get(category, 0)) for point in recent_points)
    prior_count = sum(int(point.get(category, 0)) for point in previous_points)
    recent_window_review_count = sum(
        sum(
            int(value)
            for key, value in point.items()
            if key != "bucket"
        )
        for point in recent_points
    )
    previous_window_review_count = sum(
        sum(
            int(value)
            for key, value in point.items()
            if key != "bucket"
        )
        for point in previous_points
    )
    return (
        recent_count,
        prior_count,
        recent_window_review_count,
        previous_window_review_count,
    )


def detect_category_trend(
    weekly_counts: list[dict[str, int | str]],
    category: str,
) -> dict[str, int | str | None]:
    """Return trend metadata for one category over recent and previous windows."""
    (
        recent_count,
        prior_count,
        recent_window_review_count,
        previous_window_review_count,
    ) = _window_counts(weekly_counts, category)

    if (
        recent_window_review_count < MIN_WINDOW_REVIEW_COUNT
        or previous_window_review_count < MIN_WINDOW_REVIEW_COUNT
    ):
        return {
            "recent_trend": "limited",
            "trend_status": "limited",
            "trend_reason": "insufficient_recent_volume",
            "recent_count": recent_count,
            "prior_count": prior_count,
            "recent_window_review_count": recent_window_review_count,
            "previous_window_review_count": previous_window_review_count,
        }

    if (
        recent_count >= MIN_WINDOW_REVIEW_COUNT
        and recent_count >= prior_count * 1.5
        and recent_count - prior_count >= MIN_ABSOLUTE_DELTA
    ):
        return {
            "recent_trend": "up",
            "trend_status": "ready",
            "trend_reason": None,
            "recent_count": recent_count,
            "prior_count": prior_count,
            "recent_window_review_count": recent_window_review_count,
            "previous_window_review_count": previous_window_review_count,
        }

    if (
        prior_count >= MIN_WINDOW_REVIEW_COUNT
        and prior_count >= max(recent_count, 1) * 1.5
        and prior_count - recent_count >= MIN_ABSOLUTE_DELTA
    ):
        return {
            "recent_trend": "down",
            "trend_status": "ready",
            "trend_reason": None,
            "recent_count": recent_count,
            "prior_count": prior_count,
            "recent_window_review_count": recent_window_review_count,
            "previous_window_review_count": previous_window_review_count,
        }

    return {
        "recent_trend": "flat",
        "trend_status": "ready",
        "trend_reason": None,
        "recent_count": recent_count,
        "prior_count": prior_count,
        "recent_window_review_count": recent_window_review_count,
        "previous_window_review_count": previous_window_review_count,
    }

