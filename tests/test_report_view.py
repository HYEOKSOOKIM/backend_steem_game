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


if __name__ == "__main__":
    unittest.main()


