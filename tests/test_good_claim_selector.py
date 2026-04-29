"""Tests for selecting display-ready evidence claims."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality.good_claim_selector import select_good_claims


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
        "report_display": {},
        "evidence_sections": {
            "strengths": strengths or [],
            "risks": risks or [],
        },
    }


class GoodClaimSelectorTests(unittest.TestCase):
    def test_selects_grounded_strength_and_risk_claims(self):
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
                    theme="버그와 로딩",
                    why="버그와 로딩 문제가 플레이 흐름을 끊을 수 있습니다.",
                    stance="negative",
                    snippets=["버그와 무한 로딩 때문에 플레이 흐름이 자주 끊긴다."],
                )
            ],
        )

        result = select_good_claims(report)

        self.assertEqual(result["summary"]["strength_count"], 1)
        self.assertEqual(result["summary"]["risk_count"], 1)
        self.assertEqual(result["summary"]["rejected_count"], 0)
        self.assertEqual(result["selected"]["strengths"][0]["claim_id"], "str_1")
        self.assertEqual(result["selected"]["risks"][0]["claim_id"], "risk_1")

    def test_rejects_claim_when_evidence_snippet_is_missing(self):
        report = _report(
            strengths=[
                _claim(
                    block_id="str_1",
                    title="사건과 인물의 여운이 오래 남는다는 반응",
                    theme="서사와 캐릭터",
                    why="스토리와 캐릭터 몰입을 말하는 반응입니다.",
                    stance="positive",
                    snippets=[],
                )
            ]
        )

        result = select_good_claims(report)

        self.assertEqual(result["summary"]["strength_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "missing_snippet")

    def test_rejects_claim_when_title_and_snippet_topics_do_not_match(self):
        report = _report(
            risks=[
                _claim(
                    block_id="risk_1",
                    title="버그와 오류가 많다는 반응",
                    theme="기술 문제",
                    why="오류와 튕김이 잦다는 반응입니다.",
                    stance="negative",
                    snippets=["가격이 비싸서 할인할 때 사는 편이 낫다."],
                )
            ]
        )

        result = select_good_claims(report)

        self.assertEqual(result["summary"]["risk_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "evidence_mismatch")

    def test_keeps_stronger_duplicate_claim_and_rejects_weaker_one(self):
        report = _report(
            risks=[
                _claim(
                    block_id="risk_weak",
                    title="진행 템포가 느리다는 반응",
                    theme="반복 피로",
                    why="반복 구간이 피로하게 느껴질 수 있습니다.",
                    stance="negative",
                    snippets=["반복이 많아 피로하다."],
                    consensus="medium",
                    mention_count=20,
                    quality="relaxed",
                ),
                _claim(
                    block_id="risk_strong",
                    title="진행 템포가 느리다는 반응",
                    theme="느린 진행 템포",
                    why="이동과 반복 구간이 지루하게 느껴질 수 있습니다.",
                    stance="negative",
                    snippets=[
                        "이동이 너무 느리고 반복이 많아 지루하다.",
                        "긴 호흡의 진행 템포 때문에 피로하다.",
                    ],
                    consensus="high",
                    mention_count=100,
                    quality="strict",
                ),
            ]
        )

        result = select_good_claims(report)

        self.assertEqual(result["summary"]["risk_count"], 1)
        self.assertEqual(result["selected"]["risks"][0]["claim_id"], "risk_strong")
        self.assertEqual(result["rejected"][0]["reason"], "duplicate_claim")
        self.assertEqual(result["rejected"][0]["claim_id"], "risk_weak")

    def test_rejects_weak_support_claim(self):
        report = _report(
            strengths=[
                _claim(
                    block_id="str_1",
                    title="스토리와 캐릭터가 좋다는 반응",
                    theme="스토리",
                    why="스토리를 좋게 보는 반응입니다.",
                    stance="positive",
                    snippets=["스토리가 좋다."],
                    consensus="",
                    mention_count=1,
                    quality="",
                )
            ]
        )

        result = select_good_claims(report)

        self.assertEqual(result["summary"]["strength_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "weak_support")


if __name__ == "__main__":
    unittest.main()

