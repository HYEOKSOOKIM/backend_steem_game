"""Build report.v1 payloads from prototype analysis artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from math import log1p
from typing import Any

from report.models.report_v1 import build_empty_report_v1

MAX_EVIDENCE_CATEGORY_COUNT = 3
MAX_EVIDENCE_BLOCK_COUNT = 8
MAX_EVIDENCE_QUOTE_CHARS = 220


def build_report_v1_from_artifacts(
    *,
    appid: int,
    metadata: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    processed_reviews: list[dict[str, Any]] | None,
    window_days: int = 90,
) -> dict[str, Any]:
    """Map legacy artifacts into report.v1 schema."""
    _ = metadata  # Reserved for future expansion.
    analysis = analysis or {}
    processed_reviews = processed_reviews or []
    snapshot_at = _resolve_snapshot_at(analysis)

    report = build_empty_report_v1(
        app_id=appid,
        snapshot_at=snapshot_at,
        window_days=window_days,
    )

    included_reviews = [
        review for review in processed_reviews if bool(review.get("included_in_analysis"))
    ]
    total_reviews = len(processed_reviews)
    eligible_reviews = len(included_reviews)

    issue_signals = analysis.get("issue_signals", {})
    if not isinstance(issue_signals, dict):
        issue_signals = {}

    category_rows = _build_category_rows(issue_signals, eligible_reviews)
    theme_rows = _build_top_themes(issue_signals, eligible_reviews)
    evidence_rows = _build_evidence_blocks(included_reviews, category_rows, issue_signals)
    trend_summary = _build_trend_summary(issue_signals)
    reviewer_segment_rows = _build_reviewer_segments(included_reviews)

    decision = _build_decision_snapshot(
        issue_signals=issue_signals,
        category_rows=category_rows,
        analysis=analysis,
        eligible_reviews=eligible_reviews,
    )

    report["data_quality"] = {
        "review_count_total": total_reviews,
        "review_count_eligible": eligible_reviews,
        "confidence": round(float(decision["decision_confidence"]), 2),
        "flags": _build_quality_flags(
            eligible_reviews=eligible_reviews,
            sample_size_tier=str(analysis.get("sample_size_tier", "")),
            trend_status=str(analysis.get("trend_status", "")),
        ),
    }
    report["snapshot"] = decision
    report["category_distribution"] = [
        {
            "category": row["category"],
            "share": row["share"],
            "mentions": row["mentions"],
        }
        for row in category_rows
    ]
    report["sentiment_x_category"] = [
        {
            "category": row["category"],
            "positive": row["positive"],
            "negative": row["negative"],
            "net": row["net"],
            "impact_rank": idx + 1,
        }
        for idx, row in enumerate(
            sorted(
                category_rows,
                key=lambda item: float(item["impact_score"]),
                reverse=True,
            )
        )
    ]
    report["top_themes"] = theme_rows
    report["evidence_blocks"] = evidence_rows
    report["trend"] = {
        "summary": trend_summary,
        "spikes": [],
    }
    report["reviewer_segment"] = reviewer_segment_rows
    report["final_recommendation"] = _build_final_recommendation(decision, category_rows, trend_summary)

    return report


def _resolve_snapshot_at(analysis: dict[str, Any]) -> str:
    generated_at = analysis.get("generated_at")
    if isinstance(generated_at, str) and generated_at.strip():
        return generated_at
    return datetime.now(UTC).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_category_rows(issue_signals: dict[str, Any], eligible_reviews: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_mentions = sum(
        _safe_int(signal.get("mention_count"))
        for signal in issue_signals.values()
        if isinstance(signal, dict)
    )

    for category, signal in issue_signals.items():
        if not isinstance(signal, dict):
            continue
        mentions = _safe_int(signal.get("mention_count"))
        negative = max(0.0, min(1.0, _safe_float(signal.get("negative_ratio"))))
        positive = max(0.0, min(1.0, 1.0 - negative))
        net = round(positive - negative, 4)
        share = (mentions / total_mentions) if total_mentions > 0 else 0.0
        volume_norm = (mentions / max(eligible_reviews, 1)) if eligible_reviews > 0 else 0.0
        impact_score = volume_norm * abs(net)
        rows.append(
            {
                "category": category,
                "mentions": mentions,
                "share": round(share, 4),
                "positive": round(positive, 4),
                "negative": round(negative, 4),
                "net": net,
                "impact_score": round(impact_score, 4),
            }
        )

    rows.sort(key=lambda item: (item["mentions"], item["impact_score"]), reverse=True)
    return rows


def _build_top_themes(issue_signals: dict[str, Any], eligible_reviews: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category, signal in issue_signals.items():
        if not isinstance(signal, dict):
            continue
        mentions = _safe_int(signal.get("mention_count"))
        negative = max(0.0, min(1.0, _safe_float(signal.get("negative_ratio"))))
        themes = signal.get("themes", [])
        if not isinstance(themes, list):
            continue

        for theme in themes[:3]:
            label = str(theme).strip()
            if not label:
                continue
            polarity = "negative" if negative > 0.55 else "positive" if negative < 0.45 else "neutral"
            coverage = mentions / max(eligible_reviews, 1) if eligible_reviews > 0 else 0.0
            impact = coverage * (negative if polarity == "negative" else max(0.0, 1.0 - negative))
            rows.append(
                {
                    "theme_code": _slugify_theme(label),
                    "label": label,
                    "category": category,
                    "polarity": polarity,
                    "coverage": round(coverage, 4),
                    "impact": round(float(impact), 4),
                }
            )

    rows.sort(key=lambda item: item["impact"], reverse=True)
    return rows[:8]


def _slugify_theme(value: str) -> str:
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    compact = "_".join(part for part in base.split("_") if part)
    return compact or "theme"


def _review_weight(review: dict[str, Any]) -> float:
    helpful = _safe_int(review.get("num_reviews"), 0)
    playtime_hours = _safe_float(review.get("playtime_at_review_hours"), 0.0)
    return (1.0 + min(1.0, log1p(max(helpful, 0)) / 3.0)) * (1.0 + min(0.5, log1p(max(playtime_hours, 0.0)) / 6.0))


def _build_evidence_blocks(
    included_reviews: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
    issue_signals: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    top_categories = [row["category"] for row in category_rows[:MAX_EVIDENCE_CATEGORY_COUNT]]
    block_id = 1

    for category in top_categories:
        tagged = [
            review
            for review in included_reviews
            if category in (review.get("category_tags") or [])
        ]
        if not tagged:
            continue

        ranked = sorted(
            tagged,
            key=lambda review: _review_weight(review),
            reverse=True,
        )
        positive = next((review for review in ranked if bool(review.get("voted_up"))), None)
        negative = next((review for review in ranked if not bool(review.get("voted_up"))), None)

        for review, polarity in ((negative, "negative"), (positive, "positive")):
            if review is None:
                continue
            quote = _normalize_evidence_quote(review.get("review_text"))
            if quote is None:
                continue
            timestamp = _safe_int(review.get("timestamp_created"))
            created_at = (
                datetime.fromtimestamp(timestamp, tz=UTC).date().isoformat()
                if timestamp > 0
                else None
            )
            blocks.append(
                {
                    "id": f"ev_{block_id:03d}",
                    "category": category,
                    "theme_code": _first_theme_code(issue_signals.get(category)),
                    "polarity": polarity,
                    "quote": quote,
                    "review_meta": {
                        "created_at": created_at,
                        "playtime_minutes": int(max(0.0, _safe_float(review.get("playtime_at_review_hours")) * 60)),
                        "votes_up": _safe_int(review.get("num_reviews"), 0),
                    },
                    "evidence_score": round(_review_weight(review), 4),
                }
            )
            block_id += 1

    return blocks[:MAX_EVIDENCE_BLOCK_COUNT]


def _normalize_evidence_quote(raw_text: Any) -> str | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    return text[:MAX_EVIDENCE_QUOTE_CHARS]


def _first_theme_code(signal: Any) -> str | None:
    if not isinstance(signal, dict):
        return None
    themes = signal.get("themes")
    if not isinstance(themes, list) or not themes:
        return None
    return _slugify_theme(str(themes[0]))


def _build_trend_summary(issue_signals: dict[str, Any]) -> dict[str, Any]:
    up = 0
    down = 0
    flat = 0
    limited = 0
    for signal in issue_signals.values():
        if not isinstance(signal, dict):
            continue
        trend = str(signal.get("recent_trend", "flat")).strip().lower()
        if trend == "up":
            up += 1
        elif trend == "down":
            down += 1
        elif trend == "limited":
            limited += 1
        else:
            flat += 1

    direction = "limited" if limited > 0 else "worsening" if up > down else "improving" if down > up else "stable"
    return {
        "direction": direction,
        "up_categories": up,
        "down_categories": down,
        "flat_categories": flat,
        "limited_categories": limited,
    }


def _build_reviewer_segments(included_reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments = {
        "new": {"min": 0.0, "max": 5.0, "label": "0-5h"},
        "mid": {"min": 5.0, "max": 20.0, "label": "5-20h"},
        "core": {"min": 20.0, "max": float("inf"), "label": "20h+"},
    }
    rows: list[dict[str, Any]] = []

    for segment_key, bound in segments.items():
        seg_reviews = []
        for review in included_reviews:
            hours = _safe_float(review.get("playtime_at_review_hours"), 0.0)
            if hours < bound["min"]:
                continue
            if hours > bound["max"]:
                continue
            seg_reviews.append(review)

        sample = len(seg_reviews)
        if sample == 0:
            continue
        positive = sum(1 for review in seg_reviews if bool(review.get("voted_up")))
        negative = sample - positive
        top_risk = _segment_top_risk(seg_reviews)
        rows.append(
            {
                "segment": segment_key,
                "segment_label": bound["label"],
                "sample": sample,
                "net_sentiment": round((positive - negative) / sample, 4),
                "top_risk": top_risk,
            }
        )

    return rows


def _segment_top_risk(seg_reviews: list[dict[str, Any]]) -> str | None:
    counter: dict[str, int] = {}
    for review in seg_reviews:
        if bool(review.get("voted_up")):
            continue
        tags = review.get("category_tags") or []
        if not isinstance(tags, list):
            continue
        for category in tags:
            key = str(category)
            counter[key] = counter.get(key, 0) + 1
    if not counter:
        return None
    return max(counter.items(), key=lambda item: item[1])[0]


def _build_decision_snapshot(
    *,
    issue_signals: dict[str, Any],
    category_rows: list[dict[str, Any]],
    analysis: dict[str, Any],
    eligible_reviews: int,
) -> dict[str, Any]:
    weighted_mentions = 0
    weighted_negative = 0.0
    for signal in issue_signals.values():
        if not isinstance(signal, dict):
            continue
        mentions = _safe_int(signal.get("mention_count"), 0)
        negative = max(0.0, min(1.0, _safe_float(signal.get("negative_ratio"), 0.0)))
        weighted_mentions += mentions
        weighted_negative += mentions * negative

    risk_index = (weighted_negative / weighted_mentions) if weighted_mentions > 0 else 0.5
    decision_score = round(max(0.0, min(100.0, (1.0 - risk_index) * 100.0)), 2)
    decision_label = _decision_label_from_risk(risk_index)

    sample_tier = str(analysis.get("sample_size_tier", ""))
    base_conf = {
        "empty": 0.0,
        "very_small": 35.0,
        "small": 55.0,
        "medium": 75.0,
        "large": 85.0,
    }.get(sample_tier, 60.0)
    if str(analysis.get("trend_status")) == "limited":
        base_conf -= 10.0
    if eligible_reviews < 30:
        base_conf -= 5.0
    decision_confidence = round(max(0.0, min(95.0, base_conf)), 2)

    key_drivers = []
    for row in category_rows[:3]:
        key_drivers.append(
            {
                "type": "risk" if float(row["negative"]) >= 0.5 else "benefit",
                "category": row["category"],
                "strength": round(float(row["impact_score"]), 4),
            }
        )

    return {
        "decision_label": decision_label,
        "decision_score": decision_score,
        "decision_confidence": decision_confidence,
        "key_drivers": key_drivers,
    }


def _decision_label_from_risk(risk_index: float) -> str:
    if risk_index >= 0.65:
        return "avoid"
    if risk_index >= 0.50:
        return "wait"
    if risk_index >= 0.35:
        return "buy_on_sale"
    return "buy_now"


def _build_quality_flags(
    *,
    eligible_reviews: int,
    sample_size_tier: str,
    trend_status: str,
) -> list[str]:
    flags: list[str] = []
    if eligible_reviews < 50:
        flags.append("low_sample")
    if sample_size_tier in {"very_small", "small"}:
        flags.append("small_sample_tier")
    if trend_status == "limited":
        flags.append("limited_trend")
    if not flags:
        flags.append("ok")
    return flags


def _build_final_recommendation(
    decision: dict[str, Any],
    category_rows: list[dict[str, Any]],
    trend_summary: dict[str, Any],
) -> dict[str, Any]:
    label = str(decision.get("decision_label", "wait"))
    top_risk = next((row["category"] for row in category_rows if float(row["negative"]) >= 0.5), None)
    top_benefit = next((row["category"] for row in category_rows if float(row["negative"]) < 0.5), None)

    if label == "buy_now":
        reason = f"Positive signals are dominant in {top_benefit or 'core categories'}."
        conditions = ["Purchase can be considered at the current price."]
    elif label == "buy_on_sale":
        reason = f"Strengths are clear, but {top_risk or 'key risks'} should be checked before buying."
        conditions = ["Buy during discount windows.", "Re-check recent user feedback."]
    elif label == "wait":
        reason = f"Uncertainty remains around {top_risk or 'key risks'}, so waiting is recommended."
        conditions = ["Wait for the next patch/update.", "Re-check trend over the next 2-4 weeks."]
    else:
        reason = f"Risk signals around {top_risk or 'multiple categories'} are strong right now."
        conditions = ["Avoid purchase until core issues are reduced."]

    watch_items = [row["category"] for row in category_rows[:3]]
    if trend_summary.get("direction") == "worsening":
        watch_items.append("recent_trend")

    return {
        "label": label,
        "reason_summary": reason,
        "conditions_to_buy": conditions,
        "watch_items": watch_items[:4],
        "inputs": {
            "risk_index": round(1.0 - (_safe_float(decision.get("decision_score")) / 100.0), 4),
            "confidence": _safe_float(decision.get("decision_confidence")),
            "trend_direction": trend_summary.get("direction", "stable"),
        },
    }
