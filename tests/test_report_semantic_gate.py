"""Tests for deterministic semantic QA over generated reports."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality import build_claim_ledger, build_phrase_bank, evaluate_report_semantics


def _base_report() -> dict:
    return {
        "report_display": {
            "headline": "서사와 인물은 좋지만 느린 진행 템포는 취향을 탈 수 있습니다.",
            "good_for": ["서사와 인물의 여운을 오래 가져가는 플레이어"],
            "not_good_for": ["느린 진행 템포에 쉽게 지치는 플레이어"],
            "top_strengths": [
                {
                    "title": "깊이 있는 서사",
                    "summary": "사건과 인물의 여운이 오래 남습니다.",
                }
            ],
            "top_risks": [
                {
                    "title": "느린 진행 템포",
                    "summary": "이동과 반복 구간이 지루하게 느껴질 수 있습니다.",
                }
            ],
            "recent_state": {
                "status": "mixed",
                "summary": "서사 호평은 이어지지만 진행 템포를 아쉬워하는 반응도 있습니다.",
            },
        },
        "evidence_sections": {
            "strengths": [
                {
                    "block_id": "str_1",
                    "title": "사건과 인물의 여운이 오래 남는다는 반응",
                    "theme": "사건과 인물",
                    "why_it_matters": "서사와 캐릭터 몰입을 말하는 반응이 많습니다.",
                    "explanation": "서사와 캐릭터 몰입을 말하는 반응이 많습니다.",
                    "aspect_keys": ["story"],
                    "stance": "positive",
                    "evidence_snippets": [
                        "스토리와 캐릭터가 좋아서 여운이 오래 남는다.",
                        "아서의 이야기에 몰입했고 엔딩이 기억에 남는다.",
                    ],
                }
            ],
            "risks": [
                {
                    "block_id": "risk_1",
                    "title": "진행 템포가 느리다는 반응",
                    "theme": "느린 진행 템포",
                    "why_it_matters": "이동과 반복 구간이 지루하게 느껴질 수 있습니다.",
                    "explanation": "이동과 반복 구간이 지루하게 느껴질 수 있습니다.",
                    "aspect_keys": ["content_depth"],
                    "stance": "negative",
                    "evidence_snippets": [
                        "이동이 너무 느리고 반복이 많아 지루하다.",
                        "긴 호흡의 진행 템포 때문에 피로하다.",
                    ],
                }
            ],
        },
    }


class ReportSemanticGateTests(unittest.TestCase):
    def test_builds_claim_ledger_and_phrase_bank(self):
        report = _base_report()
        claims = build_claim_ledger(report)
        phrase_bank = build_phrase_bank(claims)

        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0]["claim_id"], "str_1")
        self.assertIn("story", claims[0]["support_families"])
        self.assertIn("str_1", phrase_bank)
        self.assertTrue(phrase_bank["str_1"])

    def test_passes_when_display_is_grounded_in_evidence(self):
        result = evaluate_report_semantics(_base_report())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["critical_failure_count"], 0)

    def test_detects_unsupported_display_claim(self):
        report = _base_report()
        report["report_display"]["top_strengths"][0] = {
            "title": "장비 파밍과 빌드 성장",
            "summary": "장비를 모으며 성장 루프를 오래 즐길 수 있습니다.",
        }
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("unsupported_claim", failure_types)
        self.assertEqual(result["status"], "fail")

    def test_detects_duplicate_evidence_claim_titles(self):
        report = _base_report()
        report["evidence_sections"]["risks"].append(
            {
                "block_id": "risk_2",
                "title": "진행 템포가 느리다는 반응",
                "theme": "반복 피로",
                "why_it_matters": "반복 구간이 피로하게 느껴질 수 있습니다.",
                "explanation": "반복 구간이 피로하게 느껴질 수 있습니다.",
                "aspect_keys": ["gameplay"],
                "stance": "negative",
                "evidence_snippets": [
                    "반복이 많아 피로하다.",
                    "템포가 느려 지루하다.",
                ],
            }
        )
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("duplicate_claim", failure_types)

    def test_detects_evidence_title_snippet_mismatch(self):
        report = _base_report()
        report["evidence_sections"]["risks"][0]["title"] = "버그와 오류가 많다는 반응"
        report["evidence_sections"]["risks"][0]["why_it_matters"] = "기술 문제가 잦다는 반응입니다."
        report["evidence_sections"]["risks"][0]["explanation"] = "기술 문제가 잦다는 반응입니다."
        report["evidence_sections"]["risks"][0]["evidence_snippets"] = [
            "정가가 비싸서 할인할 때 사는 편이 낫다.",
            "가격 대비 볼륨이 아쉽다는 생각이 든다.",
        ]
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("evidence_mismatch", failure_types)
        self.assertEqual(result["status"], "fail")

    def test_detects_generic_copy(self):
        report = _base_report()
        report["report_display"]["top_strengths"][0]["title"] = "핵심 플레이 감각"
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("generic_copy", failure_types)


    def test_detects_text_corruption_in_user_facing_fields(self):
        report = _base_report()
        report["report_display"]["top_strengths"][0]["title"] = "??? ??? ???"
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("text_corruption", failure_types)
        self.assertEqual(result["status"], "fail")

    def test_detects_duplicate_evidence_block_titles(self):
        report = _base_report()
        report["evidence_sections"]["risks"].append(
            {
                "block_id": "risk_2",
                "title": report["evidence_sections"]["risks"][0]["title"],
                "theme": "湲곗닠 ?대뒋",
                "why_it_matters": report["evidence_sections"]["risks"][0]["why_it_matters"],
                "explanation": report["evidence_sections"]["risks"][0]["explanation"],
                "aspect_keys": ["stability"],
                "stance": "negative",
                "evidence_snippets": [
                    "踰꾧렇? 濡쒕뵫 ?뚮Ц?쒕줈 ?먮쫫???μ쨷?덈떎.",
                    "?ㅻ쪟媛 諛섎났?섏뿬 紐곗엯???딄만 ?덉뒿?덈떎.",
                ],
            }
        )
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("evidence_duplicate_title", failure_types)

    def test_detects_evidence_theme_title_mismatch(self):
        report = _base_report()
        report["evidence_sections"]["risks"][0]["theme"] = "가격 대비 만족"
        report["evidence_sections"]["risks"][0]["title"] = "버그와 오류가 많다는 반응"
        report["evidence_sections"]["risks"][0]["why_it_matters"] = "기술 문제가 잦다는 반응입니다."
        report["evidence_sections"]["risks"][0]["explanation"] = "기술 문제가 잦다는 반응입니다."
        result = evaluate_report_semantics(report)
        failure_types = {item["type"] for item in result["failures"]}
        self.assertIn("evidence_theme_title_mismatch", failure_types)


if __name__ == "__main__":
    unittest.main()
