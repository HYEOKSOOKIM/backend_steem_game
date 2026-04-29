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
from .text_features import clean_text, families, jaccard, normalize_text, tokens

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
    "evidence_mismatch",
    "text_corruption",
    "evidence_duplicate_title",
    "evidence_theme_title_mismatch",
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
    failures.extend(_check_text_corruption(report_payload))
    failures.extend(_check_evidence_block_copy(report_payload))
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


def _check_text_corruption(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for field, text in _collect_corruption_targets(report_payload):
        normalized = str(text or "").strip()
        if not normalized:
            continue
        if not _looks_corrupted(normalized):
            continue
        key = (field, normalized)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            {
                "type": "text_corruption",
                "severity": "critical",
                "field": field,
                "message": "사용자 노출 문구에 인코딩이 깨진 흔적이 있습니다.",
                "text": normalized,
            }
        )
    return failures


def _check_evidence_block_copy(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for section_name, blocks in (report_payload.get("evidence_sections", {}) or {}).items():
        if not isinstance(blocks, list):
            continue
        seen_titles: dict[tuple[str, str], dict[str, Any]] = {}
        for index, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                continue
            stance = "positive" if section_name == "strengths" else "negative"
            title = clean_text(block.get("title", ""))
            theme = clean_text(block.get("theme", ""))
            title_key = _normalize_for_duplicate(title)
            if title_key:
                dup_key = (stance, title_key)
                previous = seen_titles.get(dup_key)
                if previous is not None:
                    failures.append(
                        {
                            "type": "evidence_duplicate_title",
                            "severity": "critical",
                            "field": f"evidence_sections.{section_name}[{index}].title",
                            "message": "같은 stance의 evidence block title이 반복됩니다.",
                            "text": title,
                            "matched_block_id": previous.get("block_id"),
                            "block_id": block.get("block_id"),
                        }
                    )
                else:
                    seen_titles[dup_key] = block
            theme_families = families(theme)
            title_families = families(" ".join(str(block.get(key, "") or "") for key in ("title", "why_it_matters", "explanation")))
            if theme_families and title_families and not (theme_families & title_families):
                failures.append(
                    {
                        "type": "evidence_theme_title_mismatch",
                        "severity": "critical",
                        "field": f"evidence_sections.{section_name}[{index}]",
                        "message": "evidence block의 theme와 title/설명 주제가 어긋납니다.",
                        "text": title,
                        "block_id": block.get("block_id"),
                        "theme_families": sorted(theme_families),
                        "title_families": sorted(title_families),
                    }
                )
    return failures


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
                    "severity": "warning",
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
        threshold = 0.08 if str(item.get("strict", "true")) == "false" else 0.14
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


def _collect_corruption_targets(report_payload: dict[str, Any]) -> list[tuple[str, str]]:
    report_display = dict(report_payload.get("report_display", {}) or {})
    targets: list[tuple[str, str]] = []

    def add(field: str, value: Any) -> None:
        if isinstance(value, str):
            targets.append((field, value))

    add("headline", report_display.get("headline"))
    add("buy_timing_summary", report_display.get("buy_timing_summary"))
    add("disclaimer", report_payload.get("disclaimer"))

    for index, value in enumerate(list(report_display.get("good_for", []) or []), start=1):
        add(f"good_for[{index}]", value)
    for index, value in enumerate(list(report_display.get("not_good_for", []) or []), start=1):
        add(f"not_good_for[{index}]", value)
    for index, value in enumerate(list(report_display.get("top_strengths", []) or []), start=1):
        if isinstance(value, dict):
            add(f"top_strengths[{index}].title", value.get("title"))
            add(f"top_strengths[{index}].summary", value.get("summary"))
    for index, value in enumerate(list(report_display.get("top_risks", []) or []), start=1):
        if isinstance(value, dict):
            add(f"top_risks[{index}].title", value.get("title"))
            add(f"top_risks[{index}].summary", value.get("summary"))

    for section_name in ("evidence_sections", "evidence_reviews"):
        section = report_payload.get(section_name)
        groups: list[tuple[str, list[Any]]] = []
        if isinstance(section, dict):
            for group_name, blocks in section.items():
                if isinstance(blocks, list):
                    groups.append((f"{section_name}.{group_name}", blocks))
        elif isinstance(section, list):
            groups.append((section_name, list(section)))
        for group_field, blocks in groups:
            for index, block in enumerate(blocks, start=1):
                if not isinstance(block, dict):
                    continue
                add(f"{group_field}[{index}].title", block.get("title"))
                add(f"{group_field}[{index}].theme", block.get("theme"))
                add(f"{group_field}[{index}].why_it_matters", block.get("why_it_matters"))
                add(f"{group_field}[{index}].explanation", block.get("explanation"))

    return targets


def _looks_corrupted(text: str) -> bool:
    stripped = "".join(ch for ch in text if not ch.isspace())
    if "???" in text:
        return True
    if "??" in text and len(stripped) >= 6:
        return True
    question_count = text.count("?")
    if question_count < 3:
        return False
    return (question_count / max(len(stripped), 1)) >= 0.2


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
