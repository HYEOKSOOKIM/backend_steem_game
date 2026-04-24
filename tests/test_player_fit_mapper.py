"""Tests for genre-aware player-fit subtype mapping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.player_fit_mapper import (
    build_display_theme,
    build_player_fit_phrase,
    infer_copy_subtype,
)


class PlayerFitMapperTests(unittest.TestCase):
    def test_pubg_like_gameplay_does_not_map_to_boss_pattern(self):
        genres = ["Action", "Shooter", "Battle Royale"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="총기 손맛과 교전 템포",
            genres=genres,
            negative=False,
        )
        self.assertNotEqual(subtype, "boss_pattern_mastery")
        self.assertEqual(subtype, "openworld_pvp_tension")

        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="총기 손맛과 교전 템포",
            genres=genres,
            negative=False,
        )
        self.assertIn("플레이어", phrase)
        self.assertNotIn("보스", phrase)
        self.assertNotIn("패턴", phrase)

    def test_stardew_like_genres_map_to_cozy_or_life_sim_language(self):
        genres = ["Simulation", "Farming Sim", "Cozy"]
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="하루 루틴과 농장 성장",
            genres=genres,
            negative=False,
        )
        self.assertTrue("루틴" in phrase or "생활" in phrase or "키워" in phrase)
        self.assertNotIn("전술", phrase)
        self.assertNotIn("운영 판단", phrase)

    def test_football_manager_maps_to_management_tactics(self):
        genres = ["Simulation", "Sports", "Management"]
        subtype = infer_copy_subtype(
            aspect="content_depth",
            theme="전술과 로스터 운영",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "management_tactics")
        title = build_display_theme(
            aspect="content_depth",
            theme=None,
            genres=genres,
            negative=False,
        )
        self.assertIn("전술", title)

    def test_rust_like_survival_game_avoids_soulslike_mastery_copy(self):
        genres = ["Action", "Survival", "Sandbox", "Shooter"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="파밍과 거점 방어",
            genres=genres,
            negative=False,
        )
        self.assertIn(subtype, {"survival_base_building", "openworld_pvp_tension", "loot_and_loss_loop"})
        self.assertNotEqual(subtype, "boss_pattern_mastery")

    def test_negative_shooter_gameplay_prefers_performance_or_teamplay_risk(self):
        genres = ["Action", "Shooter", "Battle Royale"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="매칭과 서버 불안정",
            genres=genres,
            negative=True,
        )
        self.assertIn(subtype, {"matchmaking_variance", "performance_instability", "teamplay_stress"})

    def test_negative_cozy_gameplay_avoids_management_style_risk(self):
        genres = ["Simulation", "Farming Sim", "Cozy"]
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="반복 루틴의 지루함",
            genres=genres,
            negative=True,
        )
        self.assertNotIn("전술", phrase)
        self.assertNotIn("운영", phrase)

    def test_ddlc_maps_to_visual_narrative_subtype(self):
        genres = ["Visual Novel", "Story Rich", "Psychological Horror"]
        subtype = infer_copy_subtype(
            aspect="story",
            theme="감정선과 장면 전환의 충격",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "visual_narrative_immersion")
        phrase = build_player_fit_phrase(
            aspect="story",
            theme="감정선과 장면 전환의 충격",
            genres=genres,
            negative=False,
        )
        self.assertIn("감정선", phrase)
        self.assertNotIn("전투", phrase)
        self.assertNotIn("매칭", phrase)

    def test_cities_maps_to_city_builder_management(self):
        genres = ["Simulation", "City Builder", "Management"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="교통 흐름과 도시 확장",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "city_builder_management")
        title = build_display_theme(
            aspect="gameplay",
            theme=None,
            genres=genres,
            negative=False,
        )
        self.assertNotIn("전투", title)
        self.assertTrue("도시" in title or "운영" in title)

    def test_factorio_maps_to_automation_factory_optimization(self):
        genres = ["Simulation", "Automation", "Factory", "Sandbox"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="자동화 라인과 병목 해소",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "automation_factory_optimization")
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="자동화 라인과 병목 해소",
            genres=genres,
            negative=False,
        )
        self.assertIn("자동화", phrase)
        self.assertNotIn("매칭", phrase)

    def test_slay_the_spire_maps_to_deckbuilding_run_planning(self):
        genres = ["Strategy", "Card Game", "Deckbuilding", "Roguelike"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="덱 구성과 카드 선택",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "deckbuilding_run_planning")
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="덱 구성과 카드 선택",
            genres=genres,
            negative=False,
        )
        self.assertTrue("덱" in phrase or "카드" in phrase)

    def test_xcom2_maps_to_turn_based_tactical_pressure(self):
        genres = ["Strategy", "Turn-Based", "Tactical"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="한 턴의 판단과 병력 손실 압박",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "turn_based_tactical_pressure")
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="한 턴의 판단과 병력 손실 압박",
            genres=genres,
            negative=False,
        )
        self.assertIn("턴", phrase)


if __name__ == "__main__":
    unittest.main()
