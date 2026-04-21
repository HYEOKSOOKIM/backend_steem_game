"""Tests for selective offline LLM fallback behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.llm_fallback import LLMFallbackConfig, apply_selective_llm_fallback
from report.models.schemas import ProcessedReview
from report.services.llm_classifier import LLMClassificationResult


class StubClassifier:
    def __init__(self, decisions: list[LLMClassificationResult | None]):
        self._decisions = list(decisions)
        self.call_count = 0

    @property
    def available(self) -> bool:
        return True

    def classify(self, review, *, timeout_seconds=20, retry_limit=2):
        del review, timeout_seconds, retry_limit
        self.call_count += 1
        if self._decisions:
            return self._decisions.pop(0)
        return None


def make_processed(
    *,
    review_id: str,
    normalized_text: str,
    included_in_analysis: bool = True,
    hangul_ratio: float = 0.95,
    is_low_quality: bool = False,
    is_profanity_only: bool = False,
    ambiguity_flags: list[str] | None = None,
    category_tags: list[str] | None = None,
    rule_confidence: float = 0.55,
) -> ProcessedReview:
    return ProcessedReview(
        review_id=review_id,
        appid=570,
        review_text=normalized_text,
        normalized_text=normalized_text,
        voted_up=False,
        timestamp_created=0,
        timestamp_updated=0,
        playtime_forever=10.0,
        playtime_at_review_hours=10.0,
        num_reviews=2,
        author_steamid="steamid",
        hangul_ratio=hangul_ratio,
        is_low_quality=is_low_quality,
        is_profanity_only=is_profanity_only,
        ambiguity_flags=list(ambiguity_flags or []),
        included_in_analysis=included_in_analysis,
        rule_decision="include" if included_in_analysis else "exclude_non_korean",
        rule_confidence=rule_confidence,
        llm_invoked=False,
        llm_decision=None,
        llm_confidence=None,
        final_decision_source="rule",
        final_decision="include" if included_in_analysis else "exclude",
        category_tags=list(category_tags or []),
        canonical_theme=None,
    )


class LLMFallbackTests(unittest.TestCase):
    def test_skips_hard_exclusion_zone(self):
        reviews = [
            make_processed(
                review_id="hard",
                normalized_text="ㅋㅋㅋ",
                hangul_ratio=0.95,
                is_low_quality=True,
                included_in_analysis=False,
                rule_confidence=0.98,
            ),
            make_processed(
                review_id="candidate",
                normalized_text="그래픽은 좋은데 프레임 드랍이 심해서 불편해요",
                ambiguity_flags=["ambiguous_sentiment"],
                category_tags=[],
                rule_confidence=0.50,
            ),
        ]
        classifier = StubClassifier(
            [
                LLMClassificationResult(
                    included_in_analysis=True,
                    category_tags=["performance"],
                    canonical_theme="최적화 문제",
                    confidence=0.90,
                )
            ]
        )
        updated, stats = apply_selective_llm_fallback(
            reviews,
            classifier=classifier,
            config=LLMFallbackConfig(enabled=True, max_llm_reviews=50),
        )

        self.assertEqual(classifier.call_count, 1)
        self.assertEqual(stats.skipped_hard_exclusion, 1)
        self.assertTrue(updated[1].llm_invoked)
        self.assertEqual(updated[1].final_decision_source, "llm")
        self.assertEqual(updated[1].category_tags, ["performance"])

    def test_uses_cache_for_identical_text(self):
        text = "매칭은 좋은데 최적화 문제가 계속 반복돼요"
        reviews = [
            make_processed(
                review_id="a",
                normalized_text=text,
                ambiguity_flags=["ambiguous_category"],
                category_tags=[],
                rule_confidence=0.60,
            ),
            make_processed(
                review_id="b",
                normalized_text=text,
                ambiguity_flags=["ambiguous_category"],
                category_tags=[],
                rule_confidence=0.60,
            ),
        ]
        classifier = StubClassifier(
            [
                LLMClassificationResult(
                    included_in_analysis=True,
                    category_tags=["matchmaking"],
                    canonical_theme="매칭 품질",
                    confidence=0.88,
                )
            ]
        )
        updated, stats = apply_selective_llm_fallback(
            reviews,
            classifier=classifier,
            config=LLMFallbackConfig(enabled=True, max_llm_reviews=50),
        )

        self.assertEqual(classifier.call_count, 1)
        self.assertEqual(stats.cache_hits, 1)
        self.assertEqual(updated[0].category_tags, ["matchmaking"])
        self.assertEqual(updated[1].category_tags, ["matchmaking"])

    def test_low_confidence_falls_back_to_rule(self):
        review = make_processed(
            review_id="low",
            normalized_text="요즘은 나쁘진 않은데 전반적으로 장단점이 섞여서 꽤 애매합니다",
            ambiguity_flags=["ambiguous_sentiment"],
            category_tags=[],
            rule_confidence=0.52,
        )
        classifier = StubClassifier(
            [
                LLMClassificationResult(
                    included_in_analysis=False,
                    category_tags=["bugs"],
                    canonical_theme="충돌",
                    confidence=0.45,
                )
            ]
        )
        updated, stats = apply_selective_llm_fallback(
            [review],
            classifier=classifier,
            config=LLMFallbackConfig(enabled=True, min_confidence=0.70),
        )

        self.assertEqual(stats.low_confidence, 1)
        self.assertTrue(updated[0].llm_invoked)
        self.assertEqual(updated[0].final_decision_source, "rule")
        self.assertEqual(updated[0].final_decision, "include")
        self.assertEqual(updated[0].llm_decision, "exclude")
        self.assertAlmostEqual(updated[0].llm_confidence or 0.0, 0.45, places=3)

    def test_respects_max_llm_reviews_cap(self):
        reviews = [
            make_processed(
                review_id="1",
                normalized_text="콘텐츠는 좋은데 최적화가 불안정함",
                ambiguity_flags=["ambiguous_category"],
                category_tags=[],
                rule_confidence=0.50,
            ),
            make_processed(
                review_id="2",
                normalized_text="초반은 괜찮지만 서버 상태가 애매함",
                ambiguity_flags=["ambiguous_category"],
                category_tags=[],
                rule_confidence=0.50,
            ),
        ]
        classifier = StubClassifier(
            [
                LLMClassificationResult(
                    included_in_analysis=True,
                    category_tags=["performance"],
                    canonical_theme="최적화 문제",
                    confidence=0.93,
                )
            ]
        )
        updated, stats = apply_selective_llm_fallback(
            reviews,
            classifier=classifier,
            config=LLMFallbackConfig(enabled=True, max_llm_reviews=1),
        )

        self.assertEqual(stats.invoked, 1)
        self.assertEqual(classifier.call_count, 1)
        self.assertTrue(updated[0].llm_invoked)
        self.assertFalse(updated[1].llm_invoked)
        self.assertEqual(updated[1].final_decision_source, "rule")


if __name__ == "__main__":
    unittest.main()


