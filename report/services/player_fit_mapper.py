"""Genre-aware player-fit and experience copy helpers.

This module exists to avoid mapping broad analysis aspects such as
``gameplay`` directly to buyer-facing phrases. The old pipeline used a
single aspect-level phrase table, which produced genre-incompatible copy
such as boss-fight language for battle royale shooters.
"""

from __future__ import annotations

import re
from typing import Any


GENRE_HINTS: dict[str, tuple[str, ...]] = {
    "shooter": ("shooter", "fps", "tps", "슈팅", "사격", "총", "gun"),
    "battle_royale": ("battle royale", "배틀로얄", "battlegrounds"),
    "soulslike": ("soulslike", "소울", "액션 rpg", "action rpg", "rpg"),
    "openworld": ("open world", "오픈월드", "어드벤처", "adventure", "sandbox"),
    "management": ("management", "simulation", "sim", "시뮬레이션", "운영", "경영"),
    "sports": ("sports", "sport", "스포츠", "football", "soccer"),
    "strategy": ("strategy", "전략", "tactics", "tactical"),
    "cozy": ("farming", "life sim", "농장", "힐링", "cozy"),
}

THEME_HINTS: dict[str, tuple[str, ...]] = {
    "boss_pattern_mastery": ("보스", "패턴", "회피", "트라이", "도전", "소울", "죽고"),
    "shooter_gunplay": ("총", "총기", "사격", "에임", "반동", "교전", "손맛", "타격감"),
    "survival_loot_loop": ("생존", "파밍", "루트", "루팅", "자기장", "파밍", "서바이벌"),
    "openworld_exploration": ("탐험", "월드", "오픈 월드", "자유도", "발견", "맵"),
    "sandbox_freedom": ("자유도", "마음대로", "자유", "샌드박스", "놀이"),
    "narrative_immersion": ("스토리", "서사", "캐릭터", "연출", "세계관", "몰입"),
    "build_customization": ("빌드", "세팅", "커스터마이징", "외형", "의상", "조합"),
    "long_term_growth": ("성장", "볼륨", "콘텐츠", "엔드게임", "장기", "오래"),
    "tactical_management": ("전술", "운영", "로스터", "전략", "감독", "전개"),
    "teamplay_synergy": ("팀플", "파티", "협동", "호흡", "합", "스쿼드"),
    "matchmaking_variance": ("매칭", "서버", "핑", "대기", "큐"),
    "stability_interruptions": ("버그", "오류", "에러", "충돌", "튕김", "멈춤"),
    "performance_instability": ("프레임", "렉", "끊김", "최적화", "버벅", "발열"),
    "onboarding_friction": ("튜토리얼", "가이드", "입문", "초반", "적응", "조작감"),
    "repetition_fatigue": ("반복", "지루", "노가다", "루틴", "늘어짐"),
    "price_sensitivity": ("가격", "과금", "현질", "비싸", "가성비", "dlc"),
    "teamplay_stress": ("팀플", "소통", "스트레스", "트롤", "민폐", "정치"),
    "balance_swings": ("밸런스", "메타", "너프", "버프", "불공정"),
    "save_safety": ("세이브", "저장", "롤백", "유실", "손실"),
    "translation_friction": ("번역", "자막", "오역", "텍스트", "로컬"),
    "control_friction": ("조작", "ui", "키설정", "인터페이스", "입력"),
}

POSITIVE_PLAYER_FIT = {
    "boss_pattern_mastery": "반복 도전 속에서 패턴을 익히는 재미를 좋아하는 플레이어",
    "shooter_gunplay": "짧고 강한 교전 템포를 좋아하는 플레이어",
    "survival_loot_loop": "파밍과 생존 판단이 맞물리는 긴장감을 즐기는 플레이어",
    "openworld_exploration": "맵을 돌아다니며 발견하는 재미를 중요하게 보는 플레이어",
    "sandbox_freedom": "정해진 길보다 자유롭게 굴려보는 재미를 선호하는 플레이어",
    "narrative_immersion": "서사와 분위기에 오래 몰입하는 플레이어",
    "build_customization": "세팅과 빌드를 바꿔보며 자기 스타일을 찾는 플레이어",
    "long_term_growth": "한 게임을 오래 붙잡고 성장 흐름을 쌓는 플레이어",
    "tactical_management": "전술과 운영 판단을 오래 다듬는 플레이를 좋아하는 플레이어",
    "teamplay_synergy": "팀원과 합을 맞추며 플레이하는 재미를 좋아하는 플레이어",
    "visual_atmosphere": "풍경과 연출까지 천천히 즐기는 플레이어",
    "core_play_mastery": "핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어",
}

