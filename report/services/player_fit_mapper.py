"""Genre-aware player-fit and copy helpers.

This module keeps deterministic logic focused on:
- subtype inference
- safe fallback copy
- genre mismatch prevention

The final UI tone is still handled by the LLM layer, but the seed produced here
should already avoid obvious category mistakes such as:
- battle royale -> boss-pattern mastery
- visual novel -> combat / matchmaking language
- city builder -> combat flow language
"""

from __future__ import annotations

import re
from typing import Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", _normalize(text))


def _genre_blob(genres: list[str] | None) -> str:
    return " ".join(_normalize(value) for value in (genres or []))


def _theme_blob(theme: str | None) -> str:
    return _normalize(theme or "")


def _contains_any(blob: str, needles: tuple[str, ...]) -> bool:
    compact_blob = _compact(blob)
    return any(_compact(needle) in compact_blob for needle in needles)


GENRE_HINTS: dict[str, tuple[str, ...]] = {
    "shooter": ("shooter", "fps", "tps", "슈터", "사격", "총"),
    "battle_royale": ("battle royale", "배틀로얄", "battlegrounds"),
    "soulslike": ("soulslike", "소울", "action rpg", "액션 rpg", "액션rpg"),
    "openworld": ("open world", "오픈 월드", "openworld", "adventure", "어드벤처", "sandbox"),
    "management": ("management", "manager", "경영", "운영"),
    "sports": ("sports", "sport", "football", "soccer", "스포츠", "축구"),
    "strategy": ("strategy", "strategic", "tactics", "tactical", "4x", "전략", "전술"),
    "cozy": ("cozy", "farming", "farm", "life sim", "농장", "힐링", "생활"),
    "survival": ("survival", "생존", "craft", "crafting", "raid", "loot", "루팅"),
    "coop": ("co-op", "coop", "cooperative", "협동", "파티", "team"),
    "visual_novel": ("visual novel", "비주얼 노벨", "novel", "story rich", "선택형"),
    "city_builder": ("city builder", "city-building", "도시 건설", "city", "urban"),
    "automation": ("automation", "factory", "factorio", "belt", "logistics", "자동화", "공장"),
    "deckbuilder": ("deckbuilding", "deck builder", "card", "cards", "deck", "덱빌딩", "카드"),
    "roguelike": ("roguelike", "roguelite", "로그라이크", "로그라이트"),
    "turn_based": ("turn-based", "turn based", "턴제"),
}


THEME_HINTS: dict[str, tuple[str, ...]] = {
    "boss_pattern_mastery": ("보스", "패턴", "트라이", "반복 도전", "회피", "근접 전투"),
    "high_tension_melee_combat": ("손맛", "타격", "액션", "근접", "긴장감", "전투"),
    "world_lore_discovery": ("세계관", "서사", "단서", "해석", "탐험", "몰입"),
    "shooter_gunplay": ("총", "총기", "사격", "에임", "교전", "반동", "타격감"),
    "cooperative_mission_loop": ("협동", "팀워크", "파티", "임무", "클래스", "역할"),
    "survival_base_building": ("기지", "건설", "건축", "베이스", "방어", "생존"),
    "openworld_pvp_tension": ("생존", "파밍", "루팅", "교전", "긴장감", "매복"),
    "loot_and_loss_loop": ("루팅", "파밍", "손실", "리스크", "잃어버림", "보상"),
    "openworld_exploration": ("탐험", "월드", "자유도", "발견", "오픈월드"),
    "sandbox_freedom": ("자유도", "샌드박스", "창의", "마음대로"),
    "narrative_immersion": ("스토리", "서사", "캐릭터", "연출", "몰입"),
    "visual_narrative_immersion": ("감정선", "관계", "대사", "선택지", "심리", "충격"),
    "build_customization": ("빌드", "세팅", "커스터마이징", "조합", "무기"),
    "long_term_growth": ("성장", "볼륨", "장기", "오래", "반복 플레이"),
    "management_tactics": ("전술", "운영", "전략", "라인업", "로스터", "감독"),
    "life_sim_routine": ("하루 루틴", "마을", "생활", "관계", "일상"),
    "cozy_growth_loop": ("농장", "재배", "낚시", "채집", "힐링", "소소한 성장"),
    "city_builder_management": ("도시", "교통", "인프라", "배치", "행정", "도시 운영"),
    "automation_factory_optimization": ("자동화", "공장", "벨트", "물류", "병목", "최적화"),
    "deckbuilding_run_planning": ("덱", "카드", "유물", "경로", "한 판", "시너지"),
    "turn_based_tactical_pressure": ("턴제", "엄폐", "병력 손실", "포지셔닝", "한 턴"),
    "matchmaking_variance": ("매칭", "서버", "핑", "대기", "세션"),
    "stability_interruptions": ("버그", "오류", "크래시", "충돌", "튕김"),
    "performance_instability": ("프레임", "렉", "최적화", "버벅", "발열"),
    "onboarding_friction": ("튜토리얼", "입문", "초반", "적응", "조작감", "가이드"),
    "repetition_fatigue": ("반복", "지루", "피로", "루즈", "늘어진다"),
    "price_sensitivity": ("가격", "과금", "비싸", "가성비", "dlc"),
    "teamplay_stress": ("팀플", "소통", "스트레스", "정치", "팀원"),
    "balance_swings": ("밸런스", "메타", "너프", "버프", "불공정"),
    "save_safety": ("세이브", "저장", "로컬", "클라우드", "진행"),
    "translation_friction": ("번역", "자막", "대사", "텍스트", "오역"),
    "control_friction": ("조작", "ui", "인터페이스", "입력", "설정"),
}


