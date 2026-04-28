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
    def test_generic_core_play_phrase_avoids_old_action_flavored_copy(self):
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme=None,
            genres=[],
            negative=False,
        )
        self.assertNotIn("핵심 플레이", phrase)
        self.assertNotIn("손에 익혀", phrase)

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
        self.assertTrue(any(token in phrase for token in ("루틴", "생활", "쌓아")))
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
            theme="루팅과 거점 방어",
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
            theme="반복 루프의 지루함",
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
        self.assertTrue("턴" in phrase or "판단" in phrase)

    def test_warframe_maps_to_looter_shooter_progression(self):
        genres = ["Action", "Shooter", "Looter Shooter", "Free to Play"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="장비 파밍과 빌드 성장",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "looter_shooter_progression")
        phrase = build_player_fit_phrase(
            aspect="gameplay",
            theme="장비 파밍과 빌드 성장",
            genres=genres,
            negative=False,
        )
        self.assertIn("장비", phrase)
        self.assertNotIn("탐험", phrase)

    def test_helldivers_maps_to_coop_live_service_shooter(self):
        genres = ["Action", "Shooter", "Co-op", "Live Service Shooter"]
        subtype = infer_copy_subtype(
            aspect="multiplayer",
            theme="분대 호흡과 임무 수행",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "cooperative_live_service_shooter")
        phrase = build_player_fit_phrase(
            aspect="multiplayer",
            theme="분대 호흡과 임무 수행",
            genres=genres,
            negative=False,
        )
        self.assertIn("분대", phrase)

    def test_witcher_maps_to_narrative_openworld_immersion(self):
        genres = ["RPG", "Open World", "Story Rich"]
        subtype = infer_copy_subtype(
            aspect="story",
            theme="사건과 인물의 여운",
            genres=genres + ["The Witcher 3"],
            negative=False,
        )
        self.assertEqual(subtype, "narrative_openworld_immersion")
        phrase = build_player_fit_phrase(
            aspect="story",
            theme="사건과 인물의 여운",
            genres=genres + ["The Witcher 3"],
            negative=False,
        )
        self.assertIn("사건", phrase)
        self.assertNotIn("매칭", phrase)

    def test_sims_maps_to_life_sim_social_loop(self):
        genres = ["Simulation", "Life Sim", "Social Sim"]
        subtype = infer_copy_subtype(
            aspect="gameplay",
            theme="생활 루프와 관계 시뮬레이션",
            genres=genres,
            negative=False,
        )
        self.assertEqual(subtype, "life_sim_social_loop")
        title = build_display_theme(
            aspect="gameplay",
            theme=None,
            genres=genres,
            negative=False,
        )
        self.assertTrue("생활" in title or "관계" in title)
        self.assertNotIn("전투", title)

    def test_negative_price_phrase_avoids_overly_harsh_generic_copy(self):
        phrase = build_player_fit_phrase(
            aspect="monetization",
            theme="가격과 dlc 부담",
            genres=["RPG"],
            negative=True,
        )
        self.assertNotIn("매우 엄격", phrase)


if __name__ == "__main__":
    unittest.main()