NEGATIVE_PLAYER_FIT = {
    "matchmaking_variance": "매 판 팀원과 서버 상태 편차에 스트레스를 크게 받는 플레이어",
    "stability_interruptions": "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어",
    "performance_instability": "프레임과 반응성이 조금만 흔들려도 예민하게 느끼는 플레이어",
    "onboarding_friction": "초반 적응 구간 없이 바로 편하게 즐기고 싶은 플레이어",
    "repetition_fatigue": "반복 구간이 조금만 보여도 금방 지루해지는 플레이어",
    "price_sensitivity": "가격 대비 만족을 아주 엄격하게 따지는 플레이어",
    "teamplay_stress": "팀플레이 소통 피로를 크게 느끼는 플레이어",
    "balance_swings": "작은 밸런스 변화에도 플레이 감각이 크게 흔들리는 플레이어",
    "save_safety": "진행 데이터 안정성을 가장 먼저 보는 플레이어",
    "translation_friction": "번역과 텍스트 이해가 막히면 바로 몰입이 깨지는 플레이어",
    "control_friction": "조작과 인터페이스 적응에 스트레스를 크게 받는 플레이어",
}

POSITIVE_TITLES = {
    "boss_pattern_mastery": "반복 도전 끝에 손맛이 살아나는 전투",
    "shooter_gunplay": "교전 손맛과 템포가 살아 있는 전투",
    "survival_loot_loop": "파밍과 생존 판단이 긴장감을 만드는 플레이",
    "openworld_exploration": "맵을 돌아다니는 재미가 큰 탐험 경험",
    "sandbox_freedom": "하고 싶은 방식으로 굴릴 수 있는 자유도",
    "narrative_immersion": "세계와 사건에 빨려드는 몰입감",
    "build_customization": "세팅을 바꿔보는 재미가 분명한 성장 구조",
    "long_term_growth": "오래 붙잡게 만드는 성장 루프",
    "tactical_management": "전술과 운영 판단의 깊이가 살아 있는 플레이",
    "teamplay_synergy": "팀원과 호흡이 맞을 때 살아나는 플레이",
    "visual_atmosphere": "분위기를 살리는 연출과 비주얼",
    "core_play_mastery": "핵심 플레이 감각이 꾸준히 살아 있는 경험",
}

NEGATIVE_TITLES = {
    "matchmaking_variance": "매칭과 서버 상태에 따라 판마다 편차가 커요",
    "stability_interruptions": "예상치 못한 오류로 흐름이 끊길 수 있어요",
    "performance_instability": "끊김과 프레임 저하가 거슬릴 수 있어요",
    "onboarding_friction": "처음엔 익숙해지기까지 시간이 필요해요",
    "repetition_fatigue": "익숙해진 뒤엔 반복감이 빨리 올 수 있어요",
    "price_sensitivity": "가격 대비 만족감은 취향을 많이 타요",
    "teamplay_stress": "팀플레이 피로가 생각보다 크게 느껴질 수 있어요",
    "balance_swings": "메타와 밸런스 변화에 민감하게 흔들릴 수 있어요",
    "save_safety": "진행 데이터가 흔들리면 불안이 크게 올라와요",
    "translation_friction": "번역과 텍스트 품질이 몰입을 막을 수 있어요",
    "control_friction": "조작이 손에 익기 전까지 답답할 수 있어요",
}

