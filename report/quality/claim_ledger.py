"""Build evidence-backed claim records for generated reports."""

from __future__ import annotations

from typing import Any

from .text_features import clean_text, families, tokens


def build_claim_ledger(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return evidence-backed claims extracted from report evidence sections."""
    evidence_sections = dict(report_payload.get("evidence_sections", {}) or {})
    claims: list[dict[str, Any]] = []
    for section_key, stance in (("strengths", "positive"), ("risks", "negative")):
        for index, block in enumerate(list(evidence_sections.get(section_key, []) or []), start=1):
            if not isinstance(block, dict):
                continue
            snippets = [str(item) for item in list(block.get("evidence_snippets", []) or []) if str(item).strip()]
            candidate_snippets = _candidate_snippets(block)
            claim_text = " ".join(
                str(block.get(key, "") or "")
                for key in ("title", "theme", "why_it_matters", "explanation")
            )
            support_text = " ".join([claim_text, *snippets])
            claim_id = str(block.get("block_id") or f"{section_key}_{index}")
            claims.append(
                {
                    "claim_id": claim_id,
                    "section": section_key,
                    "stance": stance,
                    "title": clean_text(block.get("title", "")),
                    "theme": clean_text(block.get("theme", "")),
                    "why_it_matters": clean_text(block.get("why_it_matters", "")),
                    "aspect_keys": [str(item) for item in list(block.get("aspect_keys", []) or [])],
                    "claim_families": families(claim_text),
                    "snippet_families": families(" ".join(snippets)),
                    "support_families": families(support_text),
                    "support_tokens": tokens(support_text),
                    "evidence_snippets": snippets,
                    "evidence_candidate_snippets": candidate_snippets,
                    "snippet_count": len(snippets),
                    "support_score": _support_score(block, snippets),
                }
            )
    return claims


def _candidate_snippets(block: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for item in list(block.get("evidence_candidate_items", []) or []):
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            if text:
                candidates.append(text)
    for item in list(block.get("evidence_candidate_snippets", []) or []):
        text = str(item).strip()
        if text:
            candidates.append(text)
    for item in list(block.get("evidence_snippets", []) or []):
        text = str(item).strip()
        if text:
            candidates.append(text)

    seen: set[str] = set()
    unique: list[str] = []
    for text in candidates:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique[:12]


def _support_score(block: dict[str, Any], snippets: list[str]) -> float:
    score = 0.0
    consensus = str(block.get("consensus_level", "")).strip().lower()
    if consensus == "high":
        score += 0.35
    elif consensus == "medium":
        score += 0.2
    score += min(len(snippets), 3) * 0.15
    quality = str(block.get("evidence_quality_level", "")).strip().lower()
    if quality == "strict":
        score += 0.2
    elif quality == "relaxed":
        score += 0.1
    elif quality == "guaranteed_fill":
        score += 0.05
    if int(block.get("mention_count", 0) or 0) >= 100:
        score += 0.1
    return round(min(score, 1.0), 4)
