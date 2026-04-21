"""Rule-based multi-label categorization for Korean Steam reviews."""

from __future__ import annotations

from report.analysis.rules import normalize_text

# NOTE:
# - Keep this dictionary deterministic and easy to maintain.
# - Added a focused fallback token set for high unclassified games in cohort_v1
#   (Stardew / Civ6 / HELLDIVERS 2 / PUBG / RimWorld).
CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "bugs": (
        "버그",
        "오류",
        "에러",
        "충돌",
        "크래시",
        "멈춤",
        "멈췄",
        "튕김",
        "깨짐",
        "접속불가",
        "진행불가",
        "계정",
        "제재",
        "정지",
    ),
    "performance": (
        "최적화",
        "프레임",
        "프레임드랍",
        "렉",
        "버벅",
        "로딩",
        "발열",
        "끊김",
        "튕김",
        "튕기",
        "꺼짐",
        "꺼지",
        "안켜짐",
        "싱글코어",
        "stutter",
        "fps",
        "drop",
    ),
    "balance": (
        "밸런스",
        "메타",
        "너프",
        "버프",
        "op",
        "사기",
    ),
    "story": (
        "스토리",
        "서사",
        "시나리오",
        "연출",
        "캐릭터",
        "몰입",
        "감동",
        "세계관",
    ),
    "graphics": (
        "그래픽",
        "비주얼",
        "아트",
        "풍경",
        "모델링",
        "분위기",
    ),
    "gameplay": (
        "전투",
        "타격감",
        "손맛",
        "액션",
        "빌드",
        "무기",
        "탐험",
        "월드",
        "던전",
        "보스전",
        # cohort_v1 high-unclassified reinforcement
        "턴제",
        "농사",
        "농장",
        "문명",
        "사녹",
        "치킨",
        "민주주의",
        "강하",
        "식민지",
        "정착민",
        "림월드",
        "스타듀",
        "배그",
        "배틀그라운드",
        "헬다이버",
        "헬다이버즈",
        "패링",
        "구르기",
        "자유도",
        "보스잡",
        "공룡",
        "오토체스",
    ),
    "monetization": (
        "과금",
        "가격",
        "bm",
        "dlc",
        "확장팩",
        "패스",
        "상점",
        "유료",
        "결제",
        "환불",
        "정가",
        "할인",
        "무료로",
        "무료다",
    ),
    "multiplayer": (
        "매칭",
        "서버",
        "멀티",
        "파티",
        "듀오",
        "스쿼드",
        "솔로",
        "친구랑",
        "친구들이랑",
        "팀원",
        "협동",
        "경쟁",
        "pvp",
        "pve",
        "연동",
        "psn",
        "크로스플레이",
        "mmr",
        "핵",
        "치트",
        "팀킬",
        "친구",
    ),
    "localization": (
        "번역",
        "현지화",
        "자막",
        "오역",
        "맞춤법",
        "한국어",
        "더빙",
    ),
    "difficulty": (
        "난이도",
        "초반",
        "초보",
        "입문",
        "어려움",
        "튜토리얼",
        "온보딩",
    ),
    "controls": (
        "조작",
        "조작감",
        "ui",
        "인터페이스",
        "입력",
        "키마",
        "패드",
        "반응속도",
        "카메라",
        "시점",
        "멀미",
    ),
    "content_depth": (
        "콘텐츠",
        "볼륨",
        "중독성",
        "시간순삭",
        "타임머신",
        "시간가는줄",
        "다음턴",
        "반복",
        "목적성",
        "후반",
        "파밍",
        "지루",
        "업데이트",
    ),
    "building_ux": (
        "건축",
        "건설",
        "배치",
        "부지",
        "구조",
        "경사",
        "타일",
    ),
    "save_progression": (
        "저장",
        "세이브",
        "백업",
        "로드",
        "롤백",
        "이어하기",
        "날아",
        "손실",
    ),
    "mod_support": (
        "모드",
        "워크샵",
        "창작마당",
        "호환",
        "플러그인",
    ),
    "customization": (
        "커스터마이징",
        "커마",
        "헤어",
        "의상",
        "스킨",
        "외형",
        "코디",
    ),
}

GAMEPLAY_STRONG_TOKENS: tuple[str, ...] = (
    "전투",
    "타격감",
    "손맛",
    "액션",
    "빌드",
    "무기",
    "탐험",
    "월드",
    "던전",
    "턴제",
    "농사",
    "농장",
    "문명",
    "사녹",
    "치킨",
    "민주주의",
    "강하",
    "식민지",
    "정착민",
    "배그",
    "배틀그라운드",
    "헬다이버",
    "헬다이버즈",
)

SAVE_PROGRESSION_HINTS: tuple[str, ...] = (
    "저장",
    "세이브",
    "백업",
    "로드",
    "롤백",
    "이어하기",
    "날아",
    "손실",
)

PERFORMANCE_STRONG_TOKENS: tuple[str, ...] = (
    "최적화",
    "프레임",
    "렉",
    "버벅",
    "로딩",
    "발열",
    "stutter",
    "fps",
    "drop",
)


def normalize_for_category_match(text: str) -> str:
    """Normalize review text for simple substring matching."""
    return normalize_text(text).lower().replace(" ", "")


def extract_category_tags(text: str) -> list[str]:
    """Return every matched category tag for a review."""
    normalized = normalize_for_category_match(text)
    tags: list[str] = []

    for category, patterns in CATEGORY_PATTERNS.items():
        if any(pattern.lower().replace(" ", "") in normalized for pattern in patterns):
            tags.append(category)

    # Suppress incidental gameplay matches (ex: "보스전에서 튕김/세이브 손실")
    # when the primary user intent is stability/progression failure.
    if "gameplay" in tags and {"performance", "bugs", "save_progression"} & set(tags):
        has_strong_gameplay_signal = any(
            token.lower().replace(" ", "") in normalized for token in GAMEPLAY_STRONG_TOKENS
        )
        has_save_progression_signal = any(
            token.lower().replace(" ", "") in normalized for token in SAVE_PROGRESSION_HINTS
        )
        if (not has_strong_gameplay_signal) or has_save_progression_signal:
            tags = [tag for tag in tags if tag != "gameplay"]

    # Save/progression complaints often include "꺼짐/튕김" text.
    # Keep performance only when there is an explicit performance signal.
    if "save_progression" in tags and "performance" in tags:
        has_strong_performance_signal = any(
            token.lower().replace(" ", "") in normalized for token in PERFORMANCE_STRONG_TOKENS
        )
        if not has_strong_performance_signal:
            tags = [tag for tag in tags if tag != "performance"]

    return tags

