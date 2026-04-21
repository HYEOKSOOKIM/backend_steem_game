"""Tests for final Korean proofreader step."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.korean_report_proofreader import rule_proofread_text


class KoreanReportProofreaderTests(unittest.TestCase):
    def test_rule_proofreader_fixes_particle_errors(self):
        source = "일반 버그이 거슬릴 수 있어  구매 전 확인이 필요 합니다."
        corrected = rule_proofread_text(source)
        self.assertIn("버그가 거슬릴", corrected)
        self.assertIn("필요", corrected)
        self.assertNotIn("버그이", corrected)


if __name__ == "__main__":
    unittest.main()



