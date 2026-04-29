"""Tests for semantic report repair planning."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality import build_claim_ledger, build_phrase_bank
from report.quality.repair import apply_safe_repair_actions, build_repair_plan


def _report_with_duplicate_and_generic() -> dict:
    return {
        "report_display": {
            "headline": "서사와 인물은 좋지만 느린 진행 템포는 취향을 탈 수 있습니다.",
            "good_for": ["핵심 플레이 감각을 즐기는 플레이어"],
            "not_good_for": ["느린 진행 템포에 민감한 플레이어"],
            "top_strengths": [
                {
                    "title": "핵심 플레이 감각",
                    "summary": "손에 익을수록 재미가 살아납니다.",
                }
            ],
            "top_risks": [
                {
                    "title": "느린 진행 템포",
                    "summary": "이동과 반복이 지루하게 느껴질 수 있습니다.",
                }
            ],
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
                    "consensus_level": "high",
                    "mention_count": 100,
                    "evidence_quality_level": "strict",
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
                    "consensus_level": "high",
                    "mention_count": 100,
                    "evidence_quality_level": "strict",
                    "evidence_snippets": [
                        "이동이 너무 느리고 반복이 많아 지루하다.",
                        "긴 호흡의 진행 템포 때문에 피로하다.",
                    ],
                },
                {
                    "block_id": "risk_2",
                    "title": "진행 템포가 느리다는 반응",
                    "theme": "반복 피로",
                    "why_it_matters": "반복 구간이 피로하게 느껴질 수 있습니다.",
                    "explanation": "반복 구간이 피로하게 느껴질 수 있습니다.",
                    "aspect_keys": ["gameplay"],
                    "stance": "negative",
                    "consensus_level": "medium",
                    "mention_count": 20,
                    "evidence_quality_level": "relaxed",
                    "evidence_snippets": [
                        "반복이 많아 피로하다.",
                        "템포가 느려 지루하다.",
                    ],
                },
            ],
        },
    }


class ReportRepairPlanTests(unittest.TestCase):
    def test_duplicate_claim_becomes_drop_action(self):
        plan = build_repair_plan(_report_with_duplicate_and_generic())
        actions = [action for action in plan["actions"] if action["action"] == "drop_duplicate_claim"]
        self.assertTrue(actions)
        self.assertTrue(all(action.get("safety_level") == "safe" for action in actions))

    def test_generic_copy_becomes_rewrite_action(self):
        plan = build_repair_plan(_report_with_duplicate_and_generic())
        action_types = {action["action"] for action in plan["actions"]}
        self.assertIn("rewrite_generic_copy", action_types)

    def test_unsupported_claim_becomes_hold(self):
        report = _report_with_duplicate_and_generic()
        report["report_display"]["top_strengths"][0] = {
            "title": "장비 파밍과 빌드 성장",
            "summary": "장비를 모으며 성장 루프를 즐길 수 있습니다.",
        }
        plan = build_repair_plan(report)
        hold_types = {hold["failure_type"] for hold in plan["holds"]}
        self.assertIn("unsupported_claim", hold_types)
        self.assertFalse(plan["can_apply_safely"])

    def test_theme_drift_rewrite_requires_review(self):
        report = _report_with_duplicate_and_generic()
        semantic_result = {
            "status": "fail",
            "failure_count": 1,
            "critical_failure_count": 1,
            "failures": [
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": "top_risks[1]",
                    "best_claim_id": "risk_1",
                    "best_score": 0.14,
                    "text": "느린 진행 진행이 길어져 피로할 수 있습니다.",
                }
            ],
        }
        plan = build_repair_plan(report, semantic_result=semantic_result)
        review_actions = [
            action for action in plan["actions"]
            if action.get("failure_type") == "theme_drift"
        ]
        self.assertTrue(any(action.get("requires_review") for action in review_actions))
        self.assertFalse(plan["can_apply_safely"])

    def test_evidence_mismatch_becomes_hold(self):
        report = _report_with_duplicate_and_generic()
        report["evidence_sections"]["risks"][0]["title"] = "버그와 오류가 많다는 반응"
        report["evidence_sections"]["risks"][0]["why_it_matters"] = "기술 문제가 잦다는 반응입니다."
        report["evidence_sections"]["risks"][0]["explanation"] = "기술 문제가 잦다는 반응입니다."
        report["evidence_sections"]["risks"][0]["evidence_snippets"] = [
            "정가가 비싸서 할인할 때 사는 편이 낫다.",
            "가격 대비 볼륨이 아쉽다는 생각이 든다.",
        ]
        plan = build_repair_plan(report)
        hold_types = {hold["failure_type"] for hold in plan["holds"]}
        self.assertIn("evidence_mismatch", hold_types)

    def test_evidence_mismatch_can_plan_candidate_reselection(self):
        report = _report_with_duplicate_and_generic()
        report["evidence_sections"]["risks"][0]["title"] = "버그와 오류가 많다는 반응"
        report["evidence_sections"]["risks"][0]["theme"] = "기술 문제"
        report["evidence_sections"]["risks"][0]["why_it_matters"] = "버그와 오류가 흐름을 끊습니다."
        report["evidence_sections"]["risks"][0]["explanation"] = "버그와 오류가 흐름을 끊습니다."
        report["evidence_sections"]["risks"][0]["evidence_snippets"] = [
            "정가가 비싸서 할인할 때 사는 편이 낫다.",
            "가격 대비 볼륨이 아쉽다는 생각이 든다.",
        ]
        report["evidence_sections"]["risks"][0]["evidence_candidate_snippets"] = [
            "버그 때문에 진행이 막히는 일이 있습니다.",
            "오류와 크래시가 있어 플레이 흐름이 끊깁니다.",
            "가격 대비 볼륨이 아쉽습니다.",
        ]

        plan = build_repair_plan(report)
        actions = [action for action in plan["actions"] if action["action"] == "reselect_evidence_snippets"]
        self.assertTrue(actions)
        self.assertEqual(actions[0]["safety_level"], "review_required")
        self.assertGreaterEqual(len(actions[0]["replacement_text"]), 2)

    def test_phrase_bank_filters_noisy_phrases(self):
        report = _report_with_duplicate_and_generic()
        report["evidence_sections"]["strengths"][0]["evidence_snippets"] = [
            "스토리와 캐릭터가 좋아서 여운이 오래 남는다.",
            "씨발 진짜 너무 그냥 게임을 하다가 아서의 이야기에 몰입했다.",
            "갓겜이라길래 사놓고 안땡겨서 안하다가 같은 긴 잡음 문장입니다.",
        ]
        claims = build_claim_ledger(report)
        phrase_bank = build_phrase_bank(claims)
        phrases = phrase_bank["str_1"]
        joined = " ".join(phrases)

        self.assertNotIn("씨발", joined)
        self.assertNotIn("갓겜이라길래 사놓고", joined)
        self.assertIn("스토리", joined)

    def test_repair_does_not_reuse_same_claim_for_many_slots(self):
        report = _report_with_duplicate_and_generic()
        semantic_result = {
            "status": "fail",
            "failure_count": 2,
            "critical_failure_count": 2,
            "failures": [
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": "top_strengths[1]",
                    "best_claim_id": "str_1",
                    "best_score": 0.2,
                    "text": "강점 후보 1",
                },
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": "top_strengths[2]",
                    "best_claim_id": "str_1",
                    "best_score": 0.2,
                    "text": "강점 후보 2",
                },
            ],
        }

        plan = build_repair_plan(report, semantic_result=semantic_result)
        self.assertEqual(
            len([action for action in plan["actions"] if action.get("claim_id") == "str_1"]),
            1,
        )
        hold_types = {hold["hold_type"] for hold in plan["holds"]}
        self.assertIn("duplicate_rewrite_source_hold", hold_types)

    def test_repair_does_not_rewrite_from_mismatched_claim(self):
        report = _report_with_duplicate_and_generic()
        semantic_result = {
            "status": "fail",
            "failure_count": 2,
            "critical_failure_count": 2,
            "failures": [
                {
                    "type": "evidence_mismatch",
                    "severity": "critical",
                    "claim_id": "str_1",
                    "text": "사건과 인물의 여운이 오래 남는다는 반응",
                },
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": "top_strengths[1]",
                    "best_claim_id": "str_1",
                    "best_score": 0.2,
                    "text": "강점 후보",
                },
            ],
        }

        plan = build_repair_plan(report, semantic_result=semantic_result)
        hold_types = {hold["hold_type"] for hold in plan["holds"]}
        self.assertIn("invalid_rewrite_source_hold", hold_types)
        self.assertFalse(
            any(
                action.get("action") == "rewrite_from_best_claim"
                and action.get("claim_id") == "str_1"
                for action in plan["actions"]
            )
        )

    def test_apply_safe_repair_actions_only_drops_duplicate_blocks(self):
        report = _report_with_duplicate_and_generic()
        plan = build_repair_plan(report)

        next_report, summary = apply_safe_repair_actions(report, plan)

        self.assertEqual(summary["applied_count"], 1)
        self.assertEqual(summary["applied"][0]["action"], "drop_duplicate_claim")
        risk_ids = [
            block.get("block_id")
            for block in next_report["evidence_sections"]["risks"]
        ]
        self.assertEqual(risk_ids, ["risk_1"])
        self.assertEqual(
            report["evidence_sections"]["risks"][1]["block_id"],
            "risk_2",
            "original payload must not be mutated",
        )

    def test_apply_safe_repair_actions_skips_review_required_actions(self):
        report = _report_with_duplicate_and_generic()
        semantic_result = {
            "status": "fail",
            "failure_count": 1,
            "critical_failure_count": 1,
            "failures": [
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": "top_risks[1]",
                    "best_claim_id": "risk_1",
                    "best_score": 0.14,
                    "text": "느린 진행 진행이 길어져 피로할 수 있습니다.",
                }
            ],
        }
        plan = build_repair_plan(report, semantic_result=semantic_result)

        next_report, summary = apply_safe_repair_actions(report, plan)

        self.assertEqual(summary["applied_count"], 0)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["skipped"][0]["reason"], "not_safe")
        self.assertEqual(next_report, report)


if __name__ == "__main__":
    unittest.main()
