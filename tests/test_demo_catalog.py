"""Tests for demo game alias catalog normalization."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = Path(__file__).resolve().parent / "_tmp_demo_catalog"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.demo_catalog import load_demo_games, upsert_demo_game


class DemoCatalogTests(unittest.TestCase):
    def tearDown(self):
        if TEST_OUTPUT_DIR.exists():
            shutil.rmtree(TEST_OUTPUT_DIR)

    def test_load_demo_games_deduplicates_aliases_ignoring_spacing_and_punctuation(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        catalog_path = TEST_OUTPUT_DIR / "demo_games.json"
        payload = [
            {
                "appid": 1086940,
                "name": "Baldur's Gate 3",
                "aliases": [
                    "발더스 게이트 3",
                    "발더스게이트3",
                    "BG3",
                    "bg3",
                    "Baldur's Gate 3",
                    "Baldurs Gate 3",
                ],
                "enabled_for_demo": True,
            }
        ]
        catalog_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        games = load_demo_games(catalog_path)

        self.assertEqual(len(games), 1)
        self.assertEqual(
            games[0]["aliases"],
            ["발더스 게이트 3", "BG3", "Baldur's Gate 3"],
        )

    def test_upsert_demo_game_generates_alias_draft_from_korean_and_english_names(self):
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        catalog_path = TEST_OUTPUT_DIR / "demo_games.json"
        catalog_path.write_text("[]\n", encoding="utf-8")

        upsert_demo_game(
            catalog_path,
            appid=1086940,
            name="발더스 게이트 3",
            name_en="Baldur's Gate 3",
            name_ko="발더스 게이트 3",
            enabled_for_demo=True,
        )

        games = load_demo_games(catalog_path)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["name_en"], "Baldur's Gate 3")
        self.assertEqual(games[0]["name_ko"], "발더스 게이트 3")
        self.assertIn("발더스게이트3", games[0]["aliases"])
        self.assertIn("BG3", games[0]["aliases"])
        self.assertIn("Baldurs Gate 3", games[0]["aliases"])


if __name__ == "__main__":
    unittest.main()