POSITIVE_PLAYER_FIT = {
    "boss_pattern_mastery": "패턴을 익히며 반복 도전하는 재미를 좋아하는 플레이어",
    "high_tension_melee_combat": "긴장감 있는 근접 전투를 오래 붙잡는 플레이어",
    "world_lore_discovery": "탐험하며 세계와 단서를 해석하는 재미를 좋아하는 플레이어",
    "shooter_gunplay": "짧고 강한 교전 템포를 좋아하는 플레이어",
    "cooperative_mission_loop": "팀원과 합을 맞추며 협동 플레이하는 재미를 좋아하는 플레이어",
    "survival_base_building": "거점을 세우고 지켜내는 생존 루프를 좋아하는 플레이어",
    "openworld_pvp_tension": "파밍과 교전이 맞물리는 생존 긴장감을 즐기는 플레이어",
    "loot_and_loss_loop": "위험을 감수하고 자원을 챙겨 나오는 루프를 즐기는 플레이어",
    "openworld_exploration": "맵을 돌아다니며 발견하는 재미를 중요하게 보는 플레이어",
    "sandbox_freedom": "정해진 길보다 자기 방식으로 풀어가는 플레이를 좋아하는 플레이어",
    "narrative_immersion": "서사와 분위기에 오래 몰입하는 플레이어",
    "visual_narrative_immersion": "서사와 감정선에 깊게 몰입하는 플레이어",
    "build_customization": "세팅과 빌드를 바꿔가며 내 스타일을 찾는 플레이어",
    "long_term_growth": "하루에 오래 붙잡고 성장 루프를 깊게 파는 플레이어",
    "management_tactics": "전술과 운영 판단을 오래 다듬는 플레이어",
    "life_sim_routine": "하루 루틴을 천천히 쌓아가는 플레이어",
    "cozy_growth_loop": "부담 없이 차근차근 키워가는 재미를 좋아하는 플레이어",
    "city_builder_management": "도시를 키우며 흐름을 다듬는 운영형 플레이어",
    "automation_factory_optimization": "자동화 라인을 다듬으며 효율을 올리는 플레이어",
    "deckbuilding_run_planning": "한 판마다 덱 조합과 경로 선택을 즐기는 플레이어",
    "turn_based_tactical_pressure": "한 턴의 판단 무게를 즐기는 전술형 플레이어",
    "teamplay_synergy": "팀원과 호흡을 맞추는 재미를 중요하게 보는 플레이어",
    "visual_atmosphere": "배경과 연출까지 천천히 즐기는 플레이어",
    "core_play_mastery": "핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어",
}


NEGATIVE_PLAYER_FIT = {
    "matchmaking_variance": "매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어",
    "stability_interruptions": "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어",
    "performance_instability": "프레임과 반응성에 민감한 플레이어",
    "onboarding_friction": "처음부터 빠르게 적응하고 뛰어들고 싶은 플레이어",
    "repetition_fatigue": "반복 구간에 쉽게 지루해지는 플레이어",
    "price_sensitivity": "가격 대비 만족을 매우 엄격하게 따지는 플레이어",
    "teamplay_stress": "팀플레이 소통 피로를 크게 느끼는 플레이어",
    "balance_swings": "밸런스 변화에 민감하게 반응하는 플레이어",
    "save_safety": "저장과 진행 안정성을 특히 중요하게 보는 플레이어",
    "translation_friction": "텍스트와 번역 품질에 민감한 플레이어",
    "control_friction": "조작과 인터페이스 적응 스트레스를 크게 받는 플레이어",
}


