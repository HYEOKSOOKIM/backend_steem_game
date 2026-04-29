"""Deterministic semantic QA for generated report payloads.

The release gate checks whether a report is complete. This module checks the
more important question: whether display copy is still grounded in evidence.
It intentionally avoids game-specific rules. The unit of comparison is a small
set of reusable concept families such as story, pacing, stability, and price.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .claim_ledger import build_claim_ledger
from .phrase_bank import build_phrase_bank
from .text_features import families, jaccard, normalize_text, tokens

GENERIC_COPY_MARKERS = (
    "핵심 플레이 감각",
    "핵심 플레이",
    "플레이 흐름의 안정감",
    "플레이 흐름이 안정",
    "손에 익을수록",
    "장점은 분명",
    "체감이 좋아",
)

CRITICAL_FAILURE_TYPES = {
    "unsupported_claim",
    "theme_drift",
    "evidence_mismatch",
}


def evaluate_report_semantics(
    report_payload: dict[str, Any],
    *,
    analysis_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic semantic QA results for one report payload."""
    del analysis_payload  # Reserved for claim-ledger expansion in the next step.
    report_display = dict(report_payload.get("report_display", {}) or {})
    claims = build_claim_ledger(report_payload)
    phrase_bank = build_phrase_bank(claims)

    failures: list[dict[str, Any]] = []
    failures.extend(_check_duplicate_claims(claims))
    failures.extend(_check_evidence_block_alignment(claims))
    failures.extend(_check_display_grounding(report_display, claims))
    failures.extend(_check_generic_copy(report_display))

    severity_counts = Counter(str(item.get("severity", "warning")) for item in failures)
    critical_count = sum(
        1
        for item in failures
        if item.get("type") in CRITICAL_FAILURE_TYPES or item.get("severity") == "critical"
    )
    status = "fail" if critical_count else ("warn" if failures else "pass")
    return {
        "status": status,
        "claim_count": len(claims),
        "phrase_bank_claim_count": len(phrase_bank),
        "failure_count": len(failures),
        "critical_failure_count": critical_count,
        "severity_counts": dict(severity_counts),
        "failures": failures,
    }


def _check_duplicate_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    seen_titles: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in claims:
        title_key = _normalize_for_duplicate(str(claim.get("title", "")))
        if not title_key:
            continue
        key = (str(claim.get("stance", "")), title_key)
        previous = seen_titles.get(key)
        if previous is not None:
            failures.append(
                {
                    "type": "duplicate_claim",
                    "severity": "warning",
                    "claim_id": claim.get("claim_id"),
                    "matched_claim_id": previous.get("claim_id"),
                    "message": "같은 stance 안에서 evidence claim 제목이 반복됩니다.",
                    "text": claim.get("title"),
                }
            )
        else:
            seen_titles[key] = claim
    return failures


