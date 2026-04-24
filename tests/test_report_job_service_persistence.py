"""Tests for file-backed job store persistence."""

from __future__ import annotations

import shutil
import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_tmp_job_store"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services import report_job_service
from report.storage.file_store import FileStore


class ReportJobServicePersistenceTests(unittest.TestCase):
    def tearDown(self):
        report_job_service._clear_job_store_cache_for_test()
        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)

    def test_create_job_is_recovered_as_failed_after_restart(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)

        created = report_job_service.create_report_job({"appid": 2456740}, data_root=data_root)
        job_id = str(created["job_id"])

        self.assertTrue((TEST_OUTPUT_DIR / "jobs" / "report_jobs.json").exists())

        report_job_service._clear_job_store_cache_for_test()
        loaded = report_job_service.get_report_job(job_id, data_root=data_root)

        self.assertEqual(loaded["job_id"], job_id)
        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["error_code"], "interrupted_by_restart")
        self.assertEqual(int(loaded["params"]["appid"]), 2456740)

    def test_failed_status_is_persisted(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)
        created = report_job_service.create_report_job({"appid": 2456740}, data_root=data_root)
        job_id = str(created["job_id"])

        with patch.object(
            report_job_service,
            "run_offline_pipeline_for_appid",
            side_effect=RuntimeError("pipeline exploded"),
        ):
            report_job_service.run_report_job(job_id)

        report_job_service._clear_job_store_cache_for_test()
        loaded = report_job_service.get_report_job(job_id, data_root=data_root)

        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["error_code"], "pipeline_runtime_error")
        self.assertIn("pipeline exploded", str(loaded["error_message"]))

    def test_running_job_is_marked_failed_after_restart_recovery(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)
        store = FileStore(data_root)
        store.write_report_jobs(
            {
                "schema_version": "report.jobs.v1",
                "saved_at": "2026-04-22T00:00:00+00:00",
                "jobs": {
                    "job-run-1": {
                        "job_id": "job-run-1",
                        "status": "running",
                        "progress": 35,
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "started_at": "2026-04-22T00:00:05+00:00",
                        "finished_at": None,
                        "error_code": None,
                        "error_message": None,
                        "params": {"appid": 2456740, "data_root": data_root},
                        "result": None,
                    }
                },
            }
        )

        report_job_service._clear_job_store_cache_for_test()
        loaded = report_job_service.get_report_job("job-run-1", data_root=data_root)

        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["progress"], 100)
        self.assertEqual(loaded["error_code"], "interrupted_by_restart")
        self.assertIn("interrupted by server restart", str(loaded["error_message"]))
        self.assertIsNotNone(loaded["finished_at"])

    def test_queued_job_is_marked_failed_after_restart_recovery(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)
        store = FileStore(data_root)
        store.write_report_jobs(
            {
                "schema_version": "report.jobs.v1",
                "saved_at": "2026-04-22T00:00:00+00:00",
                "jobs": {
                    "job-q-1": {
                        "job_id": "job-q-1",
                        "status": "queued",
                        "progress": 0,
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "started_at": None,
                        "finished_at": None,
                        "error_code": None,
                        "error_message": None,
                        "params": {"appid": 2456740, "data_root": data_root},
                        "result": None,
                    }
                },
            }
        )

        report_job_service._clear_job_store_cache_for_test()
        loaded = report_job_service.get_report_job("job-q-1", data_root=data_root)

        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["error_code"], "interrupted_by_restart")

    def test_duplicate_active_job_returns_existing_job_for_same_appid(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)

        first = report_job_service.create_report_job({"appid": 2456740}, data_root=data_root)
        second = report_job_service.create_report_job({"appid": 2456740}, data_root=data_root)

        self.assertEqual(first["job_id"], second["job_id"])
        self.assertFalse(bool(first.get("is_existing")))
        self.assertTrue(bool(second.get("is_existing")))
        self.assertEqual(second["status"], "queued")

        jobs_path = TEST_OUTPUT_DIR / "jobs" / "report_jobs.json"
        payload = json.loads(jobs_path.read_text(encoding="utf-8"))
        jobs = payload.get("jobs", {})
        self.assertEqual(len(jobs), 1)

    def test_snapshot_missing_required_field_marks_job_failed(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        data_root = str(TEST_OUTPUT_DIR)
        created = report_job_service.create_report_job({"appid": 2456740}, data_root=data_root)
        job_id = str(created["job_id"])

        with patch.object(
            report_job_service,
            "run_offline_pipeline_for_appid",
            return_value={
                "pipeline_run_id": "run-1",
                "raw_review_count": 10,
                "processed_review_count": 9,
                "included_review_count": 8,
            },
        ), patch.object(
            report_job_service,
            "_read_report_snapshot_payload",
            return_value={
                "schema_version": "report.v1",
                "app_id": 2456740,
                "snapshot_at": "2026-04-22T00:00:00+00:00",
                "window_days": 90,
                "data_quality": {
                    "review_count_total": 10,
                    "review_count_eligible": 8,
                    "confidence": 0.7,
                    "flags": ["ok"],
                },
                "snapshot": {
                    "decision_label": "buy_on_sale",
                    "decision_score": 65.0,
                    "decision_confidence": 70.0,
                    "key_drivers": [],
                },
                "category_distribution": [],
                "sentiment_x_category": [],
                "top_themes": [],
                "evidence_blocks": [],
                "trend": {"summary": {"direction": "stable"}, "spikes": []},
                "reviewer_segment": [],
                "final_recommendation": {
                    "label": "buy_on_sale",
                    "reason_summary": "test",
                    "conditions_to_buy": [],
                    "watch_items": [],
                    "inputs": {
                        "risk_index": 0.4,
                        "confidence": 0.7
                    }
                },
            },
        ):
            report_job_service.run_report_job(job_id)

        loaded = report_job_service.get_report_job(job_id, data_root=data_root)
        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["error_code"], "snapshot_required_missing")
        self.assertIn(
            "final_recommendation.inputs.trend_direction",
            str(loaded["error_message"]),
        )


if __name__ == "__main__":
    unittest.main()
