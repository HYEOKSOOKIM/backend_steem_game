"""Tests for rule-based multi-label categorization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.categorize import extract_category_tags
from report.analysis.preprocess import preprocess_review
from report.models.schemas import RawReview


def make_raw_review(review_text: str) -> RawReview:
    return RawReview(
        review_id="review-1",
        appid=570,
        review_text=review_text,
        voted_up=False,
        timestamp_created=0,
        timestamp_updated=0,
        playtime_forever=240.0,
        playtime_at_review_hours=4.0,
        num_reviews=5,
        author_steamid="steamid-1",
    )


class CategorizeTests(unittest.TestCase):
    def test_extracts_single_category(self):
        tags = extract_category_tags("최적화가 별로라 프레임이 자주 떨어짐")

        self.assertEqual(tags, ["performance"])

    def test_extracts_bug_category(self):
        tags = extract_category_tags("보스전에서 튕기고 데이터가 날아감")

        self.assertEqual(tags, ["save_progression"])

    def test_extracts_multi_label_categories(self):
        tags = extract_category_tags("그래픽은 좋은데 조작이 답답하고 매칭이 느림")

        self.assertEqual(tags, ["graphics", "multiplayer", "controls"])

    def test_extracts_localization_and_story(self):
        tags = extract_category_tags("번역이 어색해서 스토리 몰입감이 깨짐")

        self.assertEqual(tags, ["bugs", "story", "localization"])

    def test_returns_empty_when_no_category_matches(self):
        tags = extract_category_tags("그냥 무난함")

        self.assertEqual(tags, [])

    def test_preprocess_assigns_categories_only_when_included(self):
        included = preprocess_review(
            make_raw_review("그래픽은 좋은데 조작이 답답하고 매칭이 느림")
        )
        excluded = preprocess_review(make_raw_review("짱"))

        self.assertEqual(included.category_tags, ["graphics", "multiplayer", "controls"])
        self.assertEqual(excluded.category_tags, [])


if __name__ == "__main__":
    unittest.main()


