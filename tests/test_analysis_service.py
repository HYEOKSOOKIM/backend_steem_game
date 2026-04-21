"""Tests for analysis result assembly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.models.schemas import RawReview
from report.services.analysis_service import analyze_reviews


def make_raw_review(
    review_id: str,
    review_text: str,
    *,
    voted_up: bool = False,
    timestamp_created: int = 1704067200,
    playtime_at_review_hours: float | None = 4.0,
) -> RawReview:
    return RawReview(
        review_id=review_id,
        appid=570,
        review_text=review_text,
        voted_up=voted_up,
        timestamp_created=timestamp_created,
        timestamp_updated=timestamp_created,
        playtime_forever=240.0,
        playtime_at_review_hours=playtime_at_review_hours,
        num_reviews=5,
        author_steamid=f"steamid-{review_id}",
    )


class AnalysisServiceTests(unittest.TestCase):
    def test_analyze_reviews_assembles_issue_signals_and_summary(self):
        raw_reviews = [
            make_raw_review("r1", "최적화가 별로라 프레임이 자주 떨어짐", voted_up=False),
            make_raw_review("r2", "그래픽은 좋은데 조작이 답답하고 매칭이 느림", voted_up=False),
            make_raw_review("r3", "짱", voted_up=True),
        ]

        result, processed_reviews = analyze_reviews(raw_reviews, appid=570)

        self.assertEqual(result.appid, 570)
        self.assertEqual(result.sample_size_tier, "very_small")
        self.assertEqual(result.trend_status, "limited")
        self.assertIn("performance", result.issue_signals)
        self.assertIn("graphics", result.issue_signals)
        self.assertTrue(result.warnings)
        self.assertIn("what_players_dislike", result.summary)
        self.assertTrue(result.summary["what_players_dislike"])
        self.assertEqual(len(processed_reviews), 3)

    def test_analyze_reviews_sets_canonical_theme_on_processed_reviews(self):
        raw_reviews = [
            make_raw_review("r1", "최적화가 별로라 프레임이 자주 떨어짐"),
            make_raw_review("r2", "보스전에서 튕기고 게임이 꺼짐"),
        ]

        _result, processed_reviews = analyze_reviews(raw_reviews, appid=570)

        included_reviews = [review for review in processed_reviews if review.included_in_analysis]
        canonical_themes = {review.canonical_theme for review in included_reviews}

        self.assertIn("최적화 문제", canonical_themes)
        self.assertIn("실행 불가 / 튕김", canonical_themes)

    def test_analyze_reviews_computes_negative_ratio_and_experienced_share(self):
        raw_reviews = [
            make_raw_review(
                "r1",
                "최적화가 별로라 프레임이 자주 떨어짐",
                voted_up=False,
                playtime_at_review_hours=5.0,
            ),
            make_raw_review(
                "r2",
                "최적화 이슈는 있지만 그래픽은 괜찮음",
                voted_up=True,
                playtime_at_review_hours=1.0,
            ),
        ]

        result, _processed_reviews = analyze_reviews(raw_reviews, appid=570)

        performance_signal = result.issue_signals["performance"]
        self.assertEqual(performance_signal.mention_count, 2)
        self.assertAlmostEqual(performance_signal.negative_ratio, 0.5)
        self.assertAlmostEqual(performance_signal.experienced_player_share, 0.5)


if __name__ == "__main__":
    unittest.main()


