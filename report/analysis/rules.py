"""Deterministic preprocessing rules for Korean Steam reviews."""

from __future__ import annotations

import html
import re

HANGUL_PATTERN = re.compile(r"[가-힣]")
VISIBLE_CHAR_PATTERN = re.compile(r"[A-Za-z0-9가-힣ㄱ-ㅎㅏ-ㅣ]")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{3,}")
WHITESPACE_PATTERN = re.compile(r"\s+")
HTML_SCRIPT_STYLE_PATTERN = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s+[^<>]*)?>")
BB_CODE_PATTERN = re.compile(r"\[(?:/?[A-Za-z][A-Za-z0-9]*)(?:=[^\]]+)?\]")

LOW_QUALITY_TEXTS = {
    "",
    ".",
    "..",
    "...",
    "ㅋㅋ",
    "ㅋㅋㅋ",
    "ㅋㅋㅋㅋ",
    "ㅎㅎ",
    "ㅎㅎㅎ",
    "ㅜㅜ",
    "ㅠㅠ",
    "굿",
    "good",
    "bad",
    "게임아님",
    "이거게임아님",
    "명불허전",
    "할만해요",
    "이게게임이지",
    "미친게임",
}

PROFANITY_TOKENS = {
    "쓰레기",
    "개쓰레기",
    "병신",
    "좆같다",
    "ㅈ같다",
    "씨발",
    "시발",
    "ㅅㅂ",
    "망겜",
    "개망",
    "노답",
    "쓰레기겜",
    "개쓰레기겜",
}

NOISE_TOKENS = {
    "ㅋㅋ",
    "ㅋㅋㅋ",
    "ㅎㅎ",
    "ㅎㅎㅎ",
    "ㅠㅠ",
    "ㅜㅜ",
    "진짜",
    "너무",
    "그냥",
    "완전",
}

GENERIC_SENTIMENT_TOKENS = {
    "재밌다",
    "재밌음",
    "재밌어요",
    "재밌습니다",
    "재미있다",
    "재미있음",
    "재미있어요",
    "재미없다",
    "재미없음",
    "갓겜",
    "꿀잼",
    "노잼",
    "최고",
    "최고의",
    "최고임",
    "추천",
    "추천함",
    "비추천",
    "하지마세요",
    "하지마셈",
    "인생게임",
    "인생겜",
    "명작",
    "goat",
    "국밥",
}

GENERIC_SENTIMENT_PREFIXES = (
    "재밌",
    "재미있",
    "재미",
    "재미없",
    "갓겜",
    "꿀잼",
    "노잼",
    "최고",
    "추천",
    "비추천",
    "인생겜",
    "인생게임",
    "명작",
    "국밥",
)

TOPIC_HINT_TOKENS = {
    "버그",
    "튕김",
    "충돌",
    "에러",
    "프레임",
    "렉",
    "최적화",
    "매칭",
    "서버",
    "과금",
    "조작",
    "번역",
    "스토리",
    "밸런스",
    "난이도",
    "그래픽",
    "아트",
    "듀오",
    "솔로",
    "스킨",
    "로그인",
    "접속불가",
    "진행불가",
    "어려워",
    "매크로",
    "mmr",
    "노가다",
    "파밍",
    "숙제",
    "폐지줍기",
    "cc템",
    "크리에이션클럽",
    "몰입",
    "여운",
    "감동",
    "멀미",
    "약탈",
    "털려",
    "해킹",
    "밴",
    "킬링타임",
    "시간순삭",
    "고인물",
    "다인큐",
    "살인마",
    "생존자",
    "판자",
    "발전기",
    "검사중",
}

TOPIC_HINT_TOKENS |= {
    "콘텐츠",
    "볼륨",
    "건축",
    "부지",
    "데크",
    "저장",
    "세이브",
    "모드",
    "커스터마이징",
    "헤어",
    "의상",
    "얼리액세스",
    "전투",
    "타격감",
    "손맛",
    "보스전",
    "보스",
    "빌드",
    "무기",
    "스킬",
    "패링",
    "회피",
    "탐험",
    "오픈월드",
    "던전",
}


