"""Tests for standardized API error response format."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app


class ApiErrorFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_validation_error_returns_standard_payload(self):
        response = self.client.post("/api/v1/reports/jobs", json={})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertIn("error_code", payload)
        self.assertIn("detail", payload)
        self.assertIn("hint", payload)
        self.assertEqual(payload["error_code"], "request_validation_error")

    def test_invalid_section_returns_standard_payload(self):
        response = self.client.get("/api/v1/reports/2456740/sections/not-a-section")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error_code"], "invalid_section")
        self.assertIn("section must be one of:", payload["detail"])
        self.assertIn("Use one of:", payload["hint"])

    def test_missing_job_returns_standard_payload(self):
        response = self.client.get("/api/v1/reports/jobs/missing-job-id")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error_code"], "job_not_found")
        self.assertIn("was not found", payload["detail"])
        self.assertIn("Create a new job", payload["hint"])


if __name__ == "__main__":
    unittest.main()

