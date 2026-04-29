"""Select evidence claims that are safe enough to show in report display.

This module is intentionally small. It does not rewrite reports and it does
not decide adoption. It only answers one question: which existing evidence
claims are good enough to be used as display material?
"""

from __future__ import annotations

from typing import Any

from .claim_ledger import build_claim_ledger
from .text_features import normalize_text

DEFAULT_MIN_SUPPORT_SCORE = 0.45


def select_good_claims(
    report_payload: dict[str, Any],
    *,
    min_support_score: float = DEFAULT_MIN_SUPPORT_SCORE,
) -> dict[str, Any]:
    """Return selected/rejected evidence claims grouped by display side.

    The selector is deliberately conservative but not complicated:

    - a claim needs at least one evidence snippet
    - claim text and snippets need at least one shared concept family
    - weak support is rejected
    - duplicate claims in the same stance keep the stronger claim
    """
    claims = build_claim_ledger(report_payload)
    selected: dict[str, list[dict[str, Any]]] = {"strengths": [], "risks": []}
    rejected: list[dict[str, Any]] = []
    seen_by_side: dict[str, dict[str, tuple[int, dict[str, Any]]]] = {
        "strengths": {},
        "risks": {},
    }

    for claim in claims:
        side = str(claim.get("section", "")).strip()
        if side not in selected:
            rejected.append(_rejection(claim, "unknown_section", "알 수 없는 evidence section입니다."))
            continue

        reject_reason = _basic_reject_reason(claim, min_support_score=min_support_score)
        if reject_reason is not None:
            rejected.append(_rejection(claim, reject_reason[0], reject_reason[1]))
            continue

        key = _duplicate_key(claim)
        existing = seen_by_side[side].get(key)
        public_claim = _public_claim(claim)
        if existing is None:
            seen_by_side[side][key] = (len(selected[side]), public_claim)
            selected[side].append(public_claim)
            continue

        existing_index, existing_claim = existing
        current_score = float(public_claim.get("support_score", 0.0) or 0.0)
        existing_score = float(existing_claim.get("support_score", 0.0) or 0.0)
        if current_score > existing_score:
            rejected.append(
                _rejection(
                    existing_claim,
                    "duplicate_claim",
                    "같은 stance 안에서 더 강한 중복 claim이 있어 제외합니다.",
                    matched_claim_id=public_claim.get("claim_id"),
                )
            )
            selected[side][existing_index] = public_claim
            seen_by_side[side][key] = (existing_index, public_claim)
        else:
            rejected.append(
                _rejection(
                    claim,
                    "duplicate_claim",
                    "같은 stance 안에서 이미 선택된 중복 claim이 있어 제외합니다.",
                    matched_claim_id=existing_claim.get("claim_id"),
                )
            )

    return {
        "selected": selected,
        "rejected": rejected,
        "summary": {
            "strength_count": len(selected["strengths"]),
            "risk_count": len(selected["risks"]),
            "rejected_count": len(rejected),
        },
    }


def _basic_reject_reason(claim: dict[str, Any], *, min_support_score: float) -> tuple[str, str] | None:
    snippet_count = int(claim.get("snippet_count", 0) or 0)
    if snippet_count < 1:
        return ("missing_snippet", "실제 evidence snippet이 없습니다.")

    claim_families = set(claim.get("claim_families", set()) or set())
    snippet_families = set(claim.get("snippet_families", set()) or set())
    if claim_families and snippet_families and not (claim_families & snippet_families):
        return ("evidence_mismatch", "claim 제목/설명과 실제 스니펫의 주제가 맞지 않습니다.")

    support_score = float(claim.get("support_score", 0.0) or 0.0)
    if support_score < min_support_score:
        return ("weak_support", "근거 강도가 낮아 display 재료로 쓰기 어렵습니다.")

    return None


def _duplicate_key(claim: dict[str, Any]) -> str:
    title = str(claim.get("title", "") or "").strip()
    for suffix in ("이 있다", "가 있다", "있다는 반응", "이라는 반응", "다는 반응", "반응이다", "반응"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
            break
    return normalize_text(title)


def _public_claim(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": claim.get("claim_id"),
        "section": claim.get("section"),
        "stance": claim.get("stance"),
        "title": claim.get("title"),
        "theme": claim.get("theme"),
        "why_it_matters": claim.get("why_it_matters"),
        "aspect_keys": list(claim.get("aspect_keys", []) or []),
        "claim_families": sorted(set(claim.get("claim_families", set()) or set())),
        "snippet_families": sorted(set(claim.get("snippet_families", set()) or set())),
        "support_families": sorted(set(claim.get("support_families", set()) or set())),
        "snippet_count": int(claim.get("snippet_count", 0) or 0),
        "support_score": float(claim.get("support_score", 0.0) or 0.0),
        "evidence_snippets": list(claim.get("evidence_snippets", []) or []),
    }


def _rejection(
    claim: dict[str, Any],
    reason: str,
    message: str,
    *,
    matched_claim_id: Any | None = None,
) -> dict[str, Any]:
    result = {
        "claim_id": claim.get("claim_id"),
        "section": claim.get("section"),
        "stance": claim.get("stance"),
        "title": claim.get("title"),
        "reason": reason,
        "message": message,
        "support_score": float(claim.get("support_score", 0.0) or 0.0),
        "claim_families": sorted(set(claim.get("claim_families", set()) or set())),
        "snippet_families": sorted(set(claim.get("snippet_families", set()) or set())),
    }
    if matched_claim_id:
        result["matched_claim_id"] = matched_claim_id
    return result

