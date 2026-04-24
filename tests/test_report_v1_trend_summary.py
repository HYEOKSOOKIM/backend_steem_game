"""Tests for trend direction rules in report.v1 builder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.report_v1_builder import build_report_v1_from_artifacts


def _build_report(issue_signals: dict[str, dict[str, object]]) -> dict[str, object]:
    return build_report_v1_from_artifacts(
        appid=2456740,
        metadata={},
        analysis={
            "generated_at": "2026-04-22T00:00:00+00:00",
            "issue_signals": issue_signals,
        },
        processed_reviews=[],
    )


class ReportV1TrendSummaryTests(unittest.TestCase):
    def test_direction_limited_has_highest_priority(self):
        report = _build_report(
            {
                "performance": {"mention_count": 10, "negative_ratio": 0.7, "recent_trend": "up"},
                "content": {"mention_count": 10, "negative_ratio": 0.4, "recent_trend": "down"},
                "bugs": {"mention_count": 5, "negative_ratio": 0.8, "recent_trend": "limited"},
            }
        )

        summary = report["trend"]["summary"]
        self.assertEqual(summary["direction"], "limited")
        self.assertEqual(summary["up_categories"], 1)
        self.assertEqual(summary["down_categories"], 1)
        self.assertEqual(summary["limited_categories"], 1)

    def test_direction_worsening_when_up_is_greater_than_down(self):
        report = _build_report(
            {
                "performance": {"mention_count": 10, "negative_ratio": 0.7, "recent_trend": "up"},
                "bugs": {"mention_count": 8, "negative_ratio": 0.8, "recent_trend": "up"},
                "content": {"mention_count": 7, "negative_ratio": 0.4, "recent_trend": "down"},
                "ui": {"mention_count": 5, "negative_ratio": 0.5, "recent_trend": "flat"},
            }
        )

        summary = report["trend"]["summary"]
        self.assertEqual(summary["direction"], "worsening")
        self.assertEqual(summary["up_categories"], 2)
        self.assertEqual(summary["down_categories"], 1)
        self.assertEqual(summary["flat_categories"], 1)
        self.assertEqual(report["final_recommendation"]["inputs"]["trend_direction"], "worsening")

    def test_direction_improving_when_down_is_greater_than_up(self):
        report = _build_report(
            {
                "performance": {"mention_count": 10, "negative_ratio": 0.7, "recent_trend": "down"},
                "bugs": {"mention_count": 8, "negative_ratio": 0.8, "recent_trend": "down"},
                "content": {"mention_count": 7, "negative_ratio": 0.4, "recent_trend": "up"},
            }
        )

        summary = report["trend"]["summary"]
        self.assertEqual(summary["direction"], "improving")
        self.assertEqual(summary["up_categories"], 1)
        self.assertEqual(summary["down_categories"], 2)
        self.assertEqual(report["final_recommendation"]["inputs"]["trend_direction"], "improving")

    def test_direction_stable_when_up_and_down_are_equal(self):
        report = _build_report(
            {
                "performance": {"mention_count": 10, "negative_ratio": 0.7, "recent_trend": "UP"},
                "content": {"mention_count": 10, "negative_ratio": 0.4, "recent_trend": " down "},
                "ui": {"mention_count": 5, "negative_ratio": 0.5, "recent_trend": "unknown"},
            }
        )

        summary = report["trend"]["summary"]
        self.assertEqual(summary["direction"], "stable")
        self.assertEqual(summary["up_categories"], 1)
        self.assertEqual(summary["down_categories"], 1)
        self.assertEqual(summary["flat_categories"], 1)
        self.assertEqual(summary["limited_categories"], 0)


if __name__ == "__main__":
    unittest.main()

