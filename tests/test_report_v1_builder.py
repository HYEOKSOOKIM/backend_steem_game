"""Tests for report.v1 builder output contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.report_v1_builder import build_report_v1_from_artifacts


def _make_review(review_id: int) -> dict[str, object]:
    return {
        "review_id": str(review_id),
        "included_in_analysis": True,
        "voted_up": False,
        "review_text": "Performance got worse after the update.",
        "category_tags": ["performance"],
        "playtime_at_review_hours": 12.0,
        "num_reviews": 3,
        "timestamp_created": 1713700000,
    }


class ReportV1BuilderTests(unittest.TestCase):
    def test_final_recommendation_inputs_match_decision_and_trend(self):
        processed_reviews = [_make_review(i) for i in range(60)]
        analysis = {
            "generated_at": "2026-04-22T00:00:00+00:00",
            "sample_size_tier": "medium",
            "trend_status": "ready",
            "issue_signals": {
                "performance": {
                    "mention_count": 100,
                    "negative_ratio": 0.8,
                    "recent_trend": "up",
                    "themes": ["frame drop"],
                }
            },
        }

        report = build_report_v1_from_artifacts(
            appid=2456740,
            metadata={},
            analysis=analysis,
            processed_reviews=processed_reviews,
        )

        decision_score = float(report["snapshot"]["decision_score"])
        decision_confidence = float(report["snapshot"]["decision_confidence"])
        trend_direction = str(report["trend"]["summary"]["direction"])
        recommendation_inputs = report["final_recommendation"]["inputs"]

        self.assertAlmostEqual(float(recommendation_inputs["risk_index"]), 0.8, places=4)
        self.assertAlmostEqual(
            float(recommendation_inputs["risk_index"]),
            round(1.0 - (decision_score / 100.0), 4),
            places=4,
        )
        self.assertEqual(float(recommendation_inputs["confidence"]), decision_confidence)
        self.assertEqual(str(recommendation_inputs["trend_direction"]), trend_direction)
        self.assertEqual(str(report["final_recommendation"]["label"]), str(report["snapshot"]["decision_label"]))
        self.assertEqual(trend_direction, "worsening")

    def test_final_recommendation_trend_direction_defaults_stable(self):
        report = build_report_v1_from_artifacts(
            appid=2456740,
            metadata={},
            analysis={},
            processed_reviews=[],
        )

        self.assertEqual(str(report["trend"]["summary"]["direction"]), "stable")
        self.assertEqual(
            str(report["final_recommendation"]["inputs"]["trend_direction"]),
            "stable",
        )
        self.assertAlmostEqual(
            float(report["final_recommendation"]["inputs"]["risk_index"]),
            0.5,
            places=4,
        )


if __name__ == "__main__":
    unittest.main()

