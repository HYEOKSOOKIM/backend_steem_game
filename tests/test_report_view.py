"""Tests for consumer report evidence block structure."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.report_view import (
    _apply_final_language_polish,
    _normalize_card_title,
    _select_evidence_snippets_for_block,
    _stabilize_player_fit_list,
    build_consumer_report_from_snapshot,
)


def sentence_count(text: str) -> int:
    parts = [part.strip() for part in re.split(r"[.!?。！？]+", text) if part.strip()]
    return len(parts)


class ReportViewTests(unittest.TestCase):
    def test_apply_final_language_polish_normalizes_titles_and_player_fit_like_ui_copy(self):
        payload = {
            "report_plan": {
                "decision_anchor": {
                    "buy_recommendation": "buy_now",
                    "primary_reason_ids": ["str_1"],
                    "rationale_short": "핵심 재미가 분명합니다.",
                }
            },
            "report_display": {
                "headline": "전투와 탐험의 재미가 좋습니다.",
                "buy_timing_summary": "지금 구매하셔도 좋습니다.",
                "good_for": ["플레이할 수 있는 상황의 플레이어"],
                "not_good_for": ["진행 중 오류나 끊김을 거의 허용하지 않는 플레이어입니다."],
                "top_strengths": [
                    {"title": "세계관과 연출 덕분에 플레이를 계속하게 되는 몰입 경험이다.", "summary": "분위기와 서사가 오래 붙잡게 합니다."},
                ],
                "top_risks": [
                    {"title": "초반 적응은 필요하지만 익숙해지면 손맛이 살아나는 플레이 구조이다.", "summary": "처음에는 적응이 필요합니다."},
                ],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷한 편입니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }
        seed_display = {
            "good_for": ["하루 루틴을 천천히 쌓아가는 플레이를 좋아하는 플레이어"],
            "not_good_for": ["진행 중 오류나 끊김을 거의 허용하지 않는 플레이어"],
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display=seed_display,
        )

        self.assertEqual(
            polished["report_display"]["good_for"][0],
            "하루 루틴을 천천히 쌓아가는 플레이를 좋아하는 플레이어",
        )
        self.assertEqual(
            polished["report_display"]["not_good_for"][0],
            "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어",
        )
        self.assertFalse(polished["report_display"]["top_strengths"][0]["title"].endswith("이다"))
        self.assertFalse(polished["report_display"]["top_risks"][0]["title"].endswith("이다"))

    def test_apply_final_language_polish_preserves_non_generic_player_fit(self):
        payload = {
            "report_plan": {
                "decision_anchor": {
                    "buy_recommendation": "wait",
                    "primary_reason_ids": ["risk_1"],
                    "rationale_short": "조금 더 지켜보는 편이 좋습니다.",
                }
            },
            "report_display": {
                "headline": "관망이 더 나은 상태입니다.",
                "buy_timing_summary": "패치 흐름을 보는 편이 안전합니다.",
                "good_for": ["짧고 강한 교전 템포를 좋아하는 플레이어"],
                "not_good_for": ["팀플레이 소통 피로를 크게 느끼는 플레이어"],
                "top_strengths": [],
                "top_risks": [],
                "recent_state": {"status": "declining", "summary": "최근에는 불편 후기가 늘었습니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
        )

        self.assertEqual(
            polished["report_display"]["good_for"][0],
            "짧고 강한 교전 템포를 좋아하는 플레이어",
        )
        self.assertEqual(
            polished["report_display"]["not_good_for"][0],
            "팀플레이 소통 피로를 크게 느끼는 플레이어",
        )

    def test_apply_final_language_polish_uses_seed_when_visual_novel_copy_drift_contains_combat_terms(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "play_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "이야기 몰입이 좋습니다.",
                "buy_timing_summary": "지금 시작해도 좋습니다.",
                "good_for": ["핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어"],
                "not_good_for": ["매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어"],
                "top_strengths": [
                    {"title": "전투 손맛이 살아 있는 핵심 플레이", "summary": "손맛과 교전 템포가 좋습니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 안정적입니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }
        seed_display = {
            "good_for": ["서사와 감정선에 깊게 몰입하는 플레이어"],
            "not_good_for": ["텍스트와 번역 품질에 민감한 플레이어"],
            "top_strengths": [
                {"title": "감정선이 오래 남는 서사 몰입", "summary": "감정선과 전개에 깊게 빠져드는 흐름이 강합니다."},
            ],
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display=seed_display,
            genres=["Visual Novel", "Story Rich"],
        )

        self.assertEqual(polished["report_display"]["good_for"][0], "서사와 감정선에 깊게 몰입하는 플레이어")
        self.assertEqual(polished["report_display"]["not_good_for"][0], "텍스트와 번역 품질에 민감한 플레이어")
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "감정선이 오래 남는 서사 몰입")

    def test_apply_final_language_polish_uses_seed_when_city_builder_copy_mentions_combat(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "wait", "primary_reason_ids": ["risk_1"]}},
            "report_display": {
                "headline": "도시 운영의 재미가 있습니다.",
                "buy_timing_summary": "상황을 보고 결정하는 편이 좋습니다.",
                "good_for": ["핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어"],
                "not_good_for": ["전투 흐름이 끊기는 것을 싫어하는 플레이어"],
                "top_strengths": [
                    {"title": "전투와 이동 흐름이 매끄러운 운영 경험", "summary": "전투 흐름이 자연스럽게 이어집니다."},
                ],
                "top_risks": [
                    {"title": "전투/이동 흐름이 자주 끊기는 구간", "summary": "교전 감각이 불안정할 수 있습니다."},
                ],
                "recent_state": {"status": "mixed", "summary": "평가는 갈리는 편입니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }
        seed_display = {
            "good_for": ["도시를 키우며 흐름을 다듬는 운영형 플레이어"],
            "not_good_for": ["배치와 관리 피로에 민감한 플레이어"],
            "top_strengths": [
                {"title": "도시 흐름을 다듬는 운영의 재미", "summary": "도시를 확장하고 균형을 맞추는 과정이 핵심 재미로 이어집니다."},
            ],
            "top_risks": [
                {"title": "배치와 관리 부담이 커질 수 있는 구간", "summary": "규모가 커질수록 관리 피로가 빠르게 쌓일 수 있습니다."},
            ],
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display=seed_display,
            genres=["Simulation", "City Builder"],
        )

        self.assertEqual(polished["report_display"]["good_for"][0], "도시를 키우며 흐름을 다듬는 운영형 플레이어")
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "도시 흐름을 다듬는 운영의 재미")
        self.assertEqual(polished["report_display"]["top_risks"][0]["title"], "배치와 관리 부담이 커질 수 있는 구간")

    def test_apply_final_language_polish_rewrites_generic_strengths_for_automation_deckbuilder_and_turn_based(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "buy_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "핵심 재미가 살아 있습니다.",
                "buy_timing_summary": "지금 시작해도 좋습니다.",
                "good_for": [],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "계속 손에 붙는 핵심 플레이 감각", "summary": "기본 플레이 감각이 좋아 손에 익을수록 재미가 커지는 편입니다."},
                ],
                "top_risks": [
                    {"title": "전투/이동 흐름이 자주 끊기는 구간", "summary": "프레임과 반응성이 흔들리면 조작 감각이 무너질 수 있습니다."},
                ],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        factorio = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Simulation", "Automation"],
        )
        slay = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Roguelike", "Deckbuilder"],
        )
        xcom = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Strategy", "Turn-Based", "Tactical"],
        )

        self.assertEqual(factorio["report_display"]["top_strengths"][0]["title"], "자동화 흐름을 다듬는 재미")
        self.assertEqual(slay["report_display"]["top_strengths"][0]["title"], "덱이 손에 맞아가는 한 판 설계")
        self.assertEqual(xcom["report_display"]["top_strengths"][0]["title"], "턴마다 쌓이는 전술 긴장감")
        self.assertEqual(xcom["report_display"]["top_risks"][0]["title"], "턴 흐름이 끊기는 구간")

    def test_apply_final_language_polish_softens_price_fit_and_evidence_tone(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "wait", "primary_reason_ids": ["risk_1"]}},
            "report_display": {
                "headline": "상황을 보고 결정하는 편이 좋습니다.",
                "buy_timing_summary": "조금 더 지켜보는 편이 좋습니다.",
                "good_for": [],
                "not_good_for": ["가격 대비 만족을 매우 엄격하게 따지는 플레이어"],
                "top_strengths": [],
                "top_risks": [],
                "recent_state": {"status": "mixed", "summary": "평가는 갈립니다."},
            },
            "evidence_sections": {
                "strengths": [
                    {
                        "title": "도시를 다듬고 확장하는 재미가 좋다는 반응이다.",
                        "why_it_matters": "운영의 재미가 강합니다.",
                        "explanation": "도시 흐름을 오래 만지는 재미가 큽니다.",
                        "stance": "positive",
                        "consensus_level": "high",
                        "mention_count": 12,
                        "evidence_snippets": ["도시를 키우는 재미가 좋습니다.", "확장할수록 재미가 커집니다."],
                    }
                ],
                "risks": [],
            },
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Simulation", "City Builder"],
        )

        self.assertEqual(
            polished["report_display"]["not_good_for"][0],
            "비용 대비 만족을 꼼꼼하게 따지는 플레이어",
        )
        self.assertEqual(
            polished["evidence_sections"]["strengths"][0]["title"],
            "도시를 다듬고 확장하는 재미가 좋다는 반응",
        )

    def test_apply_final_language_polish_rewrites_visual_novel_generic_strength(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "play_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "이야기 몰입이 좋습니다.",
                "buy_timing_summary": "가볍게 시작해도 좋습니다.",
                "good_for": [],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "계속 손에 붙는 핵심 플레이 감각", "summary": "기본 플레이 감각이 좋아 손에 익을수록 재미가 커지는 편입니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Visual Novel", "Story Rich"],
        )

        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "감정선이 오래 남는 서사 경험")

    def test_apply_final_language_polish_rewrites_city_builder_generic_strength(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "wait", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "도시 운영의 재미가 있습니다.",
                "buy_timing_summary": "상황을 보고 결정하는 편이 좋습니다.",
                "good_for": [],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "계속 손에 붙는 핵심 플레이 감각", "summary": "기본 플레이 감각이 좋아 손에 익을수록 재미가 커지는 편입니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Simulation", "City Builder"],
        )

        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "도시 흐름을 다듬는 운영의 재미")

    def test_apply_final_language_polish_rewrites_looter_shooter_generic_strength(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "buy_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "성장 루프가 좋습니다.",
                "buy_timing_summary": "지금 시작해도 괜찮습니다.",
                "good_for": ["탐험과 세계 해석의 재미를 좋아하는 플레이어"],
                "not_good_for": ["매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어"],
                "top_strengths": [
                    {"title": "계속 손에 붙는 핵심 플레이 감각", "summary": "플레이 흐름이 점점 또렷해지는 재미가 있습니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"good_for": ["장비와 빌드를 오래 다듬는 플레이어"]},
            genres=["Action", "Shooter", "Looter Shooter", "Warframe"],
        )

        self.assertEqual(polished["report_display"]["good_for"][0], "장비와 빌드를 오래 다듬는 플레이어")
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "장비와 빌드를 오래 다듬는 성장 루프")

    def test_apply_final_language_polish_rewrites_looter_shooter_headline_and_story_fit(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "try_lightly", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "탐험과 세계 해석의 몰입감 장점이 보여 무료로 가볍게 시작해 보고 맞는지 판단하기 좋습니다.",
                "buy_timing_summary": "무료로 가볍게 시작해 보기 좋습니다.",
                "good_for": ["세계관과 맥락을 스스로 읽어가는 플레이어"],
                "not_good_for": [],
                "top_strengths": [],
                "top_risks": [],
                "recent_state": {"status": "mixed", "summary": "평가는 갈립니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=True,
            seed_display={"headline": "장비와 성장 루프의 매력이 분명해 무료로 가볍게 시작해 보고 맞는지 판단하기 좋습니다."},
            genres=["Action", "Free to Play", "Looter Shooter", "Warframe"],
        )

        self.assertEqual(
            polished["report_display"]["headline"],
            "장비 파밍과 성장 루프의 장점이 보여 무료로 가볍게 시작해보고 맞는지 판단하기 좋습니다.",
        )
        self.assertEqual(polished["report_display"]["good_for"][0], "장비와 빌드를 오래 다듬는 플레이어")

    def test_apply_final_language_polish_prefers_coop_live_service_language(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "wait", "primary_reason_ids": ["risk_1"]}},
            "report_display": {
                "headline": "플레이 흐름의 안정감이 좋아 보이지만 상황을 더 지켜보는 편이 좋습니다.",
                "buy_timing_summary": "조금 더 지켜보는 편이 좋습니다.",
                "good_for": ["배경과 연출이 만드는 분위기를 중요하게 보는 플레이어"],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "장비와 빌드를 오래 다듬는 성장 루프", "summary": "장비를 모으는 재미가 있습니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "mixed", "summary": "평가는 갈립니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"headline": "분대 협동과 임무 수행의 재미는 분명하지만 밸런스와 안정성 변수는 함께 감수해야 합니다."},
            genres=["Action", "Co-op", "Shooter", "Live Service", "HELLDIVERS 2"],
        )

        self.assertIn("분대 협동", polished["report_display"]["headline"])
        self.assertEqual(polished["report_display"]["good_for"][0], "분대 호흡을 맞추며 임무를 푸는 플레이어")
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "분대 합이 살아나는 협동 임무")

    def test_apply_final_language_polish_rewrites_flow_stability_strength_by_looter_context(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "buy_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "성장 루프가 좋습니다.",
                "buy_timing_summary": "지금 시작해도 괜찮습니다.",
                "good_for": ["장비와 빌드를 오래 다듬는 플레이어"],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "플레이 흐름의 안정감", "summary": "기본 플레이 흐름의 안정감이 살아 있어 반복 플레이가 편안합니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Action", "Shooter", "Looter Shooter", "Warframe"],
        )

        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "장비와 빌드를 오래 다듬는 성장 루프")

    def test_apply_final_language_polish_enforces_live_service_primary_copy(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "free_play_recommended", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "플레이 흐름의 안정감 체감이 좋아 무료로 지금 시작해 보기 좋은 상태입니다.",
                "buy_timing_summary": "무료로 지금 시작해 보기 좋은 상태입니다.",
                "good_for": ["장비와 빌드를 오래 다듬는 플레이어"],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "플레이 흐름의 안정감", "summary": "기본 플레이 흐름이 안정적으로 잡혀 익숙해질수록 리듬이 또렷해지는 편입니다."},
                ],
                "top_risks": [],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=True,
            seed_display={},
            genres=["액션", "RPG", "무료 플레이", "Warframe"],
        )

        self.assertIn("장비 파밍과 성장 루프", polished["report_display"]["headline"])
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "장비와 빌드를 오래 다듬는 성장 루프")

    def test_apply_final_language_polish_enforces_narrative_openworld_primary_copy(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "buy_now", "primary_reason_ids": ["str_1"]}},
            "report_display": {
                "headline": "플레이 흐름의 안정감 체감이 좋아 지금 바로 시작해도 만족도가 높은 편입니다.",
                "buy_timing_summary": "지금 바로 시작해도 만족도가 높은 편입니다.",
                "good_for": ["사건과 인물의 여운을 오래 가져가는 플레이어"],
                "not_good_for": [],
                "top_strengths": [
                    {"title": "플레이 흐름의 안정감", "summary": "기본 플레이 흐름이 안정적으로 잡혀 익숙해질수록 리듬이 또렷해지는 편입니다."},
                ],
                "top_risks": [
                    {"title": "매칭과 서버 문제", "summary": "매칭과 서버 상태가 흔들리면 한 판의 완성도가 크게 달라질 수 있습니다."},
                ],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={},
            genres=["Action", "Adventure", "Red Dead Redemption 2"],
        )

        self.assertIn("사건과 인물의 여운", polished["report_display"]["headline"])
        self.assertEqual(polished["report_display"]["top_strengths"][0]["title"], "사건과 인물이 오래 남는 서사 경험")
        self.assertEqual(polished["report_display"]["top_risks"][0]["title"], "몰입을 끊는 기술 이슈")

    def test_apply_final_language_polish_rewrites_life_sim_and_narrative_openworld_copy(self):
        payload = {
            "report_plan": {"decision_anchor": {"buy_recommendation": "wait", "primary_reason_ids": ["risk_1"]}},
            "report_display": {
                "headline": "몰입감이 좋습니다.",
                "buy_timing_summary": "상황을 보고 결정하는 편이 좋습니다.",
                "good_for": ["핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어"],
                "not_good_for": ["매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어"],
                "top_strengths": [
                    {"title": "계속 손에 붙는 핵심 플레이 감각", "summary": "플레이 흐름이 점점 또렷해지는 재미가 있습니다."},
                ],
                "top_risks": [
                    {"title": "매칭과 서버 상태에 따라 체감이 흔들리는 구간", "summary": "연결 상태가 몰입을 크게 흔들 수 있습니다."},
                ],
                "recent_state": {"status": "stable", "summary": "최근 분위기는 비슷합니다."},
            },
            "evidence_sections": {"strengths": [], "risks": []},
        }

        sims = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"good_for": ["생활 루프를 천천히 쌓아가는 플레이어"]},
            genres=["Simulation", "Life Sim", "The Sims 4"],
        )
        witcher = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={
                "good_for": ["사건과 인물의 여운을 오래 가져가는 플레이어"],
                "top_risks": [{"title": "몰입을 끊는 기술 이슈", "summary": "기술적인 끊김이 길게 이어지면 몰입이 쉽게 흐트러질 수 있습니다."}],
            },
            genres=["RPG", "Open World", "The Witcher 3"],
        )

        self.assertEqual(sims["report_display"]["good_for"][0], "생활 루프를 천천히 쌓아가는 플레이어")
        self.assertEqual(sims["report_display"]["top_strengths"][0]["title"], "생활 루프와 꾸미기의 자유도")
        self.assertEqual(witcher["report_display"]["good_for"][0], "사건과 인물의 여운을 오래 가져가는 플레이어")
        self.assertEqual(witcher["report_display"]["top_risks"][0]["title"], "몰입을 끊는 기술 이슈")

    def test_normalize_card_title_trims_sentence_ending_but_keeps_core_noun(self):
        self.assertEqual(
            _normalize_card_title("초반 적응은 필요하지만 익숙해지면 손맛이 살아나는 플레이 구조이다."),
            "초반 적응은 필요하지만 익숙해지면 손맛이 살아나는 플레이 구조",
        )
        self.assertEqual(
            _normalize_card_title("팀 플레이"),
            "팀 플레이",
        )

    def test_stabilize_player_fit_list_prefers_seed_for_generic_or_malformed_values(self):
        values = [
            "플레이할 수 있는 상황의 플레이어",
            "짧고 강한 교전 템포를 좋아하는 플레이어",
            "",
        ]
        seed_values = [
            "하루 루틴을 천천히 쌓아가는 플레이를 좋아하는 플레이어",
            "짧고 강한 교전 템포를 좋아하는 플레이어",
            "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어",
        ]

        stabilized = _stabilize_player_fit_list(values, seed_values)

        self.assertEqual(
            stabilized[0],
            "하루 루틴을 천천히 쌓아가는 플레이를 좋아하는 플레이어",
        )
        self.assertIn("짧고 강한 교전 템포", stabilized[1])
        self.assertIn("진행 중 오류나 끊김", stabilized[2])

    def test_evidence_reviews_are_grouped_insight_blocks(self):
        metadata = {
            "appid": 2456740,
            "name": "inZOI (인조이)",
            "genres": ["Simulation"],
            "release_stage": "released",
        }
        analysis = {
            "issue_signals": {
                "performance": {
                    "mention_count": 120,
                    "negative_ratio": 0.82,
                    "recent_trend": "up",
                    "themes": ["프레임 드랍", "최적화 문제"],
                    "sample_reviews": ["전투 중 프레임이 크게 떨어져서 몰입이 끊깁니다."],
                },
                "customization": {
                    "mention_count": 95,
                    "negative_ratio": 0.21,
                    "recent_trend": "flat",
                    "themes": ["커스터마이징 호평"],
                    "sample_reviews": ["커스터마이징 폭이 넓어서 만드는 재미가 큽니다."],
                },
            }
        }
        processed = [
            {
                "review_id": "r1",
                "review_text": (
                    "전투 중 프레임이 갑자기 끊겨 몰입이 깨집니다. "
                    "중요한 타이밍마다 반응이 늦게 들어와서 답답합니다."
                ),
                "included_in_analysis": True,
                "category_tags": ["performance"],
                "voted_up": False,
            },
            {
                "review_id": "r2",
                "review_text": (
                    "프레임 드랍 때문에 조작이 밀리는 느낌이 납니다. "
                    "전투 흐름이 자꾸 끊겨 스트레스를 받습니다."
                ),
                "included_in_analysis": True,
                "category_tags": ["performance"],
                "voted_up": False,
            },
            {
                "review_id": "r3",
                "review_text": (
                    "외형 커스터마이징이 다양해서 캐릭터 만드는 재미가 큽니다. "
                    "꾸미는 과정이 만족스럽습니다."
                ),
                "included_in_analysis": True,
                "category_tags": ["customization"],
                "voted_up": True,
            },
            {
                "review_id": "r4",
                "review_text": (
                    "커스터마이징 선택지가 많아서 오래 만지게 됩니다. "
                    "취향대로 꾸밀 수 있는 점이 정말 좋습니다."
                ),
                "included_in_analysis": True,
                "category_tags": ["customization"],
                "voted_up": True,
            },
        ]

        report = build_consumer_report_from_snapshot(
            appid=2456740,
            metadata=metadata,
            analysis=analysis,
            processed_reviews=processed,
            pipeline_run_id="test-run",
            source_review_count=4,
        )

        evidence_blocks = report.get("evidence_reviews", [])
        self.assertTrue(evidence_blocks)
        for block in evidence_blocks:
            self.assertIn("title", block)
            self.assertIn("why_it_matters", block)
            self.assertIn("explanation", block)
            self.assertIn("stance", block)
            self.assertIn("consensus_level", block)
            self.assertIn("mention_count", block)
            self.assertIn("evidence_snippets", block)
            self.assertIn(block["stance"], {"positive", "negative"})
            self.assertEqual(block["consensus_level"], "high")
            self.assertGreaterEqual(len(block["evidence_snippets"]), 2)
            self.assertLessEqual(len(block["evidence_snippets"]), 3)
            for snippet in block["evidence_snippets"]:
                self.assertGreaterEqual(sentence_count(snippet), 1)
                self.assertLessEqual(sentence_count(snippet), 4)
                self.assertFalse(snippet.endswith("…"))

        evidence_sections = report.get("evidence_sections")
        self.assertIsInstance(evidence_sections, dict)
        self.assertIn("strengths", evidence_sections)
        self.assertIn("risks", evidence_sections)
        self.assertTrue(evidence_sections["strengths"])
        self.assertTrue(evidence_sections["risks"])
        self.assertTrue(all(block.get("stance") == "positive" for block in evidence_sections["strengths"]))
        self.assertTrue(
            all(block.get("stance") == "negative" for block in evidence_sections["risks"])
        )

    def test_evidence_blocks_use_relaxed_or_guaranteed_fill_when_theme_mismatch(self):
        metadata = {
            "appid": 1245620,
            "name": "ELDEN RING",
            "genres": ["Action", "RPG"],
            "release_stage": "released",
        }
        analysis = {
            "issue_signals": {
                "monetization": {
                    "mention_count": 24,
                    "negative_ratio": 0.85,
                    "recent_trend": "up",
                    "themes": ["가격 / 과금 불만"],
                    "sample_reviews": [],
                }
            }
        }
        processed = [
            {
                "review_id": "m1",
                "review_text": "보스 패턴이 불친절해서 초반 진입이 너무 빡빡합니다.",
                "included_in_analysis": True,
                "category_tags": ["monetization"],
                "voted_up": False,
            },
            {
                "review_id": "m2",
                "review_text": "전투 타이밍이 어렵고 카메라가 불편해서 스트레스를 받았습니다.",
                "included_in_analysis": True,
                "category_tags": ["monetization"],
                "voted_up": False,
            },
        ]

        report = build_consumer_report_from_snapshot(
            appid=1245620,
            metadata=metadata,
            analysis=analysis,
            processed_reviews=processed,
            pipeline_run_id="test-run-2",
            source_review_count=2,
        )

        evidence_sections = report.get("evidence_sections", {})
        risks = evidence_sections.get("risks") or []
        self.assertTrue(risks)
        self.assertGreaterEqual(len(risks[0].get("evidence_snippets", [])), 2)

    def test_free_game_uses_price_aware_recommendation_values(self):
        metadata = {
            "appid": 578080,
            "name": "PUBG: BATTLEGROUNDS",
            "genres": ["Action"],
            "price_model": "free_to_play",
            "is_free": True,
            "release_stage": "released",
        }
        analysis = {
            "issue_signals": {
                "performance": {
                    "mention_count": 18,
                    "negative_ratio": 0.56,
                    "recent_trend": "flat",
                    "themes": ["프레임 드랍"],
                    "sample_reviews": ["교전 중 프레임이 불안정합니다."],
                },
                "gameplay": {
                    "mention_count": 22,
                    "negative_ratio": 0.30,
                    "recent_trend": "flat",
                    "themes": ["전투 손맛"],
                    "sample_reviews": ["총기 손맛이 좋아 반복 플레이하게 됩니다."],
                },
            }
        }
        processed = [
            {
                "review_id": "f1",
                "review_text": "총기 손맛이 좋아 계속 하게 됩니다.",
                "included_in_analysis": True,
                "category_tags": ["gameplay"],
                "voted_up": True,
            },
            {
                "review_id": "f2",
                "review_text": "교전 중 프레임이 떨어질 때가 있어서 답답합니다.",
                "included_in_analysis": True,
                "category_tags": ["performance"],
                "voted_up": False,
            },
        ]

        report = build_consumer_report_from_snapshot(
            appid=578080,
            metadata=metadata,
            analysis=analysis,
            processed_reviews=processed,
            pipeline_run_id="free-run",
            source_review_count=2,
        )

        recommendation = report.get("report_display", {}).get("buy_recommendation")
        self.assertIn(
            recommendation,
            {"free_play_recommended", "play_now", "try_lightly", "wait", "not_recommended"},
        )
        self.assertNotIn(recommendation, {"buy_now", "buy_on_sale"})
        headline = report.get("report_display", {}).get("headline", "")
        self.assertNotIn("할인 구매", headline)

    def test_evidence_selection_prefers_stance_and_theme_when_judge_disabled(self):
        block = {
            "title": "교전 경험이 반복 플레이 만족으로 이어진다는 반응",
            "theme": "총기 손맛과 교전 몰입",
            "why_it_matters": "교전 감각이 맞으면 장기 플레이 만족도가 높아집니다.",
            "stance": "positive",
            "aspect_keys": ["gameplay"],
        }
        candidates = [
            "프레임이 끊기고 렉이 심해서 플레이가 불가능했습니다.",
            "총기 손맛이 좋아서 교전이 짜릿하고 계속 하게 됩니다.",
            "커스터마이징 선택지가 많아 꾸미는 재미가 있습니다.",
        ]

        selected = _select_evidence_snippets_for_block(
            block=block,
            candidates=candidates,
            judge=None,
        )

        self.assertGreaterEqual(len(selected), 2)
        self.assertIn("총기 손맛", selected[0])
        self.assertTrue(all("불가능" not in snippet for snippet in selected[:2]))

    def test_apply_final_language_polish_enforces_looter_primary_copy_from_good_for(self):
        payload = {
            "game": {
                "genres": ["Action", "RPG"],
                "name": "Warframe",
                "short_description": "A free-to-play looter shooter with long-term gear progression.",
            },
            "report_display": {
                "headline": "플레이 흐름의 안정감 체감이 좋아 무료로 지금 시작해 보기 좋은 상태입니다.",
                "good_for": ["장비와 빌드를 오래 다듬는 플레이어"],
                "not_good_for": ["같은 흐름이 길어지면 피로를 크게 느끼는 플레이어"],
                "top_strengths": [
                    {
                        "title": "플레이 흐름의 안정감",
                        "summary": "기본 플레이 흐름이 안정적으로 잡혀 익숙해질수록 리듬이 또렷해지는 편입니다.",
                    }
                ],
                "top_risks": [],
            },
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=True,
            seed_display={"good_for": ["장비와 빌드를 오래 다듬는 플레이어"]},
            genres=["Action", "RPG"],
        )

        self.assertIn("장비 파밍", polished["report_display"]["headline"])
        self.assertIn("장비", polished["report_display"]["top_strengths"][0]["title"])
        self.assertIn("파밍", polished["report_display"]["top_strengths"][0]["summary"])

    def test_apply_final_language_polish_rewrites_narrative_risk_when_multiplayer_leaks(self):
        payload = {
            "game": {
                "genres": ["Open World", "RPG"],
                "name": "Red Dead Redemption 2",
                "short_description": "A story-rich open world western about outlaws and fading ideals.",
            },
            "report_display": {
                "headline": "사건과 인물의 여운 체감이 좋아 지금 바로 시작해도 만족도가 높은 편입니다.",
                "good_for": ["사건과 인물의 여운을 오래 가져가는 플레이어"],
                "not_good_for": ["느린 진행 템포에 쉽게 지치는 플레이어"],
                "top_strengths": [
                    {
                        "title": "사건과 인물",
                        "summary": "사건과 인물의 여운이 길게 남아 세계를 천천히 체험하는 플레이와 잘 맞습니다.",
                    }
                ],
                "top_risks": [
                    {
                        "title": "버그와 안정성 문제",
                        "summary": "게임 중 잦은 튕김과 로딩 문제로 인해 플레이의 흐름이 끊길 수 있습니다. 이는 특히 멀티플레이에서 더욱 두드러집니다.",
                    }
                ],
            },
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"good_for": ["사건과 인물의 여운을 오래 가져가는 플레이어"]},
            genres=["Open World", "RPG"],
        )

        self.assertIn("사건과 인물의 여운이 오래 남는 경험", polished["report_display"]["headline"])
        self.assertEqual(polished["report_display"]["top_risks"][0]["title"], "몰입을 끊는 기술 이슈")
        self.assertNotIn("멀티플레이", polished["report_display"]["top_risks"][0]["summary"])

    def test_apply_final_language_polish_enforces_soulslike_primary_copy(self):
        payload = {
            "game": {
                "genres": ["Action RPG", "Soulslike"],
                "name": "ELDEN RING",
                "short_description": "A soulslike action RPG with challenging bosses and open-world exploration.",
            },
            "report_display": {
                "headline": "핵심 플레이 감각 경험은 분명한 강점입니다. 다만 가격 대비 만족 편차 때문에 할인 시점에 시작하는 편이 더 안전합니다.",
                "good_for": ["도전적인 전투를 반복하며 손에 익히는 플레이어"],
                "not_good_for": ["같은 흐름이 길어지면 피로를 크게 느끼는 플레이어"],
                "top_strengths": [
                    {
                        "title": "핵심 플레이 감각이 꾸준히 살아 있는 경험",
                        "summary": "핵심 플레이가 손에 익을수록 흐름이 좋아져 오래 붙잡기 쉬운 편입니다.",
                    }
                ],
                "top_risks": [
                    {
                        "title": "가격 대비 만족감은 취향을 많이 타요",
                        "summary": "가격 부담이 크면 기대만큼 만족하지 못했다는 반응이 나옵니다.",
                    },
                    {
                        "title": "팀 플레이 피로가 생각보다 크게 느껴질 수 있어요",
                        "summary": "팀 호흡이 어긋나면 재미보다 피로가 먼저 올라올 수 있습니다.",
                    },
                ],
            },
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"good_for": ["도전적인 전투를 반복하며 손에 익히는 플레이어"]},
            genres=["Action RPG", "Soulslike"],
        )

        self.assertIn("보스 패턴", polished["report_display"]["headline"])
        self.assertIn("성취감", polished["report_display"]["top_strengths"][0]["title"])
        self.assertEqual(polished["report_display"]["top_risks"][0]["title"], "진입 장벽이 높은 초반")
        self.assertEqual(polished["report_display"]["top_risks"][1]["title"], "반복 트라이에서 오는 피로")

    def test_apply_final_language_polish_enforces_openworld_crime_sandbox_copy(self):
        payload = {
            "game": {
                "genres": ["Open World", "Action"],
                "name": "Grand Theft Auto V Enhanced",
                "short_description": "An open world crime sandbox with a three-protagonist story and GTA Online.",
            },
            "report_display": {
                "headline": "그래픽과 스토리는 뛰어나지만, 일반 버그와 핵 문제로 인해 구매는 업데이트 후가 좋습니다.",
                "good_for": ["넓은 오픈월드에서 자유롭게 돌아다니는 플레이어"],
                "not_good_for": ["온라인 불안정에 쉽게 지치는 플레이어"],
                "top_strengths": [
                    {
                        "title": "그래픽/비주얼 호평",
                        "summary": "현대 게임과 견주어도 손색없는 뛰어난 그래픽이 몰입감을 높여 줍니다.",
                    }
                ],
                "top_risks": [],
            },
        }

        polished = _apply_final_language_polish(
            payload=payload,
            allow_llm=False,
            is_free_game=False,
            seed_display={"good_for": ["넓은 오픈월드에서 자유롭게 돌아다니는 플레이어"]},
            genres=["Open World", "Action"],
        )

        self.assertIn("오픈월드 자유도", polished["report_display"]["headline"])
        self.assertIn("범죄 서사", polished["report_display"]["top_strengths"][0]["title"])


if __name__ == "__main__":
    unittest.main()


