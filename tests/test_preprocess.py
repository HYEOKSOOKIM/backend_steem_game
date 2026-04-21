"""Tests for deterministic preprocessing rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.rules import clean_markup_text
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
        playtime_forever=120.0,
        playtime_at_review_hours=2.0,
        num_reviews=3,
        author_steamid="steamid-1",
    )


class PreprocessReviewTests(unittest.TestCase):
    def test_includes_korean_feedback_review(self):
        review = preprocess_review(
            make_raw_review("그래픽은 좋은데 최적화가 안 좋아 프레임이 자주 떨어짐")
        )

        self.assertTrue(review.included_in_analysis)
        self.assertEqual(review.rule_decision, "include")

    def test_excludes_non_korean_review(self):
        review = preprocess_review(
            make_raw_review("matchmaking is broken and the server crashes every night")
        )

        self.assertFalse(review.included_in_analysis)
        self.assertEqual(review.rule_decision, "exclude_non_korean")

    def test_excludes_low_quality_review(self):
        review = preprocess_review(make_raw_review("짱"))

        self.assertFalse(review.included_in_analysis)
        self.assertTrue(review.is_low_quality)
        self.assertEqual(review.rule_decision, "exclude_low_quality")

    def test_excludes_profanity_only_review(self):
        review = preprocess_review(make_raw_review("쓰레기 망겜"))

        self.assertFalse(review.included_in_analysis)
        self.assertTrue(review.is_profanity_only)
        self.assertEqual(review.rule_decision, "exclude_low_quality")

    def test_keeps_profane_but_meaningful_feedback(self):
        review = preprocess_review(
            make_raw_review("쓰레기 같은 최적화 때문에 프레임이 계속 떨어짐")
        )

        self.assertTrue(review.included_in_analysis)
        self.assertFalse(review.is_profanity_only)
        self.assertIn("ambiguous_profanity", review.ambiguity_flags)

    def test_flags_ambiguous_review(self):
        review = preprocess_review(
            make_raw_review("그래픽은 좋은데 조작은 별로여서 좀 애매함")
        )

        self.assertTrue(review.included_in_analysis)
        self.assertIn("ambiguous_sentiment", review.ambiguity_flags)

    def test_flags_included_but_unclassified_review(self):
        review = preprocess_review(
            make_raw_review("이 게임은 진짜 완벽하네")
        )

        self.assertTrue(review.included_in_analysis)
        self.assertEqual(review.rule_decision, "include")
        self.assertEqual(review.category_tags, [])
        self.assertIn("unclassified_included", review.ambiguity_flags)

    def test_markup_cleaning_boundary_cases(self):
        cases = [
            ("진짜 재밌다 <3", "진짜 재밌다 <3"),
            ("2 < 3 이고 5 > 1", "2 < 3 이고 5 > 1"),
            ("<b>전투</b>는 좋고 <br> 최적화는 별로", "전투 는 좋고 최적화는 별로"),
            ("<script>alert('x')</script> 게임은 재밌음", "게임은 재밌음"),
            ("[h3]장점[/h3] 타격감 좋음", "장점 타격감 좋음"),
            ("[url=https://example.com]링크[/url] 때문에 튕김", "링크 때문에 튕김"),
            ("코드: <div class='x'>if(a<b){...}</div>", "코드: if(a<b){...}"),
            ("&lt;b&gt;가짜태그&lt;/b&gt;", "가짜태그"),
            ("<<< 진짜 구림 >>>", "<<< 진짜 구림 >>>"),
            ("<p>[b]혼합[/b] 마크업</p>", "혼합 마크업"),
        ]

        for index, (raw, expected) in enumerate(cases, start=1):
            with self.subTest(case=index):
                self.assertEqual(clean_markup_text(raw), expected)

    def test_preprocess_applies_markup_cleaning_before_normalization(self):
        review = preprocess_review(
            make_raw_review("<b>최적화</b>는 안 좋고 [h3]버그[/h3]가 많음")
        )

        self.assertIn("최적화", review.normalized_text)
        self.assertIn("버그", review.normalized_text)
        self.assertNotIn("<b>", review.normalized_text)
        self.assertNotIn("[h3]", review.normalized_text)


if __name__ == "__main__":
    unittest.main()


