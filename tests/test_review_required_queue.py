"""Tests for review-required Markdown queue export."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.export_review_required_queue import build_review_required_markdown


class ReviewRequiredQueueTests(unittest.TestCase):
    def test_build_review_required_markdown_includes_actions_and_holds(self):
        payload = {
            "mode": "dry_run",
            "appids": [1],
            "rows": [
                {
                    "appid": 1,
                    "game_name": "Test Game",
                    "status": "repairable_with_holds",
                    "semantic_status": "fail",
                    "failure_count": 2,
                    "critical_failure_count": 1,
                    "report_path": "data/report/report/1.json",
                    "actions": [
                        {
                            "action": "rewrite_from_best_claim",
                            "failure_type": "theme_drift",
                            "field": "top_risks[1]",
                            "claim_id": "risk_1",
                            "safety_level": "review_required",
                            "reason": "display 문장이 claim과 약하게 연결됩니다.",
                            "current_text": "기존 문장",
                            "replacement_text": {
                                "title": "새 제목",
                                "summary": "새 설명",
                            },
                            "phrases_used": ["리뷰 표현"],
                        },
                        {
                            "action": "drop_duplicate_claim",
                            "safety_level": "safe",
                            "claim_id": "risk_2",
                        },
                    ],
                    "holds": [
                        {
                            "hold_type": "unsupported_claim_hold",
                            "failure_type": "unsupported_claim",
                            "field": "top_strengths[1]",
                            "claim_id": None,
                            "reason": "근거가 없습니다.",
                            "text": "막힌 문장",
                        }
                    ],
                }
            ],
        }

        markdown = build_review_required_markdown(payload)

        self.assertIn("# Review Required Queue", markdown)
        self.assertIn("## Test Game (1)", markdown)
        self.assertIn("#### Action 1: `top_risks[1]`", markdown)
        self.assertIn("제목: 새 제목", markdown)
        self.assertIn("리뷰 표현", markdown)
        self.assertIn("#### Hold 1: `top_strengths[1]`", markdown)
        self.assertNotIn("drop_duplicate_claim", markdown)


if __name__ == "__main__":
    unittest.main()
