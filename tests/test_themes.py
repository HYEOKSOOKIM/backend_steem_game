"""Tests for keyword and canonical theme extraction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.preprocess import preprocess_review
from report.analysis.themes import collect_top_keywords, collect_top_themes, extract_review_themes
from report.models.schemas import RawReview


def make_raw_review(review_id: str, review_text: str) -> RawReview:
    return RawReview(
        review_id=review_id,
        appid=570,
        review_text=review_text,
        voted_up=False,
        timestamp_created=0,
        timestamp_updated=0,
        playtime_forever=240.0,
        playtime_at_review_hours=4.0,
        num_reviews=5,
        author_steamid=f"steamid-{review_id}",
    )


class ThemeExtractionTests(unittest.TestCase):
    def test_extract_review_themes_returns_category_theme_mapping(self):
        review = preprocess_review(
            make_raw_review("r1", "그래픽은 좋은데 조작이 답답하고 매칭이 느림")
        )

        themes = extract_review_themes(review)

        self.assertEqual(themes["graphics"], "그래픽 / 비주얼 호평")
        self.assertEqual(themes["controls"], "조작감 문제")
        self.assertEqual(themes["multiplayer"], "매칭 / 서버 문제")

    def test_collect_top_keywords_returns_frequent_keywords(self):
        reviews = [
            preprocess_review(
                make_raw_review("r1", "최적화가 별로라 프레임이 자주 떨어짐")
            ),
            preprocess_review(
                make_raw_review("r2", "최적화 문제 때문에 프레임이 자주 끊김")
            ),
        ]

        keywords = collect_top_keywords(reviews, limit=3)

        self.assertIn("최적화가", keywords)

    def test_collect_top_themes_aggregates_by_category(self):
        reviews = [
            preprocess_review(
                make_raw_review("r1", "최적화가 별로라 프레임이 자주 떨어짐")
            ),
            preprocess_review(
                make_raw_review("r2", "최적화 문제 때문에 렉이 자주 발생함")
            ),
            preprocess_review(
                make_raw_review("r3", "그래픽은 좋은데 조작이 너무 답답함")
            ),
        ]

        top_themes = collect_top_themes(reviews, category="performance", limit=2)

        self.assertEqual(top_themes, ["최적화 문제"])


if __name__ == "__main__":
    unittest.main()


