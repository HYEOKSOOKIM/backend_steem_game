"""Shared text feature helpers for report quality checks."""

from __future__ import annotations

import re
from typing import Any


CONCEPT_FAMILIES: dict[str, tuple[str, ...]] = {
    "story": (
        "스토리",
        "서사",
        "사건",
        "인물",
        "캐릭터",
        "여운",
        "감정선",
        "챕터",
        "엔딩",
        "아서",
    ),
    "world_exploration": (
        "오픈월드",
        "월드",
        "탐험",
        "발견",
        "세계",
        "세계관",
        "자유도",
        "필드",
        "사냥",
        "생활",
        "상호작용",
        "npc",
    ),
    "visual_audio": (
        "그래픽",
        "비주얼",
        "자연",
        "환경",
        "아트",
        "연출",
        "음악",
        "ost",
        "사운드",
        "분위기",
    ),
    "combat": (
        "전투",
        "보스",
        "패턴",
        "손맛",
        "타격감",
        "액션",
        "교전",
        "사격",
        "총질",
        "근접",
    ),
    "loot_progression": (
        "장비",
        "파밍",
        "빌드",
        "성장",
        "세팅",
        "무기",
        "스킬",
        "수집",
        "반복 임무",
    ),
    "multiplayer_online": (
        "협동",
        "분대",
        "팀",
        "팀플레이",
        "임무",
        "멀티",
        "온라인",
        "매칭",
        "서버",
        "레이드",
        "세션",
    ),
    "cheating_security": (
        "핵",
        "핵쟁이",
        "해킹",
        "치트",
        "밴",
        "정지",
        "제재",
        "안티치트",
        "보안",
    ),
    "stability": (
        "버그",
        "오류",
        "에러",
        "크래시",
        "충돌",
        "튕김",
        "팅김",
        "끊김",
        "렉",
        "프레임",
        "최적화",
        "로딩",
        "기술",
        "불안정",
    ),
    "controls_ux": (
        "조작",
        "조작감",
        "입력",
        "반응",
        "ui",
        "시점",
        "멀미",
        "답답",
        "불편",
    ),
    "pacing_repetition": (
        "느림",
        "느리",
        "지루",
        "반복",
        "템포",
        "이동",
        "긴 호흡",
        "피로",
        "노가다",
        "숙제",
    ),
    "price_monetization": (
        "가격",
        "비용",
        "정가",
        "할인",
        "구매",
        "과금",
        "dlc",
        "가성비",
        "볼륨",
    ),
    "strategy_management": (
        "전략",
        "전술",
        "턴",
        "관리",
        "운영",
        "도시",
        "문명",
        "로스터",
        "시뮬레이션",
    ),
}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_text(text: str) -> str:
    return str(text or "").lower().replace(" ", "")


def tokens(text: str) -> set[str]:
    normalized = normalize_text(text)
    raw_tokens = re.findall(r"[0-9a-zA-Z가-힣]{2,}", normalized)
    return {token for token in raw_tokens if len(token) >= 2}


def families(text: str) -> set[str]:
    normalized = normalize_text(text)
    result: set[str] = set()
    for family, family_tokens in CONCEPT_FAMILIES.items():
        for token in family_tokens:
            if normalize_text(token) in normalized:
                result.add(family)
                break
    return result


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