POSITIVE_TITLES = {
    "boss_pattern_mastery": "반복 도전에 손이 붙는 전투 감각",
    "high_tension_melee_combat": "긴장감이 오래 유지되는 근접 전투",
    "world_lore_discovery": "탐험과 세계 해석이 이어지는 몰입 경험",
    "shooter_gunplay": "교전 손맛과 템포가 살아 있는 슈팅 경험",
    "cooperative_mission_loop": "협동과 역할 분담이 맞물리는 임무 흐름",
    "survival_base_building": "거점을 세우고 지켜내는 생존 루프",
    "openworld_pvp_tension": "파밍과 교전이 맞물리는 생존 긴장감",
    "loot_and_loss_loop": "위험과 보상이 분명한 루팅 루프",
    "openworld_exploration": "발견이 이어지는 탐험 경험",
    "sandbox_freedom": "자유롭게 풀어가는 샌드박스 플레이",
    "narrative_immersion": "세계와 사건에 빨려드는 몰입감",
    "visual_narrative_immersion": "감정선과 장면 전환이 오래 남는 서사 경험",
    "build_customization": "세팅을 바꿔가며 즐기는 빌드 실험",
    "long_term_growth": "오래 붙잡게 만드는 성장 루프",
    "management_tactics": "전술과 운영 판단의 깊이",
    "life_sim_routine": "하루하루 쌓아가는 생활 루프",
    "cozy_growth_loop": "편안하게 이어지는 성장 흐름",
    "city_builder_management": "도시 흐름을 다듬는 운영의 재미",
    "automation_factory_optimization": "병목을 풀며 확장하는 자동화 설계",
    "deckbuilding_run_planning": "카드 선택과 경로 판단이 살아 있는 한 판 루프",
    "turn_based_tactical_pressure": "한 턴의 선택이 무거운 전술 압박",
    "teamplay_synergy": "팀 합과 호흡이 살아 있는 멀티플레이 흐름",
    "visual_atmosphere": "분위기를 밀어주는 비주얼과 연출",
    "core_play_mastery": "계속 손에 붙는 핵심 플레이 감각",
}


NEGATIVE_TITLES = {
    "matchmaking_variance": "매칭과 서버 상태에 따라 체감이 흔들리는 구간",
    "stability_interruptions": "예상치 못한 오류로 흐름이 끊길 수 있는 구간",
    "performance_instability": "프레임과 반응성이 흔들리는 구간",
    "onboarding_friction": "초반 적응에 시간이 필요한 구조",
    "repetition_fatigue": "반복 구간이 길어질수록 피로가 커지는 부분",
    "price_sensitivity": "가격 대비 만족이 갈릴 수 있는 부분",
    "teamplay_stress": "팀플레이 피로가 크게 느껴질 수 있는 부분",
    "balance_swings": "밸런스 변화가 체감에 직접 닿는 부분",
    "save_safety": "진행 안정성에 대한 불안이 남는 부분",
    "translation_friction": "번역과 텍스트 흐름이 몰입을 끊는 부분",
    "control_friction": "조작 적응이 답답하게 느껴질 수 있는 부분",
}