POSITIVE_HINT_TOKENS = {
    "재밌",
    "좋",
    "훌륭",
    "추천",
    "만족",
    "깔끔",
}

NEGATIVE_HINT_TOKENS = {
    "별로",
    "나쁘",
    "불편",
    "아쉽",
    "문제",
    "심함",
    "답답",
    "느림",
    "떨어짐",
}

FIGURATIVE_HINT_TOKENS = {
    "천국",
    "지옥",
    "미쳤",
    "살인적",
}


NORMALIZATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("앞서 해보기", "얼리액세스"),
    ("앞서해보기", "얼리액세스"),
    ("얼엑", "얼리액세스"),
    ("컨텐츠", "콘텐츠"),
    ("업뎃", "업데이트"),
    ("커스타마이징", "커스터마이징"),
    ("커마", "커스터마이징"),
    ("발적화", "최적화문제"),
    ("프레임 드랍", "프레임드랍"),
    ("프레임 저하", "프레임드랍"),
    ("게속", "계속"),
    ("안됌", "안됨"),
    ("않됨", "안됨"),
    ("재밋", "재밌"),
    ("디엘씨", "dlc"),
    ("크리에이션 클럽", "크리에이션클럽"),
    ("메크로", "매크로"),
    ("컨텐츤데", "콘텐츠인데"),
    ("시간순삭게임", "시간순삭"),
    ("시간 순삭", "시간순삭"),
    ("쏘쏘", "보통"),
    ("슴슴", "심심"),
    ("노잼", "재미없음"),
    ("포텐셜", "잠재력"),
    ("포텐", "잠재력"),
    ("찍먹", "가볍게플레이"),
    ("그리픽카드", "그래픽카드"),
    ("밸패", "밸런스"),
    ("할게업성", "할게없음"),
    ("개재밌음", "재밌음"),
    ("개재밌다", "재밌다"),
    ("개재밌네", "재밌네"),
    ("개재밌노", "재밌음"),
    ("존나재밌음", "재밌음"),
    ("시간가는줄모름", "시간순삭"),
    ("시간 가는 줄 모름", "시간순삭"),
)


def normalize_text(text: str) -> str:
    """Normalize whitespace and repeated punctuation without rewriting the review."""
    normalized = WHITESPACE_PATTERN.sub(" ", text or "").strip()
    for source, target in NORMALIZATION_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    normalized = REPEATED_CHAR_PATTERN.sub(r"\1\1", normalized)
    return normalized


def clean_markup_text(text: str) -> str:
    """Remove HTML/BBCode noise from analysis text while keeping plain text intact."""
    decoded = html.unescape(text or "")
    no_script = HTML_SCRIPT_STYLE_PATTERN.sub(" ", decoded)
    no_html = HTML_TAG_PATTERN.sub(" ", no_script)
    no_bbcode = BB_CODE_PATTERN.sub(" ", no_html)
    return WHITESPACE_PATTERN.sub(" ", no_bbcode).strip()


def _visible_chars(text: str) -> list[str]:
    return VISIBLE_CHAR_PATTERN.findall(text)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def calculate_hangul_ratio(text: str) -> float:
    """Return the ratio of Hangul characters among visible characters."""
    visible_chars = _visible_chars(text)
    if not visible_chars:
        return 0.0

    hangul_count = len(HANGUL_PATTERN.findall("".join(visible_chars)))
    return hangul_count / len(visible_chars)


