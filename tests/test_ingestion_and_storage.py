"""Tests for Steam normalization helpers and local file persistence."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_tmp_storage"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.models.schemas import RawReview
from report.services.analysis_service import run_and_persist_analysis
from report.services.steam_reviews import (
    ALL_MODE_PAGE_CAP,
    fetch_steam_reviews,
    normalize_steam_game_metadata,
    normalize_steam_review,
    normalize_steam_reviews,
)
from report.storage.file_store import FileStore


def make_steam_payload() -> dict:
    return {
        "reviews": [
            {
                "recommendationid": "1001",
                "review": "최적화가 별로라 프레임 드랍이 심함",
                "voted_up": False,
                "timestamp_created": 1704067200,
                "timestamp_updated": 1704067200,
                "author": {
                    "steamid": "steamid-1001",
                    "playtime_forever": 180,
                    "playtime_at_review": 120,
                    "num_reviews": 4,
                },
            }
        ]
    }


def make_appdetails_payload(appid: int = 570) -> dict:
    return {
        str(appid): {
            "success": True,
            "data": {
                "steam_appid": appid,
                "name": "Test Game",
                "is_free": False,
                "genres": [
                    {"id": "1", "description": "Action"},
                    {"id": "2", "description": "RPG"},
                ],
                "categories": [
                    {"id": 2, "description": "Single-player"},
                ],
                "price_overview": {
                    "currency": "KRW",
                    "final": 22000,
                },
                "release_date": {
                    "coming_soon": False,
                    "date": "1 Jan, 2024",
                },
            },
        }
    }


class IngestionAndStorageTests(unittest.TestCase):
    def test_normalize_steam_review_maps_payload_to_raw_schema(self):
        payload = make_steam_payload()["reviews"][0]

        raw_review = normalize_steam_review(570, payload)

        self.assertIsInstance(raw_review, RawReview)
        self.assertEqual(raw_review.review_id, "1001")
        self.assertEqual(raw_review.appid, 570)
        self.assertEqual(raw_review.playtime_forever, 3.0)
        self.assertEqual(raw_review.playtime_at_review_hours, 2.0)
        self.assertEqual(raw_review.num_reviews, 4)

    def test_normalize_steam_reviews_maps_multiple_reviews(self):
        payload = make_steam_payload()

        raw_reviews = normalize_steam_reviews(570, payload)

        self.assertEqual(len(raw_reviews), 1)
        self.assertEqual(raw_reviews[0].review_text, "최적화가 별로라 프레임 드랍이 심함")

    def test_normalize_steam_game_metadata_maps_appdetails_payload(self):
        metadata = normalize_steam_game_metadata(570, make_appdetails_payload())

        self.assertEqual(metadata.appid, 570)
        self.assertEqual(metadata.name, "Test Game")
        self.assertEqual(metadata.price_model, "paid")
        self.assertEqual(metadata.release_stage, "released")
        self.assertEqual(metadata.genres, ["Action", "RPG"])

    def test_run_and_persist_analysis_writes_raw_processed_and_analysis_files(self):
        raw_reviews = [
            RawReview(
                review_id="1001",
                appid=570,
                review_text="최적화가 별로라 프레임 드랍이 심함",
                voted_up=False,
                timestamp_created=1704067200,
                timestamp_updated=1704067200,
                playtime_forever=3.0,
                playtime_at_review_hours=2.0,
                num_reviews=4,
                author_steamid="steamid-1001",
            )
        ]

        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        try:
            result, processed_reviews = run_and_persist_analysis(
                raw_reviews,
                appid=570,
                data_root=TEST_OUTPUT_DIR,
            )

            raw_path = TEST_OUTPUT_DIR / "raw" / "570.json"
            processed_path = TEST_OUTPUT_DIR / "processed" / "570.json"
            analysis_path = TEST_OUTPUT_DIR / "analysis" / "570.json"

            self.assertTrue(raw_path.exists())
            self.assertTrue(processed_path.exists())
            self.assertTrue(analysis_path.exists())
            self.assertEqual(result.appid, 570)
            self.assertEqual(len(processed_reviews), 1)

            analysis_payload = json.loads(analysis_path.read_text(encoding="utf-8"))
            self.assertEqual(analysis_payload["appid"], 570)
            self.assertIn("issue_signals", analysis_payload)
        finally:
            if TEST_OUTPUT_DIR.exists():
                shutil.rmtree(TEST_OUTPUT_DIR)

    def test_file_store_can_persist_metadata_payload(self):
        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        try:
            metadata_payload = normalize_steam_game_metadata(570, make_appdetails_payload()).to_dict()
            store = FileStore(TEST_OUTPUT_DIR)
            path = store.write_game_metadata(570, metadata_payload)

            self.assertTrue(path.exists())
            self.assertEqual(store.read_json(Path("metadata") / "570.json")["name"], "Test Game")
        finally:
            if TEST_OUTPUT_DIR.exists():
                shutil.rmtree(TEST_OUTPUT_DIR)

    def test_fetch_steam_reviews_all_mode_is_capped_at_200_pages(self):
        def fake_page(*_args, **kwargs):
            cursor = kwargs.get("cursor", "*")
            if cursor == "*":
                next_cursor = "cursor-1"
            else:
                current = int(str(cursor).split("-")[1])
                next_cursor = f"cursor-{current + 1}"
            return {
                "success": 1,
                "cursor": next_cursor,
                "reviews": [{"recommendationid": next_cursor, "review": "테스트"}],
            }

        with patch("report.services.steam_reviews.fetch_steam_reviews_page", side_effect=fake_page) as mock_fetch:
            payload = fetch_steam_reviews(570, max_pages=None)

        self.assertEqual(mock_fetch.call_count, ALL_MODE_PAGE_CAP)
        self.assertEqual(payload["_fetch_stats"]["pages_fetched"], ALL_MODE_PAGE_CAP)
        self.assertTrue(payload["_fetch_stats"]["all_mode_cap_reached"])
        self.assertEqual(payload["_fetch_stats"]["all_mode_page_cap"], ALL_MODE_PAGE_CAP)


if __name__ == "__main__":
    unittest.main()