POSITIVE_SUMMARIES = {
    "boss_pattern_mastery": "반복할수록 손에 붙는 전투 감각이 살아 있어 도전 자체를 즐기기 좋습니다.",
    "high_tension_melee_combat": "근접 전투의 긴장감이 꾸준히 유지돼 전투 비중이 높은 플레이에 잘 맞습니다.",
    "world_lore_discovery": "탐험과 단서 해석이 맞물려 스스로 세계를 읽어가는 재미가 분명합니다.",
    "shooter_gunplay": "교전 손맛과 템포가 살아 있어 한 판씩 다시 들어가게 만드는 힘이 있습니다.",
    "cooperative_mission_loop": "역할 분담과 협동 흐름이 잘 맞물려 함께할수록 재미가 올라갑니다.",
    "survival_base_building": "거점을 세우고 지켜내는 과정이 분명해 생존 루프를 오래 붙잡기 좋습니다.",
    "openworld_pvp_tension": "파밍과 교전이 맞물리는 긴장감이 강해서 생존 장르 특유의 압박이 잘 살아 있습니다.",
    "loot_and_loss_loop": "위험을 감수하고 보상을 챙겨 나오는 구조가 분명해 루프의 동기가 또렷합니다.",
    "openworld_exploration": "이동하고 발견하는 과정 자체가 재미를 만들어 탐험 비중이 높은 플레이에 맞습니다.",
    "sandbox_freedom": "정해진 답보다 자기 방식으로 풀어가는 자유도가 커서 실험하는 재미가 있습니다.",
    "narrative_immersion": "세계와 사건에 빨려들 듯 몰입하는 흐름이 살아 있어 분위기와 서사를 중시할 때 만족도가 높습니다.",
    "visual_narrative_immersion": "감정선과 장면 전환이 오래 남아 이야기를 따라가는 몰입감이 강합니다.",
    "build_customization": "세팅을 바꾸며 내 스타일을 찾는 재미가 분명해 여러 방식으로 오래 즐기기 좋습니다.",
    "long_term_growth": "목표를 쌓아가며 오래 붙잡게 되는 성장 구조가 강해 장기 플레이와 잘 맞습니다.",
    "management_tactics": "전술과 운영 판단이 계속 이어져 생각하면서 오래 붙잡기 좋은 구조입니다.",
    "life_sim_routine": "하루 루틴을 차분히 쌓아가는 흐름이 안정적이라 천천히 이어가는 플레이에 맞습니다.",
    "cozy_growth_loop": "부담 없이 조금씩 키워가는 흐름이 좋아 편하게 오래 즐기기 좋습니다.",
    "city_builder_management": "도시의 흐름을 조정하고 균형을 맞추는 재미가 분명해 운영형 플레이에 잘 맞습니다.",
    "automation_factory_optimization": "병목을 풀고 생산 라인을 확장하는 과정이 재미의 중심이라 최적화를 즐길수록 만족도가 높습니다.",
    "deckbuilding_run_planning": "카드 선택과 경로 판단이 매번 달라져 한 판 한 판 계획을 세우는 재미가 살아 있습니다.",
    "turn_based_tactical_pressure": "한 턴의 판단이 크게 작용해 전술 선택의 무게를 즐기는 쪽에 잘 맞습니다.",
    "teamplay_synergy": "팀 합이 맞을수록 재미가 분명해져 함께 호흡을 맞추는 플레이에 잘 맞습니다.",
    "visual_atmosphere": "비주얼과 연출이 분위기를 오래 밀어줘 화면과 감각을 즐기는 플레이에 잘 맞습니다.",
    "core_play_mastery": "기본 플레이 감각이 좋아 손에 익을수록 재미가 커지는 편입니다.",
}


NEGATIVE_SUMMARIES = {
    "matchmaking_variance": "매칭과 서버 상태가 흔들리면 한 판의 완성도가 크게 달라질 수 있습니다.",
    "stability_interruptions": "예상치 못한 오류가 생기면 플레이 흐름이 끊겨 피로가 빠르게 쌓일 수 있습니다.",
    "performance_instability": "프레임과 반응성이 흔들리면 조작 감각이 무너져 답답하게 느껴질 수 있습니다.",
    "onboarding_friction": "규칙과 조작에 익숙해지기 전까지는 진입 장벽이 높게 느껴질 수 있습니다.",
    "repetition_fatigue": "익숙해진 뒤에는 새로움보다 반복감이 먼저 느껴질 수 있습니다.",
    "price_sensitivity": "가격 부담이 크면 기대만큼 만족하지 못했다는 반응이 나올 수 있습니다.",
    "teamplay_stress": "팀원과의 호흡이 맞지 않으면 플레이보다 피로가 먼저 커질 수 있습니다.",
    "balance_swings": "밸런스 변화가 체감에 직접 닿아 플레이 감각이 흔들릴 수 있습니다.",
    "save_safety": "저장과 진행 안정성이 불안하면 게임 자체보다 불안감이 더 크게 남을 수 있습니다.",
    "translation_friction": "텍스트와 번역 흐름이 매끄럽지 않으면 몰입이 자주 끊길 수 있습니다.",
    "control_friction": "조작과 인터페이스 적응에 시간이 걸리면 재미보다 답답함이 먼저 올 수 있습니다.",
}