POSITIVE_SUMMARIES = {
    "boss_pattern_mastery": "실패를 거듭할수록 손에 익는 구조라, 익숙해질수록 재미가 커집니다.",
    "shooter_gunplay": "교전 템포와 손맛이 살아 있어 한 판이 금방 지나가는 편입니다.",
    "survival_loot_loop": "파밍과 생존 판단이 맞물려 매 판 다른 긴장감이 살아납니다.",
    "openworld_exploration": "맵을 돌아다니며 발견하는 재미가 꾸준히 플레이를 끌어갑니다.",
    "sandbox_freedom": "하고 싶은 방식으로 굴릴 수 있어 자기만의 플레이를 만들기 좋습니다.",
    "narrative_immersion": "인물과 사건을 따라가다 보면 다음 장면이 궁금해서 계속 붙잡게 됩니다.",
    "build_customization": "세팅을 바꿔보는 재미가 분명해서 자기 취향에 맞게 오래 만지기 좋습니다.",
    "long_term_growth": "목표를 하나씩 쌓아가는 흐름이 분명해서 긴 호흡으로 즐기기 좋습니다.",
    "tactical_management": "전술과 운영 판단이 쌓일수록 플레이 깊이가 살아납니다.",
    "teamplay_synergy": "팀원과 합이 맞는 순간의 손맛이 분명해서 같이 할수록 재미가 커집니다.",
    "visual_atmosphere": "화면과 연출이 분위기를 잘 살려 가만히 둘러보는 재미도 있는 편입니다.",
    "core_play_mastery": "핵심 플레이가 손에 익을수록 흐름이 좋아져 오래 붙잡기 쉬운 편입니다.",
}

NEGATIVE_SUMMARIES = {
    "matchmaking_variance": "판마다 팀원과 서버 상태 차이가 커서 플레이 품질 편차가 큰 편입니다.",
    "stability_interruptions": "예상치 못한 오류가 끼어들면 흐름이 한 번에 끊길 수 있습니다.",
    "performance_instability": "끊김이나 프레임 저하가 생기면 교전과 이동 감각이 무뎌질 수 있습니다.",
    "onboarding_friction": "처음엔 규칙과 조작에 익숙해지기까지 시간이 꽤 필요한 편입니다.",
    "repetition_fatigue": "익숙해진 뒤에는 새로움보다 반복감이 먼저 느껴질 수 있습니다.",
    "price_sensitivity": "가격 부담이 크면 기대만큼 만족하지 못했다는 반응이 나옵니다.",
    "teamplay_stress": "팀 호흡이 어긋나면 재미보다 피로가 먼저 올라올 수 있습니다.",
    "balance_swings": "메타와 밸런스 변화에 따라 플레이 만족도가 자주 흔들릴 수 있습니다.",
    "save_safety": "진행 데이터가 흔들리면 플레이 자체보다 불안이 더 커질 수 있습니다.",
    "translation_friction": "텍스트 이해가 막히면 몰입과 진입 속도가 함께 떨어질 수 있습니다.",
    "control_friction": "조작과 인터페이스가 손에 익기 전까지 답답하게 느껴질 수 있습니다.",
}

POSITIVE_HEADLINE_THEMES = {
    "boss_pattern_mastery": "반복 도전 끝에 살아나는 전투 손맛",
    "shooter_gunplay": "교전 템포와 손맛",
    "survival_loot_loop": "생존 교전의 긴장감",
    "openworld_exploration": "탐험과 자유도",
    "sandbox_freedom": "자유롭게 굴려보는 재미",
    "narrative_immersion": "세계와 사건에 빨려드는 몰입감",
    "build_customization": "세팅을 바꿔보는 재미",
    "long_term_growth": "오래 붙잡게 만드는 성장 루프",
    "tactical_management": "전술과 운영 판단의 깊이",
    "teamplay_synergy": "팀플레이 합이 맞을 때의 손맛",
    "visual_atmosphere": "분위기를 살리는 연출과 비주얼",
    "core_play_mastery": "핵심 플레이 감각",
}

NEGATIVE_HEADLINE_THEMES = {
    "matchmaking_variance": "매칭과 서버 상태 편차",
    "stability_interruptions": "예상치 못한 오류",
    "performance_instability": "프레임과 끊김 문제",
    "onboarding_friction": "초반 적응 부담",
    "repetition_fatigue": "중후반 반복감",
    "price_sensitivity": "가격 대비 만족 편차",
    "teamplay_stress": "팀플레이 피로",
    "balance_swings": "메타와 밸런스 변화",
    "save_safety": "진행 데이터 불안",
    "translation_friction": "번역과 텍스트 이해 문제",
    "control_friction": "조작 적응 부담",
}

