"""Additional tests for buyer-facing release-gate behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.report_view import build_consumer_report_from_snapshot


class ReportViewReleaseGateTests(unittest.TestCase):
    def test_forbidden_labels_are_replaced_in_titles(self):
        metadata = {
            "appid": 2456740,
            "name": "inZOI",
            "genres": ["Simulation"],
            "release_stage": "released",
        }
        analysis = {
            "issue_signals": {
                "difficulty": {
                    "mention_count": 30,
                    "negative_ratio": 0.20,
                    "recent_trend": "flat",
                    "themes": ["조작 / 규칙 학습 난이도"],
                    "sample_reviews": [],
                },
                "performance": {
                    "mention_count": 30,
                    "negative_ratio": 0.70,
                    "recent_trend": "up",
                    "themes": ["최적화 문제"],
                    "sample_reviews": [],
                },
            }
        }
        processed = [
            {
                "review_id": "x1",
                "review_text": "조작이 어렵지만 익숙해지면 재미가 살아납니다.",
                "included_in_analysis": True,
                "category_tags": ["difficulty"],
                "voted_up": True,
            },
            {
                "review_id": "x2",
                "review_text": "전투가 손에 붙고 플레이가 재밌습니다.",
                "included_in_analysis": True,
                "category_tags": ["difficulty"],
                "voted_up": True,
            },
            {
                "review_id": "x3",
                "review_text": "프레임이 떨어져 전투 중 끊김이 있습니다.",
                "included_in_analysis": True,
                "category_tags": ["performance"],
                "voted_up": False,
            },
            {
                "review_id": "x4",
                "review_text": "최적화 문제가 남아 있어 답답합니다.",
                "included_in_analysis": True,
                "category_tags": ["performance"],
                "voted_up": False,
            },
        ]

        report = build_consumer_report_from_snapshot(
            appid=2456740,
            metadata=metadata,
            analysis=analysis,
            processed_reviews=processed,
            pipeline_run_id="replace-test",
            source_review_count=4,
        )
        report_display = report.get("report_display", {})
        titles = []
        for item in list(report_display.get("top_strengths", []) or []):
            if isinstance(item, dict):
                titles.append(str(item.get("title", "")))
        for item in list(report_display.get("top_risks", []) or []):
            if isinstance(item, dict):
                titles.append(str(item.get("title", "")))
        for block in list((report.get("evidence_sections", {}) or {}).get("strengths", []) or []):
            if isinstance(block, dict):
                titles.append(str(block.get("title", "")))
        for block in list((report.get("evidence_sections", {}) or {}).get("risks", []) or []):
            if isinstance(block, dict):
                titles.append(str(block.get("title", "")))

        joined = " ".join(titles)
        self.assertNotIn("조작 / 규칙 학습 난이도", joined)
        self.assertNotIn("최적화 문제", joined)

    def test_guaranteed_fill_keeps_risk_section_non_empty(self):
        metadata = {
            "appid": 413150,
            "name": "Stardew Valley",
            "genres": ["Simulation"],
            "release_stage": "released",
        }
        analysis = {
            "issue_signals": {
                "controls": {
                    "mention_count": 22,
                    "negative_ratio": 0.12,
                    "recent_trend": "flat",
                    "themes": ["조작 / 규칙 학습 난이도"],
                    "sample_reviews": [],
                },
                "story": {
                    "mention_count": 40,
                    "negative_ratio": 0.05,
                    "recent_trend": "flat",
                    "themes": ["스토리 / 서사 몰입"],
                    "sample_reviews": [],
                },
            }
        }
        processed = [
            {
                "review_id": "g1",
                "review_text": "스토리 몰입이 좋아 계속 플레이하게 됩니다.",
                "included_in_analysis": True,
                "category_tags": ["story"],
                "voted_up": True,
            },
            {
                "review_id": "g2",
                "review_text": "조작이 불편해서 적응이 필요합니다.",
                "included_in_analysis": True,
                "category_tags": ["controls"],
                "voted_up": False,
            },
            {
                "review_id": "g3",
                "review_text": "입력 반응이 늦어 답답한 구간이 있습니다.",
                "included_in_analysis": True,
                "category_tags": ["controls"],
                "voted_up": False,
            },
            {
                "review_id": "g4",
                "review_text": "조작을 익히면 플레이가 편해집니다.",
                "included_in_analysis": True,
                "category_tags": ["controls"],
                "voted_up": True,
            },
        ]

        report = build_consumer_report_from_snapshot(
            appid=413150,
            metadata=metadata,
            analysis=analysis,
            processed_reviews=processed,
            pipeline_run_id="guaranteed-fill-test",
            source_review_count=4,
        )
        evidence_sections = report.get("evidence_sections", {})
        strengths = list(evidence_sections.get("strengths", []) or [])
        risks = list(evidence_sections.get("risks", []) or [])
        self.assertTrue(strengths)
        self.assertTrue(risks)
        self.assertGreaterEqual(len(risks[0].get("evidence_snippets", [])), 2)


if __name__ == "__main__":
    unittest.main()



