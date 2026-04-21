"""Theme extraction helpers for categorized Korean Steam reviews."""

from __future__ import annotations

from collections import Counter

from report.models.schemas import ProcessedReview

THEME_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "bugs": {
        "충돌 / 크래시": ("충돌", "크래시", "멈춤"),
        "일반 버그": ("버그", "오류", "에러", "깨짐"),
        "접속 / 진행 불가": ("로그인", "접속불가", "진행불가"),
        "계정 / 제재 이슈": ("계정", "정지", "밴"),
    },
    "performance": {
        "최적화 문제": ("최적화", "최적화문제", "프레임", "프레임드랍", "렉", "버벅"),
        "실행 불가 / 튕김": ("실행안", "안됨", "꺼짐", "튕김"),
        "로딩 / 발열 문제": ("로딩", "발열", "무거움", "그래픽카드"),
    },
    "balance": {
        "밸런스 불만": ("밸런스", "사기", "너프", "버프", "op"),
    },
    "story": {
        "스토리 / 서사 몰입": ("스토리", "서사", "시나리오", "몰입", "여운", "감동"),
        "캐릭터 / 연출 인상": ("캐릭터", "연출"),
    },
    "graphics": {
        "그래픽 / 비주얼 호평": ("그래픽", "비주얼", "아트", "모델링", "분위기"),
    },
    "gameplay": {
        "전투 손맛 / 액션 호평": ("전투", "타격감", "손맛", "액션", "보스전", "보스"),
        "빌드 / 무기 다양성": ("빌드", "무기", "스킬", "세팅"),
        "탐험 / 월드 경험": ("탐험", "오픈월드", "던전", "필드"),
        "전투 피로 / 반복 전투": ("전투반복", "반복전투", "패턴반복"),
    },
    "monetization": {
        "가격 / 과금 불만": ("과금", "가격", "bm", "패스", "현질"),
        "DLC / 확장팩 언급": ("dlc", "확장팩", "키트"),
    },
    "multiplayer": {
        "매칭 / 서버 문제": ("매칭", "서버", "핑"),
        "멀티플레이 경험": ("멀티", "파티", "협동", "pvp", "pve", "레이드"),
        "모드 / 큐 구성 이슈": ("듀오", "솔로"),
        "부정행위 / 보안 이슈": ("핵", "매크로", "해킹", "mmr", "밴", "약탈", "털려"),
    },
    "localization": {
        "번역 / 현지화 이슈": ("번역", "오역", "현지화", "자막", "한국어"),
    },
    "difficulty": {
        "난이도 / 진입장벽": ("난이도", "불친절", "초반"),
        "튜토리얼 / 온보딩 부족": ("튜토리얼", "온보딩"),
        "조작 / 규칙 학습 난이도": ("어려워", "어렵", "초보", "뉴비", "입문"),
    },
    "controls": {
        "조작감 문제": ("조작", "조작감", "입력", "반응속도"),
        "UI / 입력 불편": ("키맵", "답답", "불편"),
        "시점 / 멀미 이슈": ("멀미",),
    },
    "content_depth": {
        "중독성 / 시간순삭": ("시간순삭", "킬링타임"),
        "콘텐츠 부족": ("콘텐츠", "볼륨", "할게없", "할것도없", "할거없"),
        "반복 / 목적성 부족": ("지루", "심심", "목적성", "유동성", "반복적", "노가다", "파밍", "숙제", "폐지줍기"),
        "상호작용 / 생동감 부족": ("생동감", "인터랙션", "깊이"),
    },
    "building_ux": {
        "건축 조작 불편": ("건축", "건설", "배치", "집짓", "건축모드"),
        "부지 / 구조 제약": ("부지", "데크", "중정", "경사진바닥", "경사바닥", "비스듬"),
    },
    "save_progression": {
        "저장 / 세이브 손실": ("저장", "세이브", "날아감", "날려", "유실", "이어하기"),
    },
    "mod_support": {
        "모드 지원 / 호환 문제": ("모드", "공식지원", "호환", "활성화", "연결", "cc템", "크리에이션클럽"),
    },
    "customization": {
        "커스터마이징 호평": ("커스터마이징", "꾸미기", "외형", "커스텀"),
        "헤어 / 의상 옵션 부족": ("헤어", "의상", "오드아이"),
        "스킨 / 외형 요소": ("스킨",),
    },
}

STOPWORDS = {
    "그리고",
    "하지만",
    "그래도",
    "그냥",
    "너무",
    "진짜",
    "정말",
    "약간",
    "조금",
    "에서",
    "같음",
    "같다",
    "보통",
}


def _match_canonical_theme(category: str, normalized_text: str) -> str | None:
    patterns = THEME_PATTERNS.get(category, {})
    for canonical_theme, aliases in patterns.items():
        if any(alias.replace(" ", "") in normalized_text for alias in aliases):
            return canonical_theme
    return None


def extract_review_themes(processed_review: ProcessedReview) -> dict[str, str]:
    """Return one canonical theme per matched category for a review."""
    normalized = processed_review.normalized_text.lower().replace(" ", "")
    themes: dict[str, str] = {}

    for category in processed_review.category_tags:
        canonical_theme = _match_canonical_theme(category, normalized)
        if canonical_theme is not None:
            themes[category] = canonical_theme

    return themes


def extract_keywords(text: str) -> list[str]:
    """Extract simple keyword candidates from normalized Korean review text."""
    words = [word.strip(".,!?") for word in text.split()]
    keywords: list[str] = []

    for word in words:
        clean = word.lower()
        if len(clean) < 2:
            continue
        if clean in STOPWORDS:
            continue
        keywords.append(clean)

    return keywords


def collect_top_keywords(processed_reviews: list[ProcessedReview], limit: int = 5) -> list[str]:
    """Aggregate the most frequent keyword candidates across reviews."""
    counter: Counter[str] = Counter()

    for review in processed_reviews:
        if not review.included_in_analysis:
            continue
        counter.update(extract_keywords(review.normalized_text))

    return [keyword for keyword, _count in counter.most_common(limit)]


def collect_top_themes(
    processed_reviews: list[ProcessedReview],
    category: str,
    limit: int = 3,
) -> list[str]:
    """Aggregate the most common canonical themes for a given category."""
    counter: Counter[str] = Counter()

    for review in processed_reviews:
        if not review.included_in_analysis or category not in review.category_tags:
            continue

        theme = extract_review_themes(review).get(category)
        if theme is not None:
            counter[theme] += 1

    return [theme for theme, _count in counter.most_common(limit)]