def _check_evidence_block_alignment(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for claim in claims:
        claim_families = set(claim.get("claim_families", set()))
        snippet_families = set(claim.get("snippet_families", set()))
        if not claim_families or not snippet_families:
            continue
        overlap = claim_families & snippet_families
        if not overlap:
            failures.append(
                {
                    "type": "evidence_mismatch",
                    "severity": "critical",
                    "claim_id": claim.get("claim_id"),
                    "message": "evidence 제목/설명이 실제 스니펫의 주제와 맞지 않습니다.",
                    "claim_families": sorted(claim_families),
                    "snippet_families": sorted(snippet_families),
                    "text": claim.get("title"),
                }
            )
    return failures


def _check_display_grounding(report_display: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    display_items = _collect_display_items(report_display)
    for item in display_items:
        text = str(item.get("text", "")).strip()
        stance = str(item.get("stance", "mixed"))
        item_families = families(text)
        if not text or not item_families:
            continue

        claim_pool = claims if stance == "mixed" else [claim for claim in claims if claim.get("stance") == stance]
        support_union: set[str] = set()
        for claim in claim_pool:
            support_union.update(set(claim.get("support_families", set())))
        unsupported = item_families - support_union
        if unsupported:
            failures.append(
                {
                    "type": "unsupported_claim",
                    "severity": "critical",
                    "field": item.get("field"),
                    "message": "display 문장에 evidence claim에서 지지되지 않는 주제 가족이 포함되어 있습니다.",
                    "unsupported_families": sorted(unsupported),
                    "text": text,
                }
            )
            continue

        best = _best_claim_match(text, item_families, claim_pool)
        threshold = 0.12 if str(item.get("strict", "true")) == "false" else 0.18
        if best["score"] < threshold:
            failures.append(
                {
                    "type": "theme_drift",
                    "severity": "critical",
                    "field": item.get("field"),
                    "message": "display 문장이 어떤 evidence claim과도 충분히 연결되지 않습니다.",
                    "best_claim_id": best.get("claim_id"),
                    "best_score": round(float(best.get("score", 0.0)), 4),
                    "text": text,
                }
            )
    return failures


def _check_generic_copy(report_display: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in _collect_display_items(report_display):
        text = str(item.get("text", ""))
        marker = next((marker for marker in GENERIC_COPY_MARKERS if marker in text), "")
        if marker:
            failures.append(
                {
                    "type": "generic_copy",
                    "severity": "warning",
                    "field": item.get("field"),
                    "message": "템플릿성 표현이 남아 있습니다. phrase bank 기반 치환 후보입니다.",
                    "marker": marker,
                    "text": text,
                }
            )
    return failures


def _collect_display_items(report_display: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    headline = str(report_display.get("headline", "") or "").strip()
    if headline:
        items.append({"field": "headline", "stance": "mixed", "text": headline, "strict": "false"})
    for index, value in enumerate(list(report_display.get("good_for", []) or []), start=1):
        items.append({"field": f"good_for[{index}]", "stance": "positive", "text": str(value), "strict": "false"})
    for index, value in enumerate(list(report_display.get("not_good_for", []) or []), start=1):
        items.append({"field": f"not_good_for[{index}]", "stance": "negative", "text": str(value), "strict": "false"})
    for index, value in enumerate(list(report_display.get("top_strengths", []) or []), start=1):
        if isinstance(value, dict):
            text = f"{value.get('title', '')} {value.get('summary', '')}"
            items.append({"field": f"top_strengths[{index}]", "stance": "positive", "text": text})
    for index, value in enumerate(list(report_display.get("top_risks", []) or []), start=1):
        if isinstance(value, dict):
            text = f"{value.get('title', '')} {value.get('summary', '')}"
            items.append({"field": f"top_risks[{index}]", "stance": "negative", "text": text})
    recent_state = report_display.get("recent_state")
    if isinstance(recent_state, dict):
        summary = str(recent_state.get("summary", "") or "").strip()
        if summary:
            items.append(
                {
                    "field": "recent_state.summary",
                    "stance": "mixed",
                    "text": summary,
                    "strict": "false",
                }
            )
    return items


def _best_claim_match(text: str, families: set[str], claims: list[dict[str, Any]]) -> dict[str, Any]:
    text_tokens = tokens(text)
    best = {"claim_id": None, "score": 0.0}
    for claim in claims:
        claim_families = set(claim.get("support_families", set()))
        claim_tokens = set(claim.get("support_tokens", set()))
        family_score = jaccard(families, claim_families)
        token_score = jaccard(text_tokens, claim_tokens)
        score = (family_score * 0.75) + (token_score * 0.25)
        if score > best["score"]:
            best = {"claim_id": claim.get("claim_id"), "score": score}
    return best


def _normalize_for_duplicate(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    for suffix in ("이 있다", "가 있다", "있다는 반응", "이라는 반응", "다는 반응", "반응이다", "반응"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalize_text(normalized)
