"""Tests for read-only user routes and admin-only ingest helpers."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_tmp_api_flow"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.api.routes import (
    list_demo_games,
    load_analysis_result,
    load_game_metadata,
    load_processed_reviews,
    load_raw_reviews,
    load_report,
    run_admin_ingest,
)
from report.storage.file_store import FileStore


def write_demo_catalog(root: Path, appids: list[int]) -> None:
    catalog_dir = root / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        {"appid": appid, "name": f"Game {appid}", "enabled_for_demo": True}
        for appid in appids
    ]
    (catalog_dir / "demo_games.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_snapshot_files(root: Path, appid: int) -> None:
    store = FileStore(root)
    store.write_analysis_result(
        appid,
        {
            "appid": appid,
            "sample_size_tier": "medium",
            "trend_status": "ready",
            "warnings": [],
            "issue_signals": {
                "performance": {
                    "mention_count": 20,
                    "negative_ratio": 0.7,
                    "recent_trend": "up",
                    "experienced_player_share": 0.8,
                    "themes": ["최적화 문제"],
                    "sample_reviews": ["업데이트 이후 프레임 드랍이 심해졌습니다."],
                },
                "gameplay": {
                    "mention_count": 25,
                    "negative_ratio": 0.2,
                    "recent_trend": "flat",
                    "experienced_player_share": 0.7,
                    "themes": ["전투 손맛"],
                    "sample_reviews": ["전투가 재밌어서 계속 하게 됩니다."],
                },
            },
            "summary": {},
        },
        game_name=f"Game {appid}",
    )
    store.write_game_metadata(
        appid,
        {
            "appid": appid,
            "name": f"Game {appid}",
            "genres": ["Action"],
            "release_stage": "released",
        },
        game_name=f"Game {appid}",
    )
    store.write_raw_reviews(
        appid,
        [{"review_id": "1", "appid": appid, "review_text": "raw"}],
        game_name=f"Game {appid}",
    )
    store.write_processed_reviews(
        appid,
        [
            {
                "review_id": "1",
                "appid": appid,
                "review_text": "전투는 재밌지만 프레임이 불안정합니다.",
                "voted_up": False,
                "included_in_analysis": True,
                "category_tags": ["performance", "gameplay"],
                "playtime_at_review_hours": 12.3,
            }
        ],
        game_name=f"Game {appid}",
    )


class ApiFlowTests(unittest.TestCase):
    def tearDown(self):
        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)

    def test_list_demo_games_returns_predefined_catalog_only(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740, 1049590])
        write_snapshot_files(TEST_OUTPUT_DIR, 2456740)

        games = list_demo_games(data_root=TEST_OUTPUT_DIR)

        self.assertEqual([game["appid"] for game in games], [1049590, 2456740])
        self.assertFalse(games[0]["report_ready"])
        self.assertTrue(games[1]["report_ready"])

    def test_load_report_returns_stored_consumer_report_when_available(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740])
        write_snapshot_files(TEST_OUTPUT_DIR, 2456740)
        store = FileStore(TEST_OUTPUT_DIR)
        store.write_report_view(
            2456740,
            {
                "report_plan": {
                    "decision_anchor": {
                        "buy_recommendation": "buy_now",
                        "primary_reason_ids": ["str_1"],
                        "rationale_short": "핵심 재미가 안정적으로 유지됩니다.",
                    },
                    "section_blueprint": {
                        "strength_block_count": 2,
                        "risk_block_count": 2,
                        "evidence_per_block": 2,
                    },
                    "theme_priorities": {
                        "strengths": [{"reason_id": "str_1", "aspect": "gameplay", "theme": "전투 손맛"}],
                        "risks": [{"reason_id": "risk_1", "aspect": "performance", "theme": "프레임 저하"}],
                    },
                },
                "report_display": {
                    "headline": "테스트 헤드라인",
                    "buy_recommendation": "buy_now",
                    "buy_timing_summary": "지금 구매해도 괜찮습니다.",
                    "good_for": ["A"],
                    "not_good_for": ["B"],
                    "top_strengths": [
                        {"title": "전투", "summary": "전투가 재밌다는 의견이 반복됩니다."},
                        {"title": "콘텐츠", "summary": "플레이 볼륨이 충분하다는 의견이 있습니다."},
                    ],
                    "top_risks": [
                        {"title": "성능", "summary": "일부 구간 프레임 저하가 있습니다."},
                        {"title": "버그", "summary": "간헐적 버그 제보가 있습니다."},
                    ],
                    "recent_state": {"status": "stable", "summary": "안정"},
                },
                "evidence_sections": {
                    "strengths": [
                        {
                            "block_id": "str_1",
                            "title": "전투 손맛",
                            "why_it_matters": "초반 몰입을 빠르게 끌어올립니다.",
                            "explanation": "전투 타격감 호평이 반복됩니다.",
                            "stance": "positive",
                            "consensus_level": "high",
                            "mention_count": 20,
                            "evidence_snippets": ["전투가 타격감이 좋아요.", "전투가 계속 재밌습니다."],
                        }
                    ],
                    "risks": [
                        {
                            "block_id": "risk_1",
                            "title": "성능",
                            "why_it_matters": "전투 흐름이 자주 끊기면 만족도가 크게 떨어질 수 있습니다.",
                            "explanation": "프레임 저하 불만이 반복됩니다.",
                            "stance": "negative",
                            "consensus_level": "high",
                            "mention_count": 20,
                            "evidence_snippets": ["프레임이 떨어집니다.", "전투 중 끊김이 있습니다."],
                        }
                    ],
                },
            },
            game_name="Game 2456740",
        )

        report = load_report(2456740, data_root=TEST_OUTPUT_DIR)

        self.assertEqual(report["report_display"]["headline"], "테스트 헤드라인")
        self.assertEqual(report["report_display"]["buy_recommendation"], "buy_now")

    def test_load_report_builds_from_snapshot_without_running_analysis(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740])
        write_snapshot_files(TEST_OUTPUT_DIR, 2456740)

        with patch("report.api.routes.run_offline_pipeline_for_appid") as run_pipeline:
            report = load_report(2456740, data_root=TEST_OUTPUT_DIR)
            run_pipeline.assert_not_called()

        self.assertIn("report_plan", report)
        self.assertIn("report_display", report)
        self.assertIn("evidence_sections", report)
        self.assertIn("headline", report["report_display"])
        self.assertIn("top_risks", report["report_display"])
        self.assertIn("top_strengths", report["report_display"])

    def test_user_read_helpers_reject_non_demo_appid(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740])
        write_snapshot_files(TEST_OUTPUT_DIR, 2456740)

        with self.assertRaises(ValueError):
            load_report(999999, data_root=TEST_OUTPUT_DIR)
        with self.assertRaises(ValueError):
            load_analysis_result(999999, data_root=TEST_OUTPUT_DIR)
        with self.assertRaises(ValueError):
            load_game_metadata(999999, data_root=TEST_OUTPUT_DIR)
        with self.assertRaises(ValueError):
            load_raw_reviews(999999, data_root=TEST_OUTPUT_DIR)
        with self.assertRaises(ValueError):
            load_processed_reviews(999999, data_root=TEST_OUTPUT_DIR)

    def test_admin_ingest_uses_offline_pipeline_entrypoint(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740])

        with patch("report.api.routes.run_offline_pipeline_for_appid") as run_pipeline:
            run_pipeline.return_value = {"appid": 2456740, "pipeline_run_id": "run-1"}
            result = run_admin_ingest(
                {"appid": 2456740, "review_pages": 4, "use_llm_fallback": False},
                data_root=TEST_OUTPUT_DIR,
            )

        self.assertEqual(result["appid"], 2456740)
        run_pipeline.assert_called_once()

    def test_admin_ingest_rejects_non_demo_appid(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        write_demo_catalog(TEST_OUTPUT_DIR, [2456740])

        with self.assertRaises(ValueError):
            run_admin_ingest({"appid": 1049590}, data_root=TEST_OUTPUT_DIR)


if __name__ == "__main__":
    unittest.main()


