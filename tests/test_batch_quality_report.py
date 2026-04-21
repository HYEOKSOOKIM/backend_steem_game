"""Tests for normalization benchmark quality report helpers."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = APP_DIR / "scripts"
TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_tmp_batch_quality"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from batch_quality_report import (
    build_batch_report,
    build_bucket_summaries,
    build_game_summary_record,
    build_notes,
    calculate_ratios,
    extract_sample_reviews,
    load_cohort_from_file,
    summarize_processed_reviews,
    write_json_report,
    write_markdown_report,
)


def make_processed_reviews() -> list[dict]:
    return [
        {
            "review_id": "r1",
            "included_in_analysis": True,
            "rule_decision": "include",
            "category_tags": [],
            "canonical_theme": None,
            "ambiguity_flags": ["unclassified_included"],
            "normalized_text": "할게 없음",
            "voted_up": False,
            "playtime_at_review_hours": 3.2,
            "timestamp_created": 6,
        },
        {
            "review_id": "r2",
            "included_in_analysis": True,
            "rule_decision": "include",
            "category_tags": ["performance"],
            "canonical_theme": None,
            "ambiguity_flags": [],
            "normalized_text": "프레임이 너무 떨어짐",
            "voted_up": False,
            "playtime_at_review_hours": 10.5,
            "timestamp_created": 5,
        },
        {
            "review_id": "r3",
            "included_in_analysis": True,
            "rule_decision": "include",
            "category_tags": ["controls"],
            "canonical_theme": "조작감 문제",
            "ambiguity_flags": ["ambiguous_sentiment"],
            "normalized_text": "재밌긴 한데 조작이 불편함",
            "voted_up": True,
            "playtime_at_review_hours": 12.0,
            "timestamp_created": 4,
        },
        {
            "review_id": "r4",
            "included_in_analysis": False,
            "rule_decision": "exclude_non_korean",
            "category_tags": [],
            "canonical_theme": None,
            "ambiguity_flags": [],
            "normalized_text": "this game is awesome",
            "hangul_ratio": 0.0,
            "timestamp_created": 3,
        },
        {
            "review_id": "r5",
            "included_in_analysis": False,
            "rule_decision": "exclude_low_quality",
            "category_tags": [],
            "canonical_theme": None,
            "ambiguity_flags": [],
            "normalized_text": ".",
            "timestamp_created": 2,
        },
        {
            "review_id": "r6",
            "included_in_analysis": False,
            "rule_decision": "exclude_profanity_only",
            "category_tags": [],
            "canonical_theme": None,
            "ambiguity_flags": [],
            "normalized_text": "쓰레기겜",
            "timestamp_created": 1,
        },
    ]


class BatchQualityReportTests(unittest.TestCase):
    def tearDown(self):
        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)

    def test_summarize_processed_reviews_counts_expected_fields(self):
        summary = summarize_processed_reviews(make_processed_reviews())

        self.assertEqual(summary["included_review_count"], 3)
        self.assertEqual(summary["excluded_low_quality_count"], 1)
        self.assertEqual(summary["excluded_non_korean_count"], 1)
        self.assertEqual(summary["excluded_profanity_only_count"], 1)
        self.assertEqual(summary["unclassified_included_count"], 1)
        self.assertEqual(summary["canonical_theme_missing_count"], 1)
        self.assertEqual(summary["ambiguity_flagged_count"], 2)
        self.assertEqual(summary["category_counter"]["performance"], 1)
        self.assertEqual(summary["category_counter"]["controls"], 1)
        self.assertEqual(summary["ambiguity_flag_counter"]["unclassified_included"], 1)
        self.assertEqual(summary["ambiguity_flag_counter"]["ambiguous_sentiment"], 1)

    def test_calculate_ratios_handles_expected_denominators(self):
        summary = summarize_processed_reviews(make_processed_reviews())

        ratios = calculate_ratios(
            raw_review_count=6,
            included_review_count=summary["included_review_count"],
            summary_counts=summary,
        )

        self.assertAlmostEqual(ratios["included_ratio"], 0.5)
        self.assertAlmostEqual(ratios["unclassified_included_ratio"], 0.3333)
        self.assertAlmostEqual(ratios["canonical_theme_missing_ratio"], 0.3333)
        self.assertAlmostEqual(ratios["ambiguity_flagged_ratio"], 0.3333)

    def test_extract_sample_reviews_returns_expected_buckets(self):
        samples = extract_sample_reviews(make_processed_reviews())

        self.assertEqual(len(samples["top_unclassified_samples"]), 1)
        self.assertEqual(len(samples["top_theme_missing_samples"]), 1)
        self.assertEqual(len(samples["top_ambiguity_samples"]), 2)
        self.assertEqual(len(samples["top_non_korean_samples"]), 1)
        self.assertEqual(len(samples["top_low_quality_samples"]), 1)
        self.assertEqual(samples["top_unclassified_samples"][0]["review_id"], "r1")
        self.assertEqual(samples["top_theme_missing_samples"][0]["review_id"], "r2")

    def test_build_notes_applies_threshold_rules(self):
        summary_record = {
            "raw_review_count": 6,
            "included_review_count": 3,
            "excluded_low_quality_count": 1,
            "excluded_non_korean_count": 1,
            "unclassified_included_ratio": 0.3333,
            "canonical_theme_missing_ratio": 0.3333,
            "ambiguity_flagged_ratio": 0.3333,
            "all_mode_cap_reached": False,
        }

        notes = build_notes(summary_record)

        self.assertIn("카테고리 확장 또는 정규화 사전 보강 필요", notes)
        self.assertIn("대표 테마 해석 신뢰도가 낮음", notes)
        self.assertIn("규칙 경계 점검 필요", notes)
        self.assertIn("한국어 필터 점검 필요", notes)
        self.assertIn("저품질 규칙 또는 장르 특성 점검 필요", notes)
        self.assertIn("표본 수가 작아 해석에 주의 필요", notes)

    def test_build_game_summary_record_uses_inputs_and_notes(self):
        cohort_item = {
            "appid": 570,
            "game_name": "테스트 게임",
            "primary_bucket": "액션 / 슈터",
            "secondary_tags": ["정식 출시"],
            "expected_failure_pattern": "테스트 패턴",
        }
        game_inputs = {
            "raw": [{"review_id": str(i)} for i in range(6)],
            "processed": make_processed_reviews(),
            "analysis": {
                "fetched_pages": 2,
                "fetched_review_count": 6,
                "fetch_timeout_seconds": 20,
                "fetch_filter": "recent",
                "all_mode_page_cap": 200,
                "all_mode_cap_reached": False,
                "review_pages": "all",
            },
            "metadata": {
                "name": "테스트 게임",
                "genres": ["Action"],
                "price_model": "paid",
                "release_stage": "released",
            },
        }

        summary_record = build_game_summary_record(cohort_item, game_inputs)

        self.assertEqual(summary_record["appid"], 570)
        self.assertEqual(summary_record["raw_review_count"], 6)
        self.assertEqual(summary_record["included_review_count"], 3)
        self.assertEqual(summary_record["fetched_pages"], 2)
        self.assertEqual(summary_record["price_model"], "paid")
        self.assertTrue(summary_record["notes"])

    def test_write_json_and_markdown_reports_create_files(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        summary_record = {
            "appid": 570,
            "game_name": "테스트 게임",
            "primary_bucket": "액션 / 슈터",
            "raw_review_count": 6,
            "included_review_count": 3,
            "unclassified_included_ratio": 0.3333,
            "canonical_theme_missing_ratio": 0.3333,
            "ambiguity_flagged_ratio": 0.3333,
            "notes": ["카테고리 확장 필요"],
        }
        batch_report = build_batch_report(
            cohort=[{"appid": 570}],
            summary_records=[summary_record],
            skipped_games=[],
        )

        json_path = TEST_OUTPUT_DIR / "batch_quality_report.json"
        md_path = TEST_OUTPUT_DIR / "batch_quality_report.md"
        write_json_report(batch_report, json_path)
        write_markdown_report(batch_report, md_path)

        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["cohort_size"], 1)
        self.assertIn("정규화 벤치마크 리포트", md_path.read_text(encoding="utf-8"))


    def test_load_cohort_from_file_reads_custom_cohort_json(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cohort_path = TEST_OUTPUT_DIR / "cohort.json"
        cohort_path.write_text(
            json.dumps(
                [
                    {
                        "appid": 570,
                        "game_name": "테스트 게임",
                        "primary_bucket": "액션 / 슈터",
                        "secondary_tags": ["정식 출시"],
                        "expected_failure_pattern": "테스트 패턴",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        cohort = load_cohort_from_file(cohort_path)

        self.assertEqual(len(cohort), 1)
        self.assertEqual(cohort[0]["appid"], 570)
        self.assertEqual(cohort[0]["primary_bucket"], "액션 / 슈터")

    def test_build_bucket_summaries_groups_records_by_bucket(self):
        summary_records = [
            {
                "appid": 1,
                "game_name": "A",
                "primary_bucket": "액션 / 슈터",
                "unclassified_included_ratio": 0.4,
                "canonical_theme_missing_ratio": 0.1,
                "ambiguity_flagged_ratio": 0.2,
            },
            {
                "appid": 2,
                "game_name": "B",
                "primary_bucket": "액션 / 슈터",
                "unclassified_included_ratio": 0.2,
                "canonical_theme_missing_ratio": 0.3,
                "ambiguity_flagged_ratio": 0.4,
            },
        ]

        bucket_summaries = build_bucket_summaries(summary_records)

        self.assertEqual(len(bucket_summaries), 1)
        self.assertEqual(bucket_summaries[0]["game_count"], 2)
        self.assertAlmostEqual(bucket_summaries[0]["avg_unclassified_included_ratio"], 0.3)
        self.assertAlmostEqual(bucket_summaries[0]["avg_canonical_theme_missing_ratio"], 0.2)
        self.assertAlmostEqual(bucket_summaries[0]["avg_ambiguity_flagged_ratio"], 0.3)

    def test_write_markdown_report_includes_bucket_summary_section(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        batch_report = {
            "generated_at": "2026-04-13T10:00:00+09:00",
            "cohort_size": 1,
            "processed_game_count": 1,
            "skipped_game_count": 0,
            "summary_records": [
                {
                    "appid": 570,
                    "game_name": "테스트 게임",
                    "primary_bucket": "액션 / 슈터",
                    "raw_review_count": 6,
                    "included_review_count": 3,
                    "unclassified_included_ratio": 0.3333,
                    "canonical_theme_missing_ratio": 0.3333,
                    "ambiguity_flagged_ratio": 0.3333,
                    "notes": ["카테고리 확장 필요"],
                }
            ],
            "skipped_games": [],
            "outliers": {
                "high_unclassified": [],
                "high_theme_missing": [],
                "high_ambiguity": [],
                "cap_reached": [],
            },
            "bucket_summaries": [
                {
                    "primary_bucket": "액션 / 슈터",
                    "game_count": 1,
                    "avg_unclassified_included_ratio": 0.3333,
                    "avg_canonical_theme_missing_ratio": 0.3333,
                    "avg_ambiguity_flagged_ratio": 0.3333,
                    "games": [{"appid": 570, "game_name": "테스트 게임"}],
                }
            ],
        }

        md_path = TEST_OUTPUT_DIR / "bucket_summary.md"
        write_markdown_report(batch_report, md_path)

        markdown = md_path.read_text(encoding="utf-8")
        self.assertIn("버킷별 실패 패턴 요약", markdown)
        self.assertIn("액션 / 슈터", markdown)


if __name__ == "__main__":
    unittest.main()
