"""Tests for evidence block generation rules in report.v1 builder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.report_v1_builder import build_report_v1_from_artifacts


class ReportV1EvidenceBlocksTests(unittest.TestCase):
    def test_evidence_blocks_use_top_categories_and_negative_first(self):
        long_text = "x" * 300
        processed_reviews = [
            {
                "review_id": "p-neg-1",
                "included_in_analysis": True,
                "voted_up": False,
                "review_text": long_text,
                "category_tags": ["performance"],
                "playtime_at_review_hours": 50.0,
                "num_reviews": 120,
                "timestamp_created": 1713700000,
            },
            {
                "review_id": "p-pos-1",
                "included_in_analysis": True,
                "voted_up": True,
                "review_text": "Performance was mostly smooth for me.",
                "category_tags": ["performance"],
                "playtime_at_review_hours": None,
                "num_reviews": None,
                "timestamp_created": None,
            },
            {
                "review_id": "g-neg-1",
                "included_in_analysis": True,
                "voted_up": False,
                "review_text": "Gameplay pacing drags in mid game.",
                "category_tags": ["gameplay"],
                "playtime_at_review_hours": 10.0,
                "num_reviews": 10,
                "timestamp_created": 1713600000,
            },
            {
                "review_id": "g-pos-1",
                "included_in_analysis": True,
                "voted_up": True,
                "review_text": "Combat is very satisfying.",
                "category_tags": ["gameplay"],
                "playtime_at_review_hours": 8.0,
                "num_reviews": 2,
                "timestamp_created": 1713500000,
            },
            {
                "review_id": "u-neg-empty",
                "included_in_analysis": True,
                "voted_up": False,
                "review_text": "    ",
                "category_tags": ["ui"],
                "playtime_at_review_hours": 5.0,
                "num_reviews": 3,
                "timestamp_created": 1713400000,
            },
            {
                "review_id": "u-pos-1",
                "included_in_analysis": True,
                "voted_up": True,
                "review_text": "UI is clear enough once you learn it.",
                "category_tags": ["ui"],
                "playtime_at_review_hours": 3.0,
                "num_reviews": 1,
                "timestamp_created": 1713300000,
            },
            {
                "review_id": "n-neg-1",
                "included_in_analysis": True,
                "voted_up": False,
                "review_text": "Narrative is too predictable.",
                "category_tags": ["narrative"],
                "playtime_at_review_hours": 6.0,
                "num_reviews": 4,
                "timestamp_created": 1713200000,
            },
        ]

        analysis = {
            "generated_at": "2026-04-22T00:00:00+00:00",
            "issue_signals": {
                "performance": {"mention_count": 100, "negative_ratio": 0.8, "recent_trend": "up", "themes": ["frame drop"]},
                "gameplay": {"mention_count": 80, "negative_ratio": 0.4, "recent_trend": "flat", "themes": ["combat"]},
                "ui": {"mention_count": 70, "negative_ratio": 0.55, "recent_trend": "flat", "themes": ["menus"]},
                "narrative": {"mention_count": 10, "negative_ratio": 0.65, "recent_trend": "down", "themes": ["story"]},
            },
        }

        report = build_report_v1_from_artifacts(
            appid=2456740,
            metadata={},
            analysis=analysis,
            processed_reviews=processed_reviews,
        )

        blocks = report["evidence_blocks"]
        self.assertTrue(len(blocks) > 0)
        categories = {block["category"] for block in blocks}
        self.assertIn("performance", categories)
        self.assertIn("gameplay", categories)
        self.assertIn("ui", categories)
        self.assertNotIn("narrative", categories)

        performance_blocks = [block for block in blocks if block["category"] == "performance"]
        self.assertGreaterEqual(len(performance_blocks), 2)
        self.assertEqual(performance_blocks[0]["polarity"], "negative")
        self.assertEqual(performance_blocks[1]["polarity"], "positive")

        self.assertEqual(len(performance_blocks[0]["quote"]), 220)
        self.assertEqual(performance_blocks[1]["review_meta"]["created_at"], None)
        self.assertEqual(performance_blocks[1]["review_meta"]["playtime_minutes"], 0)
        self.assertEqual(performance_blocks[1]["review_meta"]["votes_up"], 0)

    def test_evidence_blocks_skip_empty_quotes(self):
        processed_reviews = [
            {
                "review_id": "1",
                "included_in_analysis": True,
                "voted_up": False,
                "review_text": "   ",
                "category_tags": ["performance"],
                "playtime_at_review_hours": 3.0,
                "num_reviews": 5,
            },
            {
                "review_id": "2",
                "included_in_analysis": True,
                "voted_up": True,
                "review_text": "Solid performance overall.",
                "category_tags": ["performance"],
                "playtime_at_review_hours": 2.0,
                "num_reviews": 1,
            },
        ]
        analysis = {
            "issue_signals": {
                "performance": {"mention_count": 20, "negative_ratio": 0.6, "recent_trend": "flat", "themes": ["frame drop"]}
            }
        }

        report = build_report_v1_from_artifacts(
            appid=2456740,
            metadata={},
            analysis=analysis,
            processed_reviews=processed_reviews,
        )

        blocks = report["evidence_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["polarity"], "positive")
        self.assertEqual(blocks[0]["quote"], "Solid performance overall.")


if __name__ == "__main__":
    unittest.main()