POSITIVE_EVIDENCE_TITLES = {
    "boss_pattern_mastery": "반복 도전이 재미로 바뀐다는 반응",
    "shooter_gunplay": "교전 손맛과 템포가 좋다는 반응",
    "survival_loot_loop": "파밍과 생존 판단이 긴장감을 만든다는 반응",
    "openworld_exploration": "맵을 돌아다니는 재미가 크다는 반응",
    "sandbox_freedom": "자유롭게 굴리는 플레이가 오래 붙잡는다는 반응",
    "narrative_immersion": "세계와 사건 몰입감이 오래 간다는 반응",
    "build_customization": "세팅을 바꾸는 재미가 뚜렷하다는 반응",
    "long_term_growth": "오래 파고들수록 재미가 살아난다는 반응",
    "tactical_management": "운영과 전술 판단의 재미가 크다는 반응",
    "teamplay_synergy": "팀 호흡이 맞을 때 재미가 커진다는 반응",
    "visual_atmosphere": "비주얼과 분위기가 몰입을 살린다는 반응",
    "core_play_mastery": "핵심 플레이 감각이 좋다는 반응",
}

NEGATIVE_EVIDENCE_TITLES = {
    "matchmaking_variance": "매칭과 서버 상태가 판마다 흔들린다는 반응",
    "stability_interruptions": "예상치 못한 오류가 흐름을 끊는다는 반응",
    "performance_instability": "끊김과 프레임 저하가 거슬린다는 반응",
    "onboarding_friction": "초반 적응 장벽이 높다는 반응",
    "repetition_fatigue": "반복감 때문에 중후반 동력이 떨어진다는 반응",
    "price_sensitivity": "가격 대비 만족이 갈린다는 반응",
    "teamplay_stress": "팀플레이 피로가 크다는 반응",
    "balance_swings": "메타와 밸런스 변화에 피로를 느낀다는 반응",
    "save_safety": "진행 데이터 안정성이 불안하다는 반응",
    "translation_friction": "번역과 텍스트 품질이 아쉽다는 반응",
    "control_friction": "조작 적응이 답답하다는 반응",
}

POSITIVE_EVIDENCE_SUMMARIES = {
    "boss_pattern_mastery": "전투를 익혀가는 재미를 좋게 본 리뷰가 많아, 도전형 전투를 좋아한다면 만족도가 높은 편입니다.",
    "shooter_gunplay": "교전 감각이 좋다는 반응이 많아, 손맛과 템포를 중시한다면 만족도가 높을 가능성이 큽니다.",
    "survival_loot_loop": "파밍과 생존 판단의 긴장감을 높게 보는 리뷰가 많아, 한 판의 밀도를 중시하는 쪽과 잘 맞습니다.",
    "openworld_exploration": "맵을 돌아다니는 재미에 대한 호평이 많아, 발견과 이동 자체를 즐기는 플레이와 잘 맞습니다.",
    "sandbox_freedom": "정해진 답보다 자유롭게 굴리는 재미를 높게 보는 리뷰가 많아, 자기 방식으로 즐기고 싶은 쪽과 잘 맞습니다.",
    "narrative_immersion": "세계와 사건에 대한 몰입 이야기가 많아, 분위기와 서사를 중시한다면 만족도가 높은 편입니다.",
    "build_customization": "세팅을 바꾸는 재미를 좋게 보는 리뷰가 많아, 자기 스타일을 만드는 즐거움이 분명한 편입니다.",
    "long_term_growth": "오래 붙잡을수록 재미가 살아난다는 반응이 많아, 긴 호흡으로 즐기는 플레이와 잘 맞습니다.",
    "tactical_management": "운영과 전술 판단의 재미를 높게 보는 리뷰가 많아, 생각하면서 굴리는 플레이를 좋아한다면 잘 맞습니다.",
    "teamplay_synergy": "팀원과 합이 맞을 때 재미가 커진다는 반응이 많아, 같이 호흡 맞추는 플레이를 즐길수록 만족도가 높습니다.",
    "visual_atmosphere": "비주얼과 연출 몰입 이야기가 많아, 화면 분위기까지 중요하게 본다면 만족하기 쉬운 편입니다.",
    "core_play_mastery": "핵심 플레이 감각이 좋다는 반응이 꾸준해, 기본 재미를 중시하는 플레이와 잘 맞는 편입니다.",
}