POSITIVE_HEADLINE_THEMES = {
    "boss_pattern_mastery": "반복 도전에 손이 붙는 전투 감각",
    "high_tension_melee_combat": "긴장감 있는 근접 전투",
    "world_lore_discovery": "탐험과 세계 해석의 재미",
    "shooter_gunplay": "교전 템포와 사격 감각",
    "cooperative_mission_loop": "협동과 역할 분담의 재미",
    "survival_base_building": "거점을 세우며 이어가는 생존 루프",
    "openworld_pvp_tension": "파밍과 교전이 맞물리는 생존 긴장감",
    "loot_and_loss_loop": "위험과 보상이 또렷한 루프",
    "openworld_exploration": "탐험과 자유도",
    "sandbox_freedom": "정해진 답보다 자유로운 플레이",
    "narrative_immersion": "서사와 몰입감",
    "visual_narrative_immersion": "감정선이 오래 남는 서사 몰입",
    "build_customization": "빌드 실험과 세팅의 재미",
    "long_term_growth": "오래 붙잡게 만드는 성장 루프",
    "management_tactics": "전술과 운영 판단의 깊이",
    "life_sim_routine": "차분히 쌓이는 생활 루프",
    "cozy_growth_loop": "편안하게 이어지는 성장 흐름",
    "city_builder_management": "도시를 다듬는 운영의 재미",
    "automation_factory_optimization": "자동화와 최적화의 재미",
    "deckbuilding_run_planning": "덱 구성과 한 판 설계의 재미",
    "turn_based_tactical_pressure": "한 턴 판단의 압박감",
    "teamplay_synergy": "팀 합과 협업의 재미",
    "visual_atmosphere": "비주얼과 분위기",
    "core_play_mastery": "핵심 플레이 감각",
}


NEGATIVE_HEADLINE_THEMES = {
    "matchmaking_variance": "매칭과 서버 상태 변화",
    "stability_interruptions": "예상치 못한 오류",
    "performance_instability": "프레임과 반응성 문제",
    "onboarding_friction": "초반 적응 부담",
    "repetition_fatigue": "반복 피로",
    "price_sensitivity": "가격 대비 만족의 편차",
    "teamplay_stress": "팀플레이 피로",
    "balance_swings": "밸런스 변화 스트레스",
    "save_safety": "진행 안정성 불안",
    "translation_friction": "번역과 텍스트 흐름 문제",
    "control_friction": "조작 적응 부담",
}


POSITIVE_EVIDENCE_TITLES = {
    "boss_pattern_mastery": "반복 도전 속에서 전투 감각이 살아난다는 반응",
    "high_tension_melee_combat": "근접 전투의 긴장감이 오래 간다는 반응",
    "world_lore_discovery": "탐험과 세계 해석의 재미가 남는다는 반응",
    "shooter_gunplay": "교전 손맛과 템포가 좋다는 반응",
    "cooperative_mission_loop": "협동 플레이가 오래 붙잡게 만든다는 반응",
    "survival_base_building": "거점을 세우고 지키는 과정이 재미로 이어진다는 반응",
    "openworld_pvp_tension": "파밍과 교전이 만드는 긴장감이 좋다는 반응",
    "loot_and_loss_loop": "위험과 보상이 분명한 루프가 매력적이라는 반응",
    "openworld_exploration": "탐험하며 발견하는 재미가 크다는 반응",
    "sandbox_freedom": "자기 방식으로 풀어가는 자유도가 좋다는 반응",
    "narrative_immersion": "세계와 사건에 몰입하게 된다는 반응",
    "visual_narrative_immersion": "감정선과 전개가 오래 남는다는 반응",
    "build_customization": "세팅을 바꿔보는 재미가 크다는 반응",
    "long_term_growth": "오래 붙잡게 되는 성장 루프가 있다는 반응",
    "management_tactics": "전술과 운영 판단이 오래 재미를 만든다는 반응",
    "life_sim_routine": "하루 루틴을 쌓아가는 재미가 좋다는 반응",
    "cozy_growth_loop": "부담 없이 키워가는 흐름이 좋다는 반응",
    "city_builder_management": "도시를 다듬고 확장하는 재미가 좋다는 반응",
    "automation_factory_optimization": "자동화와 병목 해소의 재미가 분명하다는 반응",
    "deckbuilding_run_planning": "카드 선택과 덱 조합이 판마다 재미를 만든다는 반응",
    "turn_based_tactical_pressure": "한 턴의 선택이 긴장감을 만든다는 반응",
    "teamplay_synergy": "팀 합이 맞을 때 재미가 커진다는 반응",
    "visual_atmosphere": "비주얼과 분위기가 몰입을 끌어준다는 반응",
    "core_play_mastery": "핵심 플레이 감각이 좋다는 반응",
}


