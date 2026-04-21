"""Tests for template-based summary generation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.summarize import build_summary
from report.models.schemas import IssueSignal


class SummaryGenerationTests(unittest.TestCase):
    def test_build_summary_returns_all_required_sections(self):
        issue_signals = {
            "performance": IssueSignal(
                mention_count=5,
                negative_ratio=0.8,
                recent_trend="up",
                experienced_player_share=0.6,
                themes=["최적화 문제"],
                sample_reviews=["최적화가 별로라 프레임 드랍이 심함"],
            ),
            "graphics": IssueSignal(
                mention_count=3,
                negative_ratio=0.2,
                recent_trend="flat",
                experienced_player_share=0.4,
                themes=["그래픽 품질"],
                sample_reviews=["그래픽이 생각보다 좋음"],
            ),
        }

        summary = build_summary(
            issue_signals,
            sample_size_tier="small",
            trend_status="ready",
        )

        self.assertEqual(
            set(summary),
            {"what_players_like", "what_players_dislike", "recent_change", "fit_for", "risks"},
        )
        self.assertIn("graphics", summary["what_players_like"])
        self.assertIn("performance", summary["what_players_dislike"])
        self.assertIn("증가", summary["recent_change"])

    def test_build_summary_mentions_limited_trend_when_needed(self):
        issue_signals = {
            "bugs": IssueSignal(
                mention_count=2,
                negative_ratio=1.0,
                recent_trend="limited",
                experienced_player_share=0.5,
                themes=["충돌 및 튕김"],
                sample_reviews=["보스전에서 계속 튕김"],
            )
        }

        summary = build_summary(
            issue_signals,
            sample_size_tier="very_small",
            trend_status="limited",
        )

        self.assertIn("표본", summary["what_players_dislike"])
        self.assertIn("제한", summary["recent_change"])
        self.assertIn("단정", summary["risks"])


if __name__ == "__main__":
    unittest.main()