NEGATIVE_EVIDENCE_SUMMARIES = {
    "matchmaking_variance": "매칭과 서버 상태 문제를 자주 언급해, 판마다 플레이 품질이 흔들릴 수 있습니다.",
    "stability_interruptions": "오류와 끊김 이야기가 반복돼, 흐름이 한 번 끊기면 피로가 크게 올라올 수 있습니다.",
    "performance_instability": "프레임과 끊김 문제를 언급한 리뷰가 꾸준해, 반응성과 몰입을 중시한다면 거슬릴 수 있습니다.",
    "onboarding_friction": "초반 적응이 어렵다는 반응이 있어, 바로 손에 익는 경험을 기대하면 답답할 수 있습니다.",
    "repetition_fatigue": "반복감 이야기가 모여 있어, 새로움이 빠르게 줄어들면 동력이 떨어질 수 있습니다.",
    "price_sensitivity": "가격 대비 만족 편차를 언급한 리뷰가 있어, 비용 대비 만족을 엄격히 보면 아쉬울 수 있습니다.",
    "teamplay_stress": "팀플레이 피로를 말하는 리뷰가 있어, 소통과 팀 분위기에 민감하면 스트레스를 받을 수 있습니다.",
    "balance_swings": "메타와 밸런스 이야기가 반복돼, 플레이 감각이 패치에 따라 흔들릴 수 있습니다.",
    "save_safety": "저장과 진행 안정성을 걱정하는 리뷰가 있어, 기록 보존을 중요하게 보면 불안할 수 있습니다.",
    "translation_friction": "번역과 텍스트 품질에 대한 아쉬움이 있어, 텍스트 이해가 중요하면 몰입이 끊길 수 있습니다.",
    "control_friction": "조작 적응이 답답하다는 반응이 있어, 처음부터 부드러운 손맛을 기대하면 아쉬울 수 있습니다.",
}


