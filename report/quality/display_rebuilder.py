"""Build dry-run report_display candidates from selected good claims."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .good_claim_selector import select_good_claims

DEFAULT_MAX_CLAIMS_PER_SIDE = 2


def build_display_from_good_claims(
    report_payload: dict[str, Any],
    *,
    max_claims_per_side: int = DEFAULT_MAX_CLAIMS_PER_SIDE,
) -> dict[str, Any]:
    """Return a rebuilt display candidate without mutating the report payload."""
    selection = select_good_claims(report_payload)
    strengths = list(selection.get("selected", {}).get("strengths", []) or [])[:max_claims_per_side]
    risks = list(selection.get("selected", {}).get("risks", []) or [])[:max_claims_per_side]

    original_display = deepcopy(dict(report_payload.get("report_display", {}) or {}))
    rebuilt_display = deepcopy(original_display)
    rebuilt_display["good_for"] = [_fit_sentence(_fit_anchor(claim), positive=True) for claim in strengths]
    rebuilt_display["not_good_for"] = [_fit_sentence(_fit_anchor(claim), positive=False) for claim in risks]
    rebuilt_display["top_strengths"] = [_display_card(claim, positive=True) for claim in strengths]
    rebuilt_display["top_risks"] = [_display_card(claim, positive=False) for claim in risks]

    return {
        "rebuilt_display": rebuilt_display,
        "used_claim_ids": {
            "strengths": [claim.get("claim_id") for claim in strengths],
            "risks": [claim.get("claim_id") for claim in risks],
        },
        "dropped_existing_items": _dropped_existing_items(original_display, rebuilt_display),
        "selection": selection,
    }


def _display_card(claim: dict[str, Any], *, positive: bool) -> dict[str, str]:
    title = _compact_title(str(claim.get("title", "") or ""), positive=positive)
    summary = str(claim.get("why_it_matters", "") or "").strip()
    if not summary:
        summary = "근거 리뷰와 연결된 항목입니다."
    return {
        "title": title,
        "summary": summary,
    }


def _fit_anchor(claim: dict[str, Any]) -> str:
    theme = str(claim.get("theme", "") or "").strip()
    title = _compact_title(
        str(claim.get("title", "") or "").strip(),
        positive=str(claim.get("stance", "")) == "positive",
    )
    if theme and "/" not in theme:
        return theme
    return title or theme


def _compact_title(text: str, *, positive: bool) -> str:
    value = " ".join(str(text or "").split()).strip()
    replacements = (
        ("이 크다는 반응", "이 큰 점"),
        ("가 크다는 반응", "가 큰 점"),
        ("을 끊는다는 반응", "을 끊는 문제"),
        ("를 끊는다는 반응", "를 끊는 문제"),
        ("이 갈린다는 반응", "이 갈리는 지점"),
        ("가 갈린다는 반응", "가 갈리는 지점"),
        ("다는 반응", "다는 점"),
    )
    for source, target in replacements:
        if value.endswith(source):
            return value[: -len(source)].strip() + target
    for suffix in ("이 있다.", "가 있다.", "있다는 반응이 있다.", "있다는 반응", "이라는 반응", "다는 반응", "반응이다", "반응"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break
    if not value:
        return "근거가 뚜렷한 강점" if positive else "주의가 필요한 리스크"
    return value


def _fit_sentence(anchor: str, *, positive: bool) -> str:
    value = " ".join(str(anchor or "").split()).strip()
    if not value:
        value = "근거가 확인된 항목"
    suffix_like = ("점", "지점", "포인트", "리스크", "문제", "이슈", "부담", "불편")
    if positive:
        if value.endswith(suffix_like):
            return f"{value}{_object_particle(value)} 중요하게 보는 플레이어"
        return f"{value} 지점을 중요하게 보는 플레이어"
    if value.endswith(suffix_like):
        return f"{value}에 민감한 플레이어"
    return f"{value} 지점에 민감한 플레이어"


def _object_particle(value: str) -> str:
    if not value:
        return "을"
    last = value[-1]
    code = ord(last)
    if not (0xAC00 <= code <= 0xD7A3):
        return "을"
    return "을" if (code - 0xAC00) % 28 else "를"


def _dropped_existing_items(original_display: dict[str, Any], rebuilt_display: dict[str, Any]) -> dict[str, int]:
    fields = ("good_for", "not_good_for", "top_strengths", "top_risks")
    dropped: dict[str, int] = {}
    for field in fields:
        original_count = len(list(original_display.get(field, []) or []))
        rebuilt_count = len(list(rebuilt_display.get(field, []) or []))
        dropped[field] = max(original_count - rebuilt_count, 0)
    return dropped