NEGATIVE_EVIDENCE_TITLES = {
    "matchmaking_variance": "매칭과 서버 상태가 체감을 흔든다는 반응",
    "stability_interruptions": "예상치 못한 오류가 흐름을 끊는다는 반응",
    "performance_instability": "프레임과 반응성이 걸림돌이 된다는 반응",
    "onboarding_friction": "초반 적응이 답답하다는 반응",
    "repetition_fatigue": "반복감 때문에 동기 유지가 어렵다는 반응",
    "price_sensitivity": "가격 대비 만족이 갈린다는 반응",
    "teamplay_stress": "팀플레이 피로가 크게 남는다는 반응",
    "balance_swings": "밸런스 변화에 스트레스를 받는다는 반응",
    "save_safety": "진행 안정성이 불안하다는 반응",
    "translation_friction": "번역과 텍스트 흐름이 걸린다는 반응",
    "control_friction": "조작 적응이 답답하다는 반응",
}


POSITIVE_EVIDENCE_SUMMARIES = {
    "boss_pattern_mastery": "반복 도전 자체를 재미로 받아들이는 반응이 많아, 도전형 전투를 좋아할수록 만족도가 높아질 수 있습니다.",
    "high_tension_melee_combat": "근접 전투의 긴장감과 손맛을 좋게 보는 반응이 많아, 전투 비중이 높을수록 잘 맞는 편입니다.",
    "world_lore_discovery": "탐험과 단서 해석이 플레이 동력이라는 반응이 많아, 스스로 읽어가는 몰입을 좋아하면 더 잘 맞습니다.",
    "shooter_gunplay": "사격 감각과 교전 템포를 좋게 보는 반응이 많아, 짧고 강한 전투를 좋아하면 만족도가 높을 수 있습니다.",
    "cooperative_mission_loop": "협동과 역할 분담의 재미를 말하는 반응이 많아, 함께할수록 재미가 올라가는 구조에 가깝습니다.",
    "survival_base_building": "거점을 세우고 지키는 재미를 좋게 보는 반응이 많아, 차근차근 쌓아가는 플레이에 잘 맞습니다.",
    "openworld_pvp_tension": "생존 장르 특유의 긴장감을 좋게 보는 반응이 많아, 파밍과 교전의 압박을 즐기면 잘 맞습니다.",
    "loot_and_loss_loop": "위험과 보상이 분명한 루프를 좋게 보는 반응이 많아, 손실을 감수하는 긴장감이 재미로 이어집니다.",
    "openworld_exploration": "탐험과 발견 그 자체를 좋게 보는 반응이 많아, 돌아다니며 찾는 플레이를 좋아하면 잘 맞습니다.",
    "sandbox_freedom": "자유롭게 풀어가는 방식을 좋게 보는 반응이 많아, 정답 없는 플레이를 선호할수록 만족도가 높습니다.",
    "narrative_immersion": "세계와 사건에 몰입한다는 반응이 많아, 분위기와 서사를 중시하면 오래 붙잡히기 좋습니다.",
    "visual_narrative_immersion": "감정선과 전개가 오래 남는다는 반응이 많아, 이야기에 깊게 몰입하는 쪽에 특히 잘 맞습니다.",
    "build_customization": "세팅을 바꾸며 즐기는 반응이 많아, 여러 스타일을 시도해보는 플레이에 잘 맞습니다.",
    "long_term_growth": "오래 붙잡는 이유가 분명하다는 반응이 많아, 장기 플레이 동기가 필요한 게임에 가깝습니다.",
    "management_tactics": "운영과 전술 판단의 재미를 말하는 반응이 많아, 생각하면서 오래 즐기는 플레이에 잘 맞습니다.",
    "life_sim_routine": "하루 루틴을 쌓는 재미를 좋게 보는 반응이 많아, 천천히 이어가는 플레이어에게 잘 맞습니다.",
    "cozy_growth_loop": "부담 없이 키워가는 재미를 좋게 보는 반응이 많아, 편안한 성장 루프를 원할 때 만족도가 높습니다.",
    "city_builder_management": "도시 운영의 흐름을 만지는 재미를 말하는 반응이 많아, 균형과 확장을 다듬는 플레이에 잘 맞습니다.",
    "automation_factory_optimization": "자동화와 효율 설계를 좋게 보는 반응이 많아, 병목을 풀고 확장하는 과정이 핵심 재미로 읽힙니다.",
    "deckbuilding_run_planning": "카드 선택과 경로 판단이 매 판 재미를 만든다는 반응이 많아, 계획을 세워 굴리는 플레이에 잘 맞습니다.",
    "turn_based_tactical_pressure": "한 턴의 선택이 크게 작용한다는 반응이 많아, 전술 판단의 압박을 즐기면 잘 맞습니다.",
    "teamplay_synergy": "팀 합이 맞을 때 만족도가 올라간다는 반응이 많아, 함께 맞춰가는 플레이를 좋아하면 잘 맞습니다.",
    "visual_atmosphere": "비주얼과 분위기를 좋게 보는 반응이 많아, 화면과 연출을 중요하게 보면 만족도가 높습니다.",
    "core_play_mastery": "기본 플레이 감각을 좋게 보는 반응이 많아, 손에 익는 재미가 중요한 쪽에 잘 맞습니다.",
}