def is_low_quality_review(text: str) -> bool:
    """Conservatively exclude reviews that contain almost no meaningful information."""
    normalized = normalize_text(text).lower()
    condensed = normalized.replace(" ", "")

    if condensed in LOW_QUALITY_TEXTS:
        return True

    if len(_visible_chars(normalized)) <= 3:
        return True

    if len(set(condensed)) == 1 and len(condensed) >= 3:
        return True

    tokens = tokenize(normalized)
    if not tokens:
        return True

    meaningful_tokens = [
        token
        for token in tokens
        if token not in NOISE_TOKENS and len(token) >= 2
    ]
    has_topic_hint = any(token in TOPIC_HINT_TOKENS for token in meaningful_tokens)

    if meaningful_tokens and len(meaningful_tokens) <= 3:
        if not has_topic_hint:
            generic_only = all(
                token in GENERIC_SENTIMENT_TOKENS
                or any(token.startswith(prefix) for prefix in GENERIC_SENTIMENT_PREFIXES)
                for token in meaningful_tokens
            )
            if generic_only:
                return True

    if meaningful_tokens and not has_topic_hint:
        # 짧은 감상형 리뷰(주제 힌트 없음)는 분석 효용이 낮아 MVP에서 제외
        if len(meaningful_tokens) <= 4 and len(_visible_chars(normalized)) <= 18:
            generic_or_short = all(
                token in GENERIC_SENTIMENT_TOKENS
                or any(token.startswith(prefix) for prefix in GENERIC_SENTIMENT_PREFIXES)
                or len(token) <= 3
                for token in meaningful_tokens
            )
            if generic_or_short:
                return True

    return len(meaningful_tokens) == 0


def is_profanity_only_review(text: str) -> bool:
    """Return True only when profanity exists without meaningful topic feedback."""
    tokens = tokenize(normalize_text(text))
    if not tokens:
        return False

    contains_profanity = any(token in PROFANITY_TOKENS for token in tokens)
    if not contains_profanity:
        return False

    remaining_tokens = [
        token
        for token in tokens
        if token not in PROFANITY_TOKENS and token not in NOISE_TOKENS
    ]
    if not remaining_tokens:
        return True

    has_topic_hint = any(
        token in TOPIC_HINT_TOKENS or len(token) >= 3 for token in remaining_tokens
    )
    return not has_topic_hint


def detect_ambiguity_flags(
    text: str,
    hangul_ratio: float,
    is_low_quality: bool,
    is_profanity_only: bool,
) -> list[str]:
    """Flag reviews that may need a later LLM fallback decision."""
    normalized = normalize_text(text)
    tokens = tokenize(normalized)
    flags: list[str] = []

    if 0.20 <= hangul_ratio < 0.50:
        flags.append("ambiguous_language")

    has_profanity = any(token in PROFANITY_TOKENS for token in tokens)
    if has_profanity and not is_profanity_only:
        flags.append("ambiguous_profanity")

    has_positive = any(any(hint in token for hint in POSITIVE_HINT_TOKENS) for token in tokens)
    has_negative = any(any(hint in token for hint in NEGATIVE_HINT_TOKENS) for token in tokens)
    if has_positive and has_negative:
        flags.append("ambiguous_sentiment")

    if any(any(hint in token for hint in FIGURATIVE_HINT_TOKENS) for token in tokens):
        flags.append("figurative_expression_detected")

    topic_hits = sum(1 for token in tokens if token in TOPIC_HINT_TOKENS)
    if topic_hits >= 3:
        flags.append("ambiguous_category")

    if is_low_quality and len(tokens) >= 3:
        flags.append("ambiguous_quality")

    return flags


def calculate_rule_confidence(
    *,
    text: str,
    hangul_ratio: float,
    is_low_quality: bool,
    is_profanity_only: bool,
    category_tags: list[str],
    ambiguity_flags: list[str],
) -> float:
    """Return a simple deterministic confidence score in [0.0, 1.0]."""
    if is_low_quality or is_profanity_only or hangul_ratio < 0.20:
        return 0.98

    visible_length = len(_visible_chars(text))
    score = 0.45
    score += min(hangul_ratio, 0.90) * 0.25
    score += min(visible_length / 120.0, 1.0) * 0.20
    score += 0.10 if category_tags else -0.05

    if ambiguity_flags:
        score -= min(0.05 * len(ambiguity_flags), 0.25)

    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return round(score, 4)
