"""Tests for review trend analysis helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.trends import (
    build_weekly_category_counts,
    calculate_sample_size_tier,
    detect_category_trend,
)
from report.models.schemas import ProcessedReview


def make_processed_review(
    review_id: str,
    timestamp_created: int,
    category_tags: list[str],
    *,
    included_in_analysis: bool = True,
) -> ProcessedReview:
    return ProcessedReview(
        review_id=review_id,
        appid=570,
        review_text="테스트 리뷰",
        normalized_text="테스트 리뷰",
        voted_up=False,
        timestamp_created=timestamp_created,
        timestamp_updated=timestamp_created,
        playtime_forever=120.0,
        playtime_at_review_hours=2.0,
        num_reviews=3,
        author_steamid=f"steamid-{review_id}",
        hangul_ratio=1.0,
        is_low_quality=False,
        is_profanity_only=False,
        ambiguity_flags=[],
        included_in_analysis=included_in_analysis,
        rule_decision="include",
        llm_invoked=False,
        llm_decision=None,
        final_decision_source="rule",
        category_tags=category_tags,
        canonical_theme=None,
    )


class TrendAnalysisTests(unittest.TestCase):
    def test_calculate_sample_size_tier(self):
        self.assertEqual(calculate_sample_size_tier(0), "empty")
        self.assertEqual(calculate_sample_size_tier(12), "very_small")
        self.assertEqual(calculate_sample_size_tier(50), "small")
        self.assertEqual(calculate_sample_size_tier(200), "medium")
        self.assertEqual(calculate_sample_size_tier(700), "large")

    def test_build_weekly_category_counts_aggregates_multi_label_reviews(self):
        reviews = [
            make_processed_review("r1", 1704067200, ["performance", "controls"]),
            make_processed_review("r2", 1704067200, ["performance"]),
            make_processed_review("r3", 1704672000, ["bugs"]),
            make_processed_review("r4", 1704672000, ["performance"], included_in_analysis=False),
        ]

        weekly_counts = build_weekly_category_counts(reviews)

        self.assertEqual(len(weekly_counts), 2)
        self.assertEqual(weekly_counts[0]["performance"], 2)
        self.assertEqual(weekly_counts[0]["controls"], 1)
        self.assertEqual(weekly_counts[1]["bugs"], 1)

    def test_detect_category_trend_returns_limited_when_window_volume_is_small(self):
        weekly_counts = [
            {"bucket": "2026-W01", "performance": 1},
            {"bucket": "2026-W02", "performance": 1},
            {"bucket": "2026-W03", "performance": 1},
            {"bucket": "2026-W04", "performance": 1},
            {"bucket": "2026-W05", "performance": 2},
            {"bucket": "2026-W06", "performance": 1},
            {"bucket": "2026-W07", "performance": 1},
            {"bucket": "2026-W08", "performance": 1},
        ]

        trend = detect_category_trend(weekly_counts, "performance")

        self.assertEqual(trend["trend_status"], "limited")
        self.assertEqual(trend["recent_trend"], "limited")

    def test_detect_category_trend_returns_up_for_significant_spike(self):
        weekly_counts = [
            {"bucket": "2026-W01", "performance": 1, "bugs": 1},
            {"bucket": "2026-W02", "performance": 1, "bugs": 1},
            {"bucket": "2026-W03", "performance": 1, "bugs": 1},
            {"bucket": "2026-W04", "performance": 1, "bugs": 1},
            {"bucket": "2026-W05", "performance": 3, "bugs": 3},
            {"bucket": "2026-W06", "performance": 3, "bugs": 3},
            {"bucket": "2026-W07", "performance": 4, "bugs": 3},
            {"bucket": "2026-W08", "performance": 4, "bugs": 3},
        ]

        trend = detect_category_trend(weekly_counts, "performance")

        self.assertEqual(trend["trend_status"], "ready")
        self.assertEqual(trend["recent_trend"], "up")

    def test_detect_category_trend_returns_flat_when_change_is_not_large_enough(self):
        weekly_counts = [
            {"bucket": "2026-W01", "bugs": 2, "performance": 2},
            {"bucket": "2026-W02", "bugs": 2, "performance": 2},
            {"bucket": "2026-W03", "bugs": 2, "performance": 2},
            {"bucket": "2026-W04", "bugs": 2, "performance": 2},
            {"bucket": "2026-W05", "bugs": 2, "performance": 2},
            {"bucket": "2026-W06", "bugs": 2, "performance": 2},
            {"bucket": "2026-W07", "bugs": 3, "performance": 2},
            {"bucket": "2026-W08", "bugs": 2, "performance": 2},
        ]

        trend = detect_category_trend(weekly_counts, "bugs")

        self.assertEqual(trend["trend_status"], "ready")
        self.assertEqual(trend["recent_trend"], "flat")


if __name__ == "__main__":
    unittest.main()