NEGATIVE_EVIDENCE_SUMMARIES = {
    "matchmaking_variance": "매칭과 서버 상태를 문제로 보는 반응이 이어져, 한 판의 완성도가 상황에 따라 꽤 달라질 수 있습니다.",
    "stability_interruptions": "오류와 튕김을 반복해서 언급하는 반응이 있어, 흐름이 끊기는 상황을 감수해야 할 수 있습니다.",
    "performance_instability": "프레임과 반응성 문제를 짚는 반응이 있어, 조작 감각이 중요하면 거슬릴 가능성이 있습니다.",
    "onboarding_friction": "초반 적응이 답답하다는 반응이 있어, 바로 손에 익는 경험을 원하면 진입 장벽이 높을 수 있습니다.",
    "repetition_fatigue": "반복감이 피로로 이어진다는 반응이 있어, 새로움이 빨리 줄어드는 구간은 감수해야 할 수 있습니다.",
    "price_sensitivity": "가격 부담을 지적하는 반응이 있어, 비용 대비 만족에 민감하면 판단이 갈릴 수 있습니다.",
    "teamplay_stress": "소통과 팀플레이 피로를 말하는 반응이 있어, 합이 잘 맞지 않으면 재미보다 피로가 먼저 올 수 있습니다.",
    "balance_swings": "밸런스 변화에 대한 반응이 이어져, 메타 변화에 민감하면 스트레스가 남을 수 있습니다.",
    "save_safety": "저장과 진행 안정성을 걱정하는 반응이 있어, 누적 플레이 안정성을 중요하게 보면 불안이 남을 수 있습니다.",
    "translation_friction": "번역과 텍스트 흐름을 걸림돌로 보는 반응이 있어, 읽는 경험을 중시하면 몰입이 자주 끊길 수 있습니다.",
    "control_friction": "조작과 인터페이스 적응이 어렵다는 반응이 있어, 처음부터 부드러운 조작감을 원하면 답답할 수 있습니다.",
}


def _genre_flags(genres: list[str] | None) -> dict[str, bool]:
    blob = _genre_blob(genres)
    return {key: _contains_any(blob, hints) for key, hints in GENRE_HINTS.items()}


