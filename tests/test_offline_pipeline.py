"""Tests for offline pipeline entrypoint helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.pipeline.offline_pipeline import _parse_review_pages


class OfflinePipelineTests(unittest.TestCase):
    def test_parse_review_pages_all(self):
        self.assertEqual(_parse_review_pages("all"), "all")
        self.assertEqual(_parse_review_pages(" ALL "), "all")

    def test_parse_review_pages_numeric(self):
        self.assertEqual(_parse_review_pages("4"), 4)
        self.assertEqual(_parse_review_pages(200), 200)

    def test_parse_review_pages_out_of_range(self):
        with self.assertRaises(ValueError):
            _parse_review_pages(0)
        with self.assertRaises(ValueError):
            _parse_review_pages(201)


if __name__ == "__main__":
    unittest.main()


