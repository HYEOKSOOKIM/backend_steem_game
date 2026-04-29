"""Extract reusable review-language phrases per evidence claim."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .text_features import clean_text, families


STOP_PHRASES = {
    "게임",
    "진짜",
    "너무",
    "그냥",
    "정말",
    "하지만",
    "그리고",
    "그래도",
    "있습니다",
    "합니다",
    "같습니다",
    "플레이",
    "아니다",
    "게임을",
}

BLOCKED_FRAGMENTS = {
    "씨발",
    "시발",
    "ㅅㅂ",
    "병신",
    "짱개",
    "못함",
    "안함",
    "안하다가",
    "갓겜",
    "사놓고",
    "땡겨",
    "안땡겨",
    "하트",
    "1만번",
    "화가나",
    "관리안함",
    "선택했는데",
    "쳐다보고",
    "멀뚱멀뚱",
    "부정적인게",
    "볼맛남",
    "대학가겠",
    "이상한ui",
}


def build_phrase_bank(claims: list[dict[str, Any]], *, limit_per_claim: int = 12) -> dict[str, list[str]]:
    """Return high-signal phrase candidates keyed by claim_id."""
    bank: dict[str, list[str]] = {}
    for claim in claims:
        claim_id = str(claim.get("claim_id", "")).strip()
        snippets = [str(item) for item in list(claim.get("evidence_snippets", []) or [])]
        phrases = _extract_phrases(
            " ".join(snippets),
            limit=limit_per_claim,
            support_families=set(claim.get("support_families", set()) or set()),
        )
        if claim_id:
            bank[claim_id] = phrases
    return bank


def _extract_phrases(text: str, *, limit: int, support_families: set[str] | None = None) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    units = re.findall(r"[0-9A-Za-z가-힣]{2,}", cleaned)
    counter: Counter[str] = Counter()
    for size in (2, 3, 4):
        for index in range(0, max(len(units) - size + 1, 0)):
            phrase = " ".join(units[index : index + size]).strip()
            if not _is_useful_phrase(phrase, support_families=support_families):
                continue
            counter[phrase] += 1
    singles = [
        unit
        for unit in units
        if _is_useful_single(unit, support_families=support_families)
    ]
    counter.update(singles)
    ranked = sorted(counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [phrase for phrase, _count in ranked[:limit]]


def _is_useful_phrase(phrase: str, *, support_families: set[str] | None = None) -> bool:
    lowered = phrase.lower().strip()
    if not lowered:
        return False
    if len(phrase) > 24:
        return False
    if any(fragment in lowered for fragment in BLOCKED_FRAGMENTS):
        return False
    if any(stop == lowered for stop in STOP_PHRASES):
        return False
    parts = lowered.split()
    if len(parts) < 2:
        return False
    if all(part in STOP_PHRASES for part in parts):
        return False
    phrase_families = families(phrase)
    if support_families:
        if not phrase_families:
            return False
        if not (phrase_families & support_families):
            return False
    return True


def _is_useful_single(value: str, *, support_families: set[str] | None = None) -> bool:
    lowered = value.lower().strip()
    if len(value) < 3 or len(value) > 10:
        return False
    if lowered in STOP_PHRASES or lowered.isdigit():
        return False
    if any(fragment in lowered for fragment in BLOCKED_FRAGMENTS):
        return False
    value_families = families(value)
    if support_families:
        if not value_families:
            return False
        if not (value_families & support_families):
            return False
    if not value_families and len(value) <= 3:
        return False
    return True