def _looks_like_internal_theme(theme: str | None) -> bool:
    value = str(theme or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if "/" in value:
        return True
    bad_fragments = ("리스크", "사인", "실제 플레이 만족", "체감", "반응", "경험이다")
    return any(fragment in lowered for fragment in bad_fragments) or len(value) <= 4


def infer_copy_subtype(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    aspect_key = _normalize(aspect)
    theme_blob = _theme_blob(theme)
    flags = _genre_flags(genres)

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
            return "teamplay_stress" if (flags["shooter"] or flags["battle_royale"] or flags["coop"]) else "matchmaking_variance"
        if aspect_key == "balance":
            return "balance_swings"
        if aspect_key == "save_progression":
            return "save_safety"
        if aspect_key == "localization":
            return "translation_friction"
        if aspect_key in {"controls", "building_ux"}:
            return "control_friction"
        if aspect_key == "content_depth":
            return "repetition_fatigue"
        if aspect_key == "gameplay":
            if _contains_any(theme_blob, THEME_HINTS["matchmaking_variance"]):
                return "matchmaking_variance"
            if _contains_any(theme_blob, THEME_HINTS["control_friction"]):
                return "control_friction"
            if _contains_any(theme_blob, THEME_HINTS["repetition_fatigue"]):
                return "repetition_fatigue"
            if flags["battle_royale"] or flags["shooter"] or flags["survival"]:
                return "performance_instability"
            return "repetition_fatigue"
        return "stability_interruptions"

    if flags["visual_novel"] or _contains_any(theme_blob, THEME_HINTS["visual_narrative_immersion"]):
        if aspect_key in {"story", "gameplay", "content_depth"}:
            return "visual_narrative_immersion"

    if flags["city_builder"] or _contains_any(theme_blob, THEME_HINTS["city_builder_management"]):
        if aspect_key in {"gameplay", "content_depth", "building_ux"}:
            return "city_builder_management"

    if flags["automation"] or _contains_any(theme_blob, THEME_HINTS["automation_factory_optimization"]):
        if aspect_key in {"gameplay", "content_depth", "building_ux"}:
            return "automation_factory_optimization"

    if flags["deckbuilder"] or _contains_any(theme_blob, THEME_HINTS["deckbuilding_run_planning"]):
        if aspect_key in {"gameplay", "content_depth", "customization"}:
            return "deckbuilding_run_planning"

    if (flags["turn_based"] or _contains_any(theme_blob, THEME_HINTS["turn_based_tactical_pressure"])) and aspect_key in {
        "gameplay",
        "content_depth",
        "difficulty",
    }:
        return "turn_based_tactical_pressure"

    if aspect_key == "story":
        if flags["soulslike"] or _contains_any(theme_blob, THEME_HINTS["world_lore_discovery"]):
            return "world_lore_discovery"
        return "narrative_immersion"

    if aspect_key in {"graphics", "sound"}:
        return "visual_atmosphere"

    if aspect_key == "customization":
        if flags["deckbuilder"]:
            return "deckbuilding_run_planning"
        return "build_customization"

    if aspect_key == "content_depth":
        if flags["management"] or flags["sports"] or flags["strategy"]:
            return "management_tactics"
        if flags["city_builder"]:
            return "city_builder_management"
        if flags["automation"]:
            return "automation_factory_optimization"
        if flags["deckbuilder"]:
            return "deckbuilding_run_planning"
        if flags["cozy"]:
            return "cozy_growth_loop"
        if flags["survival"]:
            return "survival_base_building"
        return "long_term_growth"

    if aspect_key == "multiplayer":
        if flags["coop"]:
            return "cooperative_mission_loop"
        if flags["battle_royale"] or flags["shooter"]:
            return "openworld_pvp_tension"
        return "teamplay_synergy"

    if aspect_key in {"building_ux"}:
        if flags["city_builder"]:
            return "city_builder_management"
        if flags["automation"]:
            return "automation_factory_optimization"
        return "control_friction"

    if aspect_key == "gameplay":
        if flags["management"] or flags["sports"] or flags["strategy"]:
            return "management_tactics"
        if flags["cozy"]:
            return "life_sim_routine" if _contains_any(theme_blob, THEME_HINTS["life_sim_routine"]) else "cozy_growth_loop"
        if flags["battle_royale"]:
            return "openworld_pvp_tension"
        if flags["survival"]:
            if _contains_any(theme_blob, THEME_HINTS["survival_base_building"]):
                return "survival_base_building"
            if _contains_any(theme_blob, THEME_HINTS["loot_and_loss_loop"]):
                return "loot_and_loss_loop"
            return "openworld_pvp_tension"
        if flags["coop"]:
            return "cooperative_mission_loop"
        if flags["shooter"] or _contains_any(theme_blob, THEME_HINTS["shooter_gunplay"]):
            return "shooter_gunplay"
        if flags["soulslike"] or _contains_any(theme_blob, THEME_HINTS["boss_pattern_mastery"]):
            if _contains_any(theme_blob, THEME_HINTS["world_lore_discovery"]):
                return "world_lore_discovery"
            if _contains_any(theme_blob, THEME_HINTS["high_tension_melee_combat"]):
                return "high_tension_melee_combat"
            return "boss_pattern_mastery"
        if flags["openworld"] or _contains_any(theme_blob, THEME_HINTS["openworld_exploration"]):
            return "openworld_exploration"
        if _contains_any(theme_blob, THEME_HINTS["sandbox_freedom"]):
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
    return mapping.get(
        subtype,
        "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어"
        if negative
        else "핵심 플레이를 반복하며 손에 익혀가는 재미를 즐기는 플레이어",
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
        "플레이 흐름과 만족도가 흔들릴 수 있어 미리 감수 여부를 보는 편이 좋습니다."
        if negative
        else "핵심 경험의 매력이 살아 있어 오래 붙잡기 쉬운 편입니다.",
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
        "이 요소가 플레이 흐름을 자주 끊는다는 반응" if negative else "이 요소가 실제 만족으로 이어진다는 반응",
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
        "이 요소를 불편하게 느끼는 반응이 이어져 구매 전 감수 여부를 먼저 보는 편이 좋습니다."
        if negative
        else "이 요소를 좋게 보는 반응이 많아 취향만 맞으면 만족도가 높을 가능성이 있습니다.",
    )


def build_fit_signal(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> dict[str, Any]:
    return {
        "aspect": str(aspect or ""),
        "theme": str(theme or "").strip(),
        "subtype": infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative),
        "negative": bool(negative),
    }
