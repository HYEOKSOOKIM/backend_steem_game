"""Schema helpers for purchase-decision report payload (v1)."""

from __future__ import annotations

from typing import Any

REPORT_V1_SCHEMA_VERSION = "report.v1"


def build_empty_report_v1(
    *,
    app_id: int,
    snapshot_at: str,
    window_days: int = 90,
) -> dict[str, Any]:
    """Return a minimal valid report.v1 payload."""
    return {
        "schema_version": REPORT_V1_SCHEMA_VERSION,
        "app_id": app_id,
        "snapshot_at": snapshot_at,
        "window_days": window_days,
        "data_quality": {
            "review_count_total": 0,
            "review_count_eligible": 0,
            "confidence": 0.0,
            "flags": ["insufficient_data"],
        },
        "snapshot": {
            "decision_label": "wait",
            "decision_score": 0.0,
            "decision_confidence": 0.0,
            "key_drivers": [],
        },
        "category_distribution": [],
        "sentiment_x_category": [],
        "top_themes": [],
        "evidence_blocks": [],
        "trend": {
            "summary": {
                "direction": "limited",
                "up_categories": 0,
                "down_categories": 0,
                "flat_categories": 0,
            },
            "spikes": [],
        },
        "reviewer_segment": [],
        "final_recommendation": {
            "label": "wait",
            "reason_summary": "Sample size is limited, so a conservative recommendation is returned.",
            "conditions_to_buy": [],
            "watch_items": [],
            "inputs": {
                "risk_index": 0.0,
                "confidence": 0.0,
            },
        },
    }


def is_report_v1_payload(value: Any) -> bool:
    """Quick structural guard for report.v1 payloads."""
    if not isinstance(value, dict):
        return False

    if value.get("schema_version") != REPORT_V1_SCHEMA_VERSION:
        return False

    required_top_level = {
        "app_id",
        "snapshot_at",
        "data_quality",
        "snapshot",
        "category_distribution",
        "sentiment_x_category",
        "top_themes",
        "evidence_blocks",
        "trend",
        "final_recommendation",
    }
    if not required_top_level.issubset(set(value.keys())):
        return False

    if not isinstance(value.get("data_quality"), dict):
        return False
    if not isinstance(value.get("snapshot"), dict):
        return False
    if not isinstance(value.get("final_recommendation"), dict):
        return False

    return True