def infer_copy_subtype(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    aspect_key = str(aspect or "").strip().lower()
    theme_text = str(theme or "").strip().lower()
    genre_flags = _genre_flags(genres or [])

    if negative:
        if aspect_key == "bugs":
            return "stability_interruptions"
        if aspect_key == "performance":
            return "performance_instability"
        if aspect_key in {"difficulty", "difficulty_onboarding"}:
            return "onboarding_friction"
        if aspect_key == "monetization":
            return "price_sensitivity"
        if aspect_key == "matchmaking":
            return "matchmaking_variance"
        if aspect_key == "multiplayer":
            if genre_flags["shooter"] or genre_flags["battle_royale"]:
                return "matchmaking_variance"
            return "teamplay_stress"
        if aspect_key == "balance":
            return "balance_swings"
        if aspect_key == "save_progression":
            return "save_safety"
        if aspect_key == "localization":
            return "translation_friction"
        if aspect_key == "controls":
            return "control_friction"
        if aspect_key == "content_depth":
            return "repetition_fatigue"
        if aspect_key == "gameplay":
            if _matches_any(theme_text, THEME_HINTS["matchmaking_variance"]):
                return "matchmaking_variance"
            if _matches_any(theme_text, THEME_HINTS["repetition_fatigue"]):
                return "repetition_fatigue"
            if _matches_any(theme_text, THEME_HINTS["control_friction"]):
                return "control_friction"
            if genre_flags["shooter"] or genre_flags["battle_royale"]:
                return "teamplay_stress"
            return "repetition_fatigue"
        return "stability_interruptions"

    if aspect_key == "story":
        return "narrative_immersion"
    if aspect_key == "graphics" or aspect_key == "sound":
        return "visual_atmosphere"
    if aspect_key == "customization":
        return "build_customization"
    if aspect_key == "content_depth":
        if genre_flags["management"] or genre_flags["sports"] or genre_flags["strategy"]:
            return "tactical_management"
        return "long_term_growth"
    if aspect_key == "multiplayer":
        return "teamplay_synergy"
    if aspect_key == "gameplay":
        if genre_flags["management"] or genre_flags["sports"] or genre_flags["strategy"]:
            return "tactical_management"
        if genre_flags["battle_royale"] or _matches_any(theme_text, THEME_HINTS["survival_loot_loop"]):
            return "survival_loot_loop"
        if genre_flags["shooter"] or _matches_any(theme_text, THEME_HINTS["shooter_gunplay"]):
            return "shooter_gunplay"
        if genre_flags["soulslike"] or _matches_any(theme_text, THEME_HINTS["boss_pattern_mastery"]):
            return "boss_pattern_mastery"
        if genre_flags["openworld"] or _matches_any(theme_text, THEME_HINTS["openworld_exploration"]):
            return "openworld_exploration"
        if _matches_any(theme_text, THEME_HINTS["sandbox_freedom"]):
            return "sandbox_freedom"
        return "core_play_mastery"
    return "core_play_mastery"


def build_player_fit_phrase(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_PLAYER_FIT if negative else POSITIVE_PLAYER_FIT
    if subtype in mapping:
        return mapping[subtype]
    return (
        "완성도와 기술 안정성이 조금만 흔들려도 스트레스를 크게 받는 플레이어"
        if negative
        else "핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어"
    )


def build_display_theme(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    cleaned = str(theme or "").strip()
    subtype = infer_copy_subtype(aspect=aspect, theme=cleaned, genres=genres, negative=negative)
    if cleaned and not _looks_like_internal_theme(cleaned):
        return cleaned
    mapping = NEGATIVE_TITLES if negative else POSITIVE_TITLES
    return mapping.get(subtype, cleaned or "핵심 경험")


def build_experience_summary(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_SUMMARIES if negative else POSITIVE_SUMMARIES
    return mapping.get(
        subtype,
        "플레이 흐름과 만족도를 함께 흔들 수 있어 미리 감수 여부를 보는 편이 좋습니다."
        if negative
        else "핵심 재미가 꾸준히 살아 있어 오래 붙잡기 쉬운 편입니다.",
    )


def build_headline_theme(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_HEADLINE_THEMES if negative else POSITIVE_HEADLINE_THEMES
    return mapping.get(subtype, str(theme or "핵심 경험"))


def build_evidence_title(
    *,
    theme: str | None,
    stance: str,
    aspect_keys: list[str] | None,
    genres: list[str] | None,
) -> str:
    aspect = str((aspect_keys or [""])[0] or "")
    negative = str(stance or "") == "negative"
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_EVIDENCE_TITLES if negative else POSITIVE_EVIDENCE_TITLES
    return mapping.get(
        subtype,
        "이 요소가 플레이 흐름을 자주 끊는다는 반응" if negative else "이 요소가 플레이 만족을 끌어올린다는 반응",
    )


def build_evidence_why_it_matters(
    *,
    stance: str,
    theme: str | None,
    aspect_keys: list[str] | None,
    genres: list[str] | None,
) -> str:
    aspect = str((aspect_keys or [""])[0] or "")
    negative = str(stance or "") == "negative"
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_EVIDENCE_SUMMARIES if negative else POSITIVE_EVIDENCE_SUMMARIES
    return mapping.get(
        subtype,
        "이 요소를 불편하게 느끼는 리뷰가 반복돼, 구매 전에 감수 가능한지 먼저 보는 편이 좋습니다."
        if negative
        else "이 요소를 좋게 보는 리뷰가 꾸준해, 취향이 맞으면 만족도가 높은 편입니다.",
    )


def build_fit_signal(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> dict[str, Any]:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    return {
        "aspect": str(aspect or ""),
        "theme": str(theme or "").strip(),
        "subtype": subtype,
        "negative": bool(negative),
    }


def _genre_flags(genres: list[str]) -> dict[str, bool]:
    normalized = " ".join(_tokenize(genres))
    return {
        key: any(hint in normalized for hint in hints)
        for key, hints in GENRE_HINTS.items()
    }


def _tokenize(values: list[str]) -> list[str]:
    tokens: list[str] = []
    for value in values:
        text = re.sub(r"[^0-9A-Za-z가-힣]+", " ", str(value or "").lower())
        tokens.extend(part.strip() for part in text.split() if part.strip())
    return list(dict.fromkeys(tokens))


def _matches_any(text: str, hints: tuple[str, ...]) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "").lower())
    return any(re.sub(r"\s+", "", hint.lower()) in normalized for hint in hints)


def _looks_like_internal_theme(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if "/" in value:
        return True
    if any(token in lowered for token in ("리스크", "포인트", "경험이 실제", "실제 플레이 만족", "체감")):
        return True
    if len(value) <= 4:
        return True
    return False
