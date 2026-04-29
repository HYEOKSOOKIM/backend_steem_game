"""Tests for rebuilding display candidates from good claims."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality.display_rebuilder import build_display_from_good_claims


def _claim(
    *,
    block_id: str,
    title: str,
    theme: str,
    why: str,
    stance: str,
    snippets: list[str],
    consensus: str = "high",
    mention_count: int = 100,
    quality: str = "strict",
) -> dict:
    return {
        "block_id": block_id,
        "title": title,
        "theme": theme,
        "why_it_matters": why,
        "explanation": why,
        "stance": stance,
        "consensus_level": consensus,
        "mention_count": mention_count,
        "evidence_quality_level": quality,
        "evidence_snippets": snippets,
    }


def _report(strengths: list[dict] | None = None, risks: list[dict] | None = None) -> dict:
    return {
        "report_display": {
            "headline": "기존 헤드라인은 유지합니다.",
            "buy_recommendation": "buy_now",
            "good_for": ["기존 강점 대상 1", "기존 강점 대상 2", "기존 강점 대상 3"],
            "not_good_for": ["기존 리스크 대상"],
            "top_strengths": [
                {"title": "기존 강점 1", "summary": "기존 설명 1"},
                {"title": "기존 강점 2", "summary": "기존 설명 2"},
                {"title": "기존 강점 3", "summary": "기존 설명 3"},
            ],
            "top_risks": [{"title": "기존 리스크", "summary": "기존 설명"}],
        },
        "evidence_sections": {
            "strengths": strengths or [],
            "risks": risks or [],
        },
    }


class DisplayRebuilderTests(unittest.TestCase):
    def test_rebuilds_display_from_good_claims_without_mutating_report(self):
        report = _report(
            strengths=[
                _claim(
                    block_id="str_1",
                    title="사건과 인물의 여운이 오래 남는다는 반응",
                    theme="서사와 캐릭터",
                    why="스토리와 캐릭터 몰입을 말하는 반응입니다.",
                    stance="positive",
                    snippets=["스토리와 캐릭터가 좋아서 엔딩의 여운이 오래 남는다."],
                )
            ],
            risks=[
                _claim(
                    block_id="risk_1",
                    title="오류와 로딩이 흐름을 끊는다는 반응",
                    theme="버그와 로딩 문제",
                    why="버그와 로딩 문제가 플레이 흐름을 끊을 수 있습니다.",
                    stance="negative",
                    snippets=["버그와 무한 로딩 때문에 플레이 흐름이 자주 끊긴다."],
                )
            ],
        )
        before = copy.deepcopy(report)

        result = build_display_from_good_claims(report)
        rebuilt = result["rebuilt_display"]

        self.assertEqual(report, before)
        self.assertEqual(rebuilt["headline"], "기존 헤드라인은 유지합니다.")
        self.assertEqual(rebuilt["buy_recommendation"], "buy_now")
        self.assertEqual(result["used_claim_ids"]["strengths"], ["str_1"])
        self.assertEqual(result["used_claim_ids"]["risks"], ["risk_1"])
        self.assertEqual(len(rebuilt["top_strengths"]), 1)
        self.assertEqual(len(rebuilt["top_risks"]), 1)
        self.assertIn("서사와 캐릭터", rebuilt["good_for"][0])
        self.assertIn("버그와 로딩 문제", rebuilt["not_good_for"][0])

    def test_uses_at_most_two_claims_per_side(self):
        strengths = [
            _claim(
                block_id=f"str_{index}",
                title=f"스토리와 캐릭터가 좋다는 반응 {index}",
                theme=f"스토리와 캐릭터 {index}",
                why="스토리와 캐릭터 몰입을 말하는 반응입니다.",
                stance="positive",
                snippets=["스토리와 캐릭터가 좋아서 여운이 오래 남는다."],
            )
            for index in range(1, 4)
        ]
        report = _report(strengths=strengths)

        result = build_display_from_good_claims(report)

        self.assertEqual(result["used_claim_ids"]["strengths"], ["str_1", "str_2"])
        self.assertEqual(len(result["rebuilt_display"]["top_strengths"]), 2)
        self.assertEqual(result["dropped_existing_items"]["top_strengths"], 1)

    def test_empty_strength_selection_clears_strength_display_only(self):
        report = _report(
            strengths=[
                _claim(
                    block_id="str_bad",
                    title="버그와 오류가 많다는 반응",
                    theme="기술 문제",
                    why="오류와 튕김이 잦다는 반응입니다.",
                    stance="positive",
                    snippets=["가격이 비싸서 할인할 때 사는 편이 낫다."],
                )
            ],
            risks=[
                _claim(
                    block_id="risk_1",
                    title="오류와 로딩이 흐름을 끊는다는 반응",
                    theme="버그와 로딩 문제",
                    why="버그와 로딩 문제가 플레이 흐름을 끊을 수 있습니다.",
                    stance="negative",
                    snippets=["버그와 무한 로딩 때문에 플레이 흐름이 자주 끊긴다."],
                )
            ],
        )

        result = build_display_from_good_claims(report)
        rebuilt = result["rebuilt_display"]

        self.assertEqual(result["used_claim_ids"]["strengths"], [])
        self.assertEqual(rebuilt["good_for"], [])
        self.assertEqual(rebuilt["top_strengths"], [])
        self.assertEqual(result["used_claim_ids"]["risks"], ["risk_1"])
        self.assertEqual(len(rebuilt["top_risks"]), 1)

    def test_compacts_adjective_reaction_without_truncating_stem(self):
        report = _report(
            risks=[
                _claim(
                    block_id="risk_1",
                    title="조작 적응이 답답하다는 반응",
                    theme="조작 적응이 답답하다는 점",
                    why="조작 적응이 답답하다는 반응입니다.",
                    stance="negative",
                    snippets=["조작이 답답하고 적응이 어렵다."],
                )
            ]
        )

        result = build_display_from_good_claims(report)
        rebuilt = result["rebuilt_display"]

        self.assertEqual(rebuilt["top_risks"][0]["title"], "조작 적응이 답답하다는 점")
        self.assertEqual(rebuilt["not_good_for"][0], "조작 적응이 답답하다는 점에 민감한 플레이어")


if __name__ == "__main__":
    unittest.main()
