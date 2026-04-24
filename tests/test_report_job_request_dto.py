"""Tests for report job create request DTO validation."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.api.dto_jobs import ReportJobCreateRequestDTO


class ReportJobCreateRequestDTOTests(unittest.TestCase):
    def test_defaults_are_applied(self):
        dto = ReportJobCreateRequestDTO.model_validate({"appid": 2456740})

        self.assertEqual(dto.appid, 2456740)
        self.assertEqual(dto.review_pages, "all")
        self.assertFalse(dto.use_llm_fallback)
        self.assertEqual(dto.max_llm_reviews, 50)
        self.assertEqual(dto.llm_timeout_seconds, 20)
        self.assertEqual(dto.llm_retry_limit, 2)
        self.assertAlmostEqual(dto.llm_min_confidence, 0.70)
        self.assertIsNone(dto.game_name)

    def test_review_pages_accepts_numeric_string(self):
        dto = ReportJobCreateRequestDTO.model_validate(
            {"appid": 2456740, "review_pages": "12"}
        )

        self.assertEqual(dto.review_pages, 12)

    def test_review_pages_rejects_out_of_range_value(self):
        with self.assertRaises(ValidationError):
            ReportJobCreateRequestDTO.model_validate(
                {"appid": 2456740, "review_pages": 0}
            )

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValidationError):
            ReportJobCreateRequestDTO.model_validate(
                {"appid": 2456740, "unexpected": "x"}
            )


if __name__ == "__main__":
    unittest.main()
