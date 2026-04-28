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
    "visual_novel": ("visual novel", "비주얼 노벨", "novel", "literature club", "선택형"),
    "city_builder": ("city builder", "city-building", "도시 건설", "city simulation", "urban"),
    "automation": ("automation", "factory", "factorio", "belt", "logistics", "자동화", "공장"),
    "looter_shooter": (
        "looter shooter",
        "loot shooter",
        "destiny 2",
        "데스티니 가디언즈",
        "action mmo",
        "온라인 액션",
        "warframe",
        "무기고",
        "워프레임",
    ),
    "coop_live_service": (
        "helldivers 2",
        "helldivers™ 2",
        "헬다이버",
        "co-op shooter",
        "cooperative shooter",
        "live service shooter",
        "3인칭 슈팅",
    ),
    "narrative_openworld": ("the witcher 3", "witcher 3", "red dead redemption 2", "story rich open world", "open world rpg"),
    "life_sim": ("life sim", "social sim", "the sims", "sims 4", "inzoi", "daily life"),
    "deckbuilder": ("deckbuilding", "deck builder", "card", "cards", "deck", "덱빌딩", "카드"),
    "roguelike": ("roguelike", "roguelite", "로그라이크", "로그라이트"),
    "turn_based": ("turn-based", "turn based", "턴제"),
}


THEME_HINTS: dict[str, tuple[str, ...]] = {
    "boss_pattern_mastery": ("보스", "패턴", "트라이", "반복 도전", "회피"),
    "high_tension_melee_combat": ("근접", "타격", "액션", "근접전", "긴장감", "전투"),
    "world_lore_discovery": ("세계관", "서사", "단서", "해석", "탐험", "몰입"),
    "shooter_gunplay": ("총", "총기", "사격", "에임", "교전", "반동", "타격감"),
    "cooperative_mission_loop": ("협동", "팀워크", "파티", "임무", "클래스", "역할"),
    "survival_base_building": ("기지", "건설", "건축", "베이스", "방어", "생존"),
    "openworld_pvp_tension": ("생존", "루팅", "전리품", "교전", "긴장감", "약탈"),
    "loot_and_loss_loop": ("루팅", "전리품", "잃음", "리스크", "보상"),
    "openworld_exploration": ("탐험", "월드", "자유도", "발견", "오픈월드"),
    "sandbox_freedom": ("자유도", "샌드박스", "창의", "마음대로"),
    "narrative_immersion": ("스토리", "서사", "캐릭터", "연출", "몰입"),
    "visual_narrative_immersion": ("감정선", "대사", "선택지", "심리", "충격"),
    "build_customization": ("빌드", "세팅", "커스텀", "조합", "무기"),
    "long_term_growth": ("성장", "볼륨", "후기", "오래", "반복 플레이"),
    "management_tactics": ("전술", "운영", "전략", "라인업", "로스터", "감독"),
    "life_sim_routine": ("하루 루틴", "마을", "생활", "관계", "일상"),
    "cozy_growth_loop": ("농장", "목장", "낚시", "채집", "힐링", "성장"),
    "city_builder_management": ("도시", "교통", "인프라", "배치", "행정", "도시 운영"),
    "automation_factory_optimization": ("자동화", "공장", "벨트", "물류", "병목", "최적화"),
    "looter_shooter_progression": ("장비", "빌드", "파밍", "수집", "반복 임무"),
    "cooperative_live_service_shooter": ("분대", "협동 전투", "임무 수행", "역할 분담", "난전"),
    "narrative_openworld_immersion": ("사건", "인물", "퀘스트", "여운", "세계 체험", "오픈월드 서사"),
    "life_sim_social_loop": ("생활", "관계", "꾸미기", "일상", "집 꾸미기", "자유도"),
    "deckbuilding_run_planning": ("덱", "카드", "드로우", "경로", "유물", "시너지"),
    "turn_based_tactical_pressure": ("턴제", "엄폐", "병력 손실", "포지셔닝", "한 턴"),
    "matchmaking_variance": ("매칭", "서버", "핑", "대기", "연결"),
    "stability_interruptions": ("버그", "오류", "크래시", "충돌", "끊김"),
    "performance_instability": ("프레임", "렉", "최적화", "버벅", "발열"),
    "onboarding_friction": ("튜토리얼", "입문", "초반", "적응", "조작감", "가이드"),
    "repetition_fatigue": ("반복", "지루", "피로", "루프", "되풀이"),
    "price_sensitivity": ("가격", "고가", "비쌈", "가성비", "dlc"),
    "teamplay_stress": ("팀원", "소통", "스트레스", "정치", "팀플"),
    "balance_swings": ("밸런스", "메타", "너프", "버프", "불공정"),
    "save_safety": ("세이브", "저장", "롤백", "진행"),
    "translation_friction": ("번역", "자막", "텍스트", "오역"),
    "control_friction": ("조작", "ui", "인터페이스", "입력", "설정"),
}


POSITIVE_BUNDLES: dict[str, dict[str, str]] = {
    "boss_pattern_mastery": {
        "player_fit": "패턴을 익히며 반복 도전하는 플레이어",
        "title": "반복 도전의 손맛이 살아 있는 전투",
        "summary": "반복할수록 손에 붙는 전투 감각이 있어 재도전 자체를 즐기는 쪽에 잘 맞습니다.",
        "headline": "반복 도전의 손맛",
        "evidence_title": "반복 도전의 손맛이 좋다는 반응",
        "evidence_summary": "패턴을 익히며 돌파하는 과정 자체를 재미로 보는 반응이 많아, 재도전을 즐기면 만족도가 높습니다.",
    },
    "high_tension_melee_combat": {
        "player_fit": "긴장감 있는 근접 전투를 오래 붙잡는 플레이어",
        "title": "긴장감이 오래 이어지는 근접 전투",
        "summary": "근접 전투의 긴장감이 끊기지 않아 전투 비중이 높은 플레이와 잘 맞습니다.",
        "headline": "긴장감 있는 근접 전투",
        "evidence_title": "근접 전투의 긴장감이 좋다는 반응",
        "evidence_summary": "근접 전투의 밀도와 긴장감을 좋게 보는 반응이 많아 액션 비중이 높은 플레이에 잘 맞습니다.",
    },
    "world_lore_discovery": {
        "player_fit": "세계관과 맥락을 스스로 읽어가는 플레이어",
        "title": "탐험과 맥락 해석이 이어지는 몰입 경험",
        "summary": "탐험과 단서 해석이 맞물려 세계를 천천히 읽어가는 몰입감이 분명합니다.",
        "headline": "탐험과 세계 해석의 몰입감",
        "evidence_title": "탐험과 맥락 해석의 재미가 있다는 반응",
        "evidence_summary": "세계의 단서와 맥락을 읽어가는 재미를 좋게 보는 반응이 많아 서서히 몰입하는 플레이와 잘 맞습니다.",
    },
    "shooter_gunplay": {
        "player_fit": "짧고 강한 교전 템포를 좋아하는 플레이어",
        "title": "교전 템포와 사격 감각",
        "summary": "교전 템포와 사격 감각이 또렷해서 순간 집중이 필요한 플레이에 잘 맞습니다.",
        "headline": "교전 템포와 사격 감각",
        "evidence_title": "교전 감각이 좋다는 반응",
        "evidence_summary": "교전 감각과 사격 손맛을 좋게 보는 반응이 많아 순간 집중형 플레이에 특히 잘 맞습니다.",
    },
    "cooperative_mission_loop": {
        "player_fit": "팀원과 합을 맞추며 협동 플레이하는 재미를 좋아하는 플레이어",
        "title": "협동과 역할 분담의 임무 흐름",
        "summary": "역할 분담과 협동 흐름이 잘 맞물려 함께할수록 재미가 올라갑니다.",
        "headline": "협동과 역할 분담의 재미",
        "evidence_title": "협동과 역할 분담의 재미가 크다는 반응",
        "evidence_summary": "협동과 역할 분담의 재미를 말하는 반응이 많아 함께할수록 만족도가 올라가는 구조에 가깝습니다.",
    },
    "survival_base_building": {
        "player_fit": "거점을 키우고 지켜내는 생존 루프를 좋아하는 플레이어",
        "title": "거점을 세우며 이어가는 생존 루프",
        "summary": "거점을 세우고 지켜내는 과정이 생존 루프의 중심이라 천천히 쌓아가는 플레이에 잘 맞습니다.",
        "headline": "거점을 키우는 생존 루프",
        "evidence_title": "거점 운영과 생존 루프가 좋다는 반응",
        "evidence_summary": "거점을 키우고 지켜내는 과정을 좋게 보는 반응이 많아 장기 생존 플레이에 잘 맞습니다.",
    },
    "openworld_pvp_tension": {
        "player_fit": "루팅과 교전이 맞물리는 생존 긴장감을 즐기는 플레이어",
        "title": "루팅과 교전이 맞물리는 생존 긴장감",
        "summary": "루팅과 교전이 맞물리는 긴장감이 강해 한 판의 압박을 즐기면 잘 맞습니다.",
        "headline": "생존 긴장감이 강한 교전 루프",
        "evidence_title": "생존 긴장감이 크다는 반응",
        "evidence_summary": "한 번의 루팅과 교전이 크게 이어지는 긴장감을 좋게 보는 반응이 많습니다.",
    },
    "loot_and_loss_loop": {
        "player_fit": "위험과 보상이 맞물리는 루팅 루프를 즐기는 플레이어",
        "title": "위험과 보상이 분명한 루팅 루프",
        "summary": "얻는 것과 잃는 것의 압박이 분명해 긴장감 있는 루프가 살아 있습니다.",
        "headline": "위험과 보상의 루팅 루프",
        "evidence_title": "루팅과 위험 관리의 재미가 크다는 반응",
        "evidence_summary": "루팅과 손실 감수의 긴장감을 좋게 보는 반응이 많아 보상형 루프를 좋아하면 잘 맞습니다.",
    },
    "openworld_exploration": {
        "player_fit": "맵을 돌아다니며 발견하는 재미를 중요하게 보는 플레이어",
        "title": "발견이 이어지는 탐험 경험",
        "summary": "이동과 발견 그 자체가 재미로 이어져 탐험 비중이 높은 플레이와 잘 맞습니다.",
        "headline": "발견이 이어지는 탐험 경험",
        "evidence_title": "탐험과 발견의 재미가 좋다는 반응",
        "evidence_summary": "맵을 돌아다니며 발견하는 재미를 좋게 보는 반응이 많아 탐험 중심 플레이에 잘 맞습니다.",
    },
    "sandbox_freedom": {
        "player_fit": "정해진 길보다 자기 방식으로 노는 플레이를 좋아하는 플레이어",
        "title": "자유도가 큰 샌드박스 플레이",
        "summary": "정답이 없는 자유도가 커서 자기 방식으로 오래 만지는 플레이에 잘 맞습니다.",
        "headline": "자유도가 큰 샌드박스 경험",
        "evidence_title": "자유도가 높다는 반응",
        "evidence_summary": "원하는 방식으로 플레이할 수 있다는 반응이 많아 자율적인 플레이와 잘 맞습니다.",
    },
    "narrative_immersion": {
        "player_fit": "서사와 분위기에 오래 몰입하는 플레이어",
        "title": "세계와 사건에 빨려드는 몰입감",
        "summary": "세계와 사건의 흐름이 강하게 이어져 분위기와 서사를 중시하면 만족도가 높습니다.",
        "headline": "세계와 사건에 빨려드는 몰입감",
        "evidence_title": "세계와 사건에 몰입하게 된다는 반응",
        "evidence_summary": "세계와 사건에 몰입한다는 반응이 많아 분위기와 서사를 중시하는 플레이와 잘 맞습니다.",
    },
    "visual_narrative_immersion": {
        "player_fit": "서사와 감정선에 깊게 몰입하는 플레이어",
        "title": "감정선과 장면 전환이 오래 남는 서사 경험",
        "summary": "감정선과 장면 전환의 여운이 커서 이야기에 깊게 몰입하는 흐름이 강합니다.",
        "headline": "감정선이 오래 남는 서사 몰입",
        "evidence_title": "감정선과 전개가 오래 남는다는 반응",
        "evidence_summary": "감정선과 전개가 오래 남는다는 반응이 많아 이야기에 깊게 몰입하는 쪽에 특히 잘 맞습니다.",
    },
    "build_customization": {
        "player_fit": "세팅과 빌드를 바꿔가며 최적 해를 찾는 플레이어",
        "title": "세팅을 바꿔가며 찾는 빌드 조합",
        "summary": "세팅을 바꿔가며 다른 답을 찾는 과정이 뚜렷해 실험하는 재미가 살아 있습니다.",
        "headline": "세팅과 빌드 실험의 재미",
        "evidence_title": "빌드와 세팅을 바꾸는 재미가 좋다는 반응",
        "evidence_summary": "세팅을 바꾸며 다른 답을 찾는 재미를 좋게 보는 반응이 많아 실험형 플레이와 잘 맞습니다.",
    },
    "long_term_growth": {
        "player_fit": "하루보다 오래 붙잡고 성장 루프를 깊게 파는 플레이어",
        "title": "오래 붙잡게 만드는 성장 루프",
        "summary": "목표를 쌓아가며 오래 붙잡게 만드는 성장 구조가 있어 장기 플레이에 잘 맞습니다.",
        "headline": "오래 붙잡게 만드는 성장 루프",
        "evidence_title": "성장 루프가 오래 붙잡는다는 반응",
        "evidence_summary": "장기 성장 동기가 분명하다는 반응이 많아 오래 파는 플레이와 잘 맞습니다.",
    },
    "management_tactics": {
        "player_fit": "전술과 운영 판단을 오래 다듬는 플레이어",
        "title": "전술과 운영 판단의 깊이",
        "summary": "전술과 운영 판단을 계속 다듬는 재미가 있어 오래 붙잡는 운영형 플레이에 잘 맞습니다.",
        "headline": "전술과 운영 판단의 깊이",
        "evidence_title": "전술과 운영 판단의 재미가 크다는 반응",
        "evidence_summary": "전술과 운영 판단의 재미를 말하는 반응이 많아 오래 다듬는 플레이와 잘 맞습니다.",
    },
    "life_sim_routine": {
        "player_fit": "하루 루틴을 천천히 쌓아가는 플레이어",
        "title": "하루하루 쌓아가는 생활 루프",
        "summary": "하루 루틴을 차분히 이어가는 흐름이 안정적이라 천천히 만지는 플레이와 잘 맞습니다.",
        "headline": "차분히 쌓이는 생활 루프",
        "evidence_title": "생활 루프를 쌓는 재미가 좋다는 반응",
        "evidence_summary": "생활 루프를 차근차근 이어가는 재미를 좋게 보는 반응이 많아 꾸준한 플레이와 잘 맞습니다.",
    },
    "cozy_growth_loop": {
        "player_fit": "부담 없이 차근차근 키워가는 생활 루프를 좋아하는 플레이어",
        "title": "편안하게 이어지는 성장 루프",
        "summary": "부담 없이 조금씩 쌓아가는 성장 흐름이 강해 편안한 장기 플레이에 잘 맞습니다.",
        "headline": "편안하게 이어지는 성장 루프",
        "evidence_title": "편안한 성장 루프가 좋다는 반응",
        "evidence_summary": "편안하게 이어지는 성장 흐름을 좋게 보는 반응이 많아 느긋한 플레이에 잘 맞습니다.",
    },
    "city_builder_management": {
        "player_fit": "도시를 키우며 흐름을 다듬는 운영형 플레이어",
        "title": "도시 흐름을 다듬는 운영의 재미",
        "summary": "도시의 흐름을 조정하고 균형을 맞추는 재미가 분명해 운영형 플레이에 잘 맞습니다.",
        "headline": "도시를 다듬는 운영의 재미",
        "evidence_title": "도시를 다듬고 확장하는 재미가 좋다는 반응",
        "evidence_summary": "도시 운영의 흐름을 만지는 재미를 말하는 반응이 많아 균형과 확장을 다듬는 플레이와 잘 맞습니다.",
    },
    "automation_factory_optimization": {
        "player_fit": "자동화 라인을 다듬으며 효율을 올리는 플레이어",
        "title": "병목을 풀며 확장하는 자동화 설계",
        "summary": "병목을 풀고 생산 라인을 확장하는 과정이 재미의 중심이라 최적화를 즐길수록 만족도가 높습니다.",
        "headline": "자동화와 최적화의 재미",
        "evidence_title": "자동화와 병목 해소의 재미가 분명하다는 반응",
        "evidence_summary": "자동화와 효율 설계를 좋게 보는 반응이 많아 병목을 풀고 확장하는 과정이 핵심 재미로 읽힙니다.",
    },
    "looter_shooter_progression": {
        "player_fit": "장비와 빌드를 오래 다듬는 플레이어",
        "title": "장비와 빌드를 쌓는 성장 루프",
        "summary": "장비를 파밍하고 빌드를 확장하는 과정이 분명한 성장 동기로 이어져 오래 붙잡기 좋습니다.",
        "headline": "장비 파밍과 성장 루프",
        "evidence_title": "장비 파밍과 성장 루프가 오래 붙잡는다는 반응",
        "evidence_summary": "장비 파밍과 성장 루프를 좋게 보는 반응이 많아 반복 임무 속에서 강해지는 구조를 즐기면 잘 맞습니다.",
    },
    "cooperative_live_service_shooter": {
        "player_fit": "분대 호흡을 맞추며 임무를 푸는 플레이어",
        "title": "분대 호흡이 살아나는 협동 임무",
        "summary": "분대 호흡과 임무 수행이 맞물릴수록 협동 전투의 만족감이 크게 살아납니다.",
        "headline": "분대 협동과 임무 수행",
        "evidence_title": "분대 협동과 임무 수행의 재미가 크다는 반응",
        "evidence_summary": "분대 협동과 임무 수행의 재미를 말하는 반응이 많아 역할을 나눠 함께 푸는 플레이와 잘 맞습니다.",
    },
    "narrative_openworld_immersion": {
        "player_fit": "사건과 인물의 여운을 오래 가져가는 플레이어",
        "title": "사건과 인물이 오래 남는 서사 경험",
        "summary": "사건과 인물의 여운이 길게 남아 세계를 천천히 체험하는 플레이와 잘 맞습니다.",
        "headline": "사건과 인물의 여운",
        "evidence_title": "사건과 인물의 여운이 오래 남는다는 반응",
        "evidence_summary": "사건과 인물의 여운을 말하는 반응이 많아 서사와 세계를 천천히 체험하는 플레이에 잘 맞습니다.",
    },
    "life_sim_social_loop": {
        "player_fit": "생활 루프를 천천히 쌓아가는 플레이어",
        "title": "생활 루프와 꾸미기의 자유도",
        "summary": "생활 루프와 꾸미기, 관계를 차근차근 쌓아가는 흐름이 안정적으로 이어집니다.",
        "headline": "생활과 관계를 쌓는 재미",
        "evidence_title": "생활 루프와 관계 시뮬레이션이 좋다는 반응",
        "evidence_summary": "생활 루프와 관계 시뮬레이션을 좋게 보는 반응이 많아 일상을 천천히 쌓아가는 플레이에 잘 맞습니다.",
    },
    "deckbuilding_run_planning": {
        "player_fit": "한 판마다 덱 조합과 경로 선택을 즐기는 플레이어",
        "title": "카드 선택과 경로 판단이 살아 있는 한 판 루프",
        "summary": "카드 선택과 경로 판단이 매번 다른 계획을 만들며 한 판의 설계 재미가 또렷합니다.",
        "headline": "덱 구성과 한 판 설계의 재미",
        "evidence_title": "카드 선택과 경로 판단의 재미가 크다는 반응",
        "evidence_summary": "카드 선택과 경로 판단의 재미를 말하는 반응이 많아 계획을 세워 굴리는 플레이와 잘 맞습니다.",
    },
    "turn_based_tactical_pressure": {
        "player_fit": "한 턴의 판단 무게를 즐기는 전술형 플레이어",
        "title": "한 턴의 선택이 무거운 전술 압박",
        "summary": "한 번의 선택이 다음 턴 결과에 크게 이어져 전술 판단의 무게가 분명하게 살아 있습니다.",
        "headline": "한 턴 판단의 압박감",
        "evidence_title": "한 턴의 선택이 긴장감을 만든다는 반응",
        "evidence_summary": "한 턴의 선택이 크게 작용한다는 반응이 많아 전술 판단의 압박을 즐기면 잘 맞습니다.",
    },
    "teamplay_synergy": {
        "player_fit": "팀원과 호흡을 맞추는 플레이를 중요하게 보는 플레이어",
        "title": "팀 합이 맞을 때 살아나는 멀티플레이 흐름",
        "summary": "팀 합이 맞을수록 만족도가 올라가 협동 호흡을 맞추는 플레이에 잘 맞습니다.",
        "headline": "팀 합이 살아나는 멀티플레이 흐름",
        "evidence_title": "팀 합의 재미가 크다는 반응",
        "evidence_summary": "팀 합이 맞을 때 만족도가 올라간다는 반응이 많아 함께 맞춰가는 플레이에 잘 맞습니다.",
    },
    "visual_atmosphere": {
        "player_fit": "배경과 연출이 만드는 분위기를 중요하게 보는 플레이어",
        "title": "비주얼과 분위기를 오래 붙잡는 연출",
        "summary": "비주얼과 연출이 만든 분위기가 길게 남아 화면과 감각을 즐기기 좋습니다.",
        "headline": "비주얼과 분위기 연출",
        "evidence_title": "비주얼과 분위기가 몰입을 만든다는 반응",
        "evidence_summary": "비주얼과 연출의 분위기를 좋게 보는 반응이 많아 장면과 감각을 중시하면 만족도가 높습니다.",
    },
    "core_play_mastery": {
        "player_fit": "플레이 흐름이 점점 또렷해지는 재미를 좋아하는 플레이어",
        "title": "플레이 흐름의 안정감",
        "summary": "기본 플레이 흐름이 안정적으로 잡혀 익숙해질수록 리듬이 또렷해지는 편입니다.",
        "headline": "플레이 흐름의 안정감",
        "evidence_title": "플레이 흐름이 안정적으로 잡힌다는 반응",
        "evidence_summary": "플레이 흐름이 안정적으로 잡힌다는 반응이 많아 익숙해질수록 리듬을 타기 좋은 편입니다.",
    },
}


NEGATIVE_BUNDLES: dict[str, dict[str, str]] = {
    "matchmaking_variance": {
        "player_fit": "매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어",
        "title": "매칭과 서버 상태에 따라 체감이 흔들리는 구간",
        "summary": "매칭과 서버 상태가 흔들리면 한 판의 완성도가 크게 달라질 수 있습니다.",
        "headline": "매칭과 서버 상태 변화",
        "evidence_title": "매칭과 서버 상태가 체감을 흔든다는 반응",
        "evidence_summary": "매칭과 서버 상태를 문제로 보는 반응이 있어 한 판의 안정성이 상황에 따라 갈릴 수 있습니다.",
    },
    "stability_interruptions": {
        "player_fit": "진행 중 오류나 끊김을 거의 허용하지 않는 플레이어",
        "title": "예상치 못한 오류가 흐름을 끊는 구간",
        "summary": "예상치 못한 오류가 나오면 플레이 흐름과 몰입이 크게 끊길 수 있습니다.",
        "headline": "오류와 끊김 리스크",
        "evidence_title": "오류와 끊김이 흐름을 끊는다는 반응",
        "evidence_summary": "오류와 끊김을 지적하는 반응이 이어져 흐름이 끊기는 상황은 감수할 필요가 있습니다.",
    },
    "performance_instability": {
        "player_fit": "프레임과 반응성에 민감한 플레이어",
        "title": "프레임과 반응성이 흔들리는 구간",
        "summary": "프레임과 반응성이 흔들리면 조작 감각과 플레이 리듬이 함께 무너질 수 있습니다.",
        "headline": "프레임과 반응성 변수",
        "evidence_title": "프레임과 반응성이 흔들린다는 반응",
        "evidence_summary": "프레임과 반응성 문제를 지적하는 반응이 이어져 기술 안정성에 민감하면 거슬릴 수 있습니다.",
    },
    "onboarding_friction": {
        "player_fit": "처음부터 빠르게 적응하고 뛰어들고 싶은 플레이어",
        "title": "초반 적응에 시간이 필요한 구간",
        "summary": "시스템과 조작을 익히기까지 시간이 걸려 빠른 진입을 원하면 답답하게 느껴질 수 있습니다.",
        "headline": "초반 적응 부담",
        "evidence_title": "초반 적응이 답답하다는 반응",
        "evidence_summary": "초반 적응이 느리다는 반응이 있어 바로 손에 붙는 경험을 원하면 답답함이 먼저 올 수 있습니다.",
    },
    "repetition_fatigue": {
        "player_fit": "같은 흐름이 길어지면 피로를 크게 느끼는 플레이어",
        "title": "반복 구간이 길어질수록 피로가 커지는 부분",
        "summary": "익숙해진 뒤에는 새로움보다 반복감이 먼저 느껴질 수 있습니다.",
        "headline": "반복 피로가 쌓이는 구간",
        "evidence_title": "반복감이 피로로 이어진다는 반응",
        "evidence_summary": "반복감이 피로로 이어진다는 반응이 있어 새로움이 빨리 줄어드는 구간은 감수해야 할 수 있습니다.",
    },
    "price_sensitivity": {
        "player_fit": "비용 대비 만족을 꼼꼼하게 따지는 플레이어",
        "title": "가격 대비 만족이 갈릴 수 있는 부분",
        "summary": "가격 부담이 있으면 기대만큼 만족하지 못했다는 반응도 함께 나올 수 있습니다.",
        "headline": "가격 대비 만족도 변수",
        "evidence_title": "가격 대비 만족이 갈린다는 반응",
        "evidence_summary": "가격 대비 만족을 지적하는 반응이 있어 비용 대비 만족을 꼼꼼히 보면 고민이 필요할 수 있습니다.",
    },
    "teamplay_stress": {
        "player_fit": "팀플레이 소통 피로를 크게 느끼는 플레이어",
        "title": "팀플레이 피로가 커질 수 있는 구간",
        "summary": "팀 호흡이 맞지 않으면 게임 자체보다 소통 피로가 먼저 커질 수 있습니다.",
        "headline": "팀플레이 피로",
        "evidence_title": "소통과 팀 합의 피로가 크다는 반응",
        "evidence_summary": "소통과 팀 합의 피로를 말하는 반응이 있어 함께하는 과정 자체가 부담이 될 수 있습니다.",
    },
    "balance_swings": {
        "player_fit": "밸런스 변화에 민감하게 반응하는 플레이어",
        "title": "밸런스 변화에 따라 체감이 흔들리는 구간",
        "summary": "밸런스 변화가 직접적인 플레이 감각 차이로 이어질 수 있습니다.",
        "headline": "밸런스 변화 변수",
        "evidence_title": "밸런스 변화가 체감을 흔든다는 반응",
        "evidence_summary": "밸런스 변화에 민감한 반응이 이어져 메타 변화가 크게 거슬릴 수 있습니다.",
    },
    "save_safety": {
        "player_fit": "저장과 진행 안정성을 특히 중요하게 보는 플레이어",
        "title": "저장과 진행 안정성이 불안한 구간",
        "summary": "저장과 진행 안정성이 흔들리면 성취감보다 불안이 먼저 커질 수 있습니다.",
        "headline": "저장과 진행 안정성 변수",
        "evidence_title": "진행 안정성이 불안하다는 반응",
        "evidence_summary": "저장과 진행 안정성을 걱정하는 반응이 있어 누적 플레이를 중요하게 보면 부담이 될 수 있습니다.",
    },
    "translation_friction": {
        "player_fit": "텍스트와 번역 품질에 민감한 플레이어",
        "title": "텍스트와 번역이 몰입을 끊는 부분",
        "summary": "텍스트와 번역 흐름이 매끄럽지 않으면 서사와 설명이 자주 끊길 수 있습니다.",
        "headline": "텍스트 전달의 거슬림",
        "evidence_title": "텍스트와 번역이 거슬린다는 반응",
        "evidence_summary": "텍스트와 번역 흐름이 거슬린다는 반응이 있어 읽는 경험을 중시하면 자주 눈에 밟힐 수 있습니다.",
    },
    "control_friction": {
        "player_fit": "조작과 인터페이스 적응 스트레스를 크게 받는 플레이어",
        "title": "조작 적응이 답답하게 느껴지는 구간",
        "summary": "조작과 인터페이스 적응에 시간이 걸리면 플레이보다 답답함이 먼저 커질 수 있습니다.",
        "headline": "조작 적응 부담",
        "evidence_title": "조작 적응이 답답하다는 반응",
        "evidence_summary": "조작과 인터페이스 적응이 느리다는 반응이 있어 처음부터 부드러운 조작감을 원하면 거슬릴 수 있습니다.",
    },
}


def _genre_flags(genres: list[str] | None) -> dict[str, bool]:
    blob = _genre_blob(genres)
    return {key: _contains_any(blob, hints) for key, hints in GENRE_HINTS.items()}


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
        if flags["visual_novel"]:
            if aspect_key in {"story", "localization"}:
                return "translation_friction"
            if aspect_key in {"performance", "bugs", "matchmaking", "multiplayer", "gameplay", "content_depth", "controls"}:
                return "stability_interruptions"
        if flags["life_sim"]:
            if aspect_key in {"gameplay", "story", "content_depth", "customization"}:
                return "repetition_fatigue"
            if aspect_key in {"controls", "building_ux"}:
                return "control_friction"
            if aspect_key == "performance":
                return "performance_instability"
        if flags["narrative_openworld"]:
            if aspect_key in {"matchmaking", "multiplayer", "story", "gameplay", "content_depth"}:
                return "repetition_fatigue"
        if flags["coop_live_service"]:
            if aspect_key in {"matchmaking", "multiplayer"}:
                return "teamplay_stress"
            if aspect_key in {"gameplay", "content_depth", "bugs"}:
                return "stability_interruptions"
        if flags["looter_shooter"]:
            if aspect_key in {"matchmaking", "multiplayer"}:
                return "matchmaking_variance"
            if aspect_key in {"gameplay", "content_depth", "story", "customization"}:
                return "repetition_fatigue"
        if flags["automation"] and aspect_key in {"matchmaking", "multiplayer"}:
            return "control_friction"
        if flags["deckbuilder"] and aspect_key in {"story", "gameplay", "multiplayer", "matchmaking"}:
            return "repetition_fatigue"
        if flags["turn_based"] and aspect_key in {"story", "gameplay"}:
            return "onboarding_friction"
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

    if flags["life_sim"] or _contains_any(theme_blob, THEME_HINTS["life_sim_social_loop"]):
        if aspect_key in {"gameplay", "content_depth", "customization", "story", "building_ux"}:
            return "life_sim_social_loop"

    if flags["city_builder"] or _contains_any(theme_blob, THEME_HINTS["city_builder_management"]):
        if aspect_key in {"gameplay", "content_depth", "building_ux"}:
            return "city_builder_management"

    if flags["automation"] or _contains_any(theme_blob, THEME_HINTS["automation_factory_optimization"]):
        if aspect_key in {"gameplay", "content_depth", "building_ux"}:
            return "automation_factory_optimization"

    if flags["coop_live_service"] or _contains_any(theme_blob, THEME_HINTS["cooperative_live_service_shooter"]):
        if aspect_key in {"gameplay", "multiplayer", "content_depth", "customization"}:
            return "cooperative_live_service_shooter"

    if flags["looter_shooter"] or _contains_any(theme_blob, THEME_HINTS["looter_shooter_progression"]):
        if aspect_key in {"gameplay", "content_depth", "customization", "story"}:
            return "cooperative_live_service_shooter" if flags["coop_live_service"] else "looter_shooter_progression"
        if aspect_key == "multiplayer":
            return "cooperative_live_service_shooter" if (flags["coop"] or flags["coop_live_service"]) else "looter_shooter_progression"

    if flags["narrative_openworld"] or _contains_any(theme_blob, THEME_HINTS["narrative_openworld_immersion"]):
        if aspect_key in {"story", "gameplay", "content_depth", "graphics", "sound"}:
            return "narrative_openworld_immersion"

    if flags["deckbuilder"] or _contains_any(theme_blob, THEME_HINTS["deckbuilding_run_planning"]):
        if aspect_key in {"gameplay", "content_depth", "customization"}:
            return "deckbuilding_run_planning"

    if (flags["turn_based"] or _contains_any(theme_blob, THEME_HINTS["turn_based_tactical_pressure"])) and aspect_key in {
        "gameplay",
        "content_depth",
        "difficulty",
    }:
        return "turn_based_tactical_pressure"

    if flags["deckbuilder"] and aspect_key in {"story", "gameplay", "content_depth", "customization"}:
        return "deckbuilding_run_planning"

    if flags["automation"] and aspect_key in {"story", "gameplay", "content_depth", "building_ux", "multiplayer"}:
        return "automation_factory_optimization"

    if flags["turn_based"] and aspect_key in {"story", "gameplay", "content_depth", "difficulty"}:
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
        if flags["city_builder"]:
            return "city_builder_management"
        if flags["automation"]:
            return "automation_factory_optimization"
        if flags["coop_live_service"]:
            return "cooperative_live_service_shooter"
        if flags["looter_shooter"]:
            return "cooperative_live_service_shooter" if flags["coop_live_service"] else "looter_shooter_progression"
        if flags["narrative_openworld"]:
            return "narrative_openworld_immersion"
        if flags["deckbuilder"]:
            return "deckbuilding_run_planning"
        if flags["turn_based"]:
            return "turn_based_tactical_pressure"
        if flags["management"] or flags["sports"] or flags["strategy"]:
            return "management_tactics"
        if flags["cozy"]:
            return "cozy_growth_loop"
        if flags["survival"]:
            return "survival_base_building"
        return "long_term_growth"

    if aspect_key == "multiplayer":
        if flags["coop_live_service"]:
            return "cooperative_live_service_shooter"
        if flags["looter_shooter"]:
            return "cooperative_live_service_shooter" if flags["coop_live_service"] else "looter_shooter_progression"
        if flags["automation"]:
            return "automation_factory_optimization"
        if flags["coop"]:
            return "cooperative_mission_loop"
        if flags["battle_royale"] or flags["shooter"]:
            return "openworld_pvp_tension"
        return "teamplay_synergy"

    if aspect_key in {"building_ux"}:
        if flags["life_sim"]:
            return "life_sim_social_loop"
        if flags["city_builder"]:
            return "city_builder_management"
        if flags["automation"]:
            return "automation_factory_optimization"
        return "control_friction"

    if aspect_key == "gameplay":
        if flags["life_sim"]:
            return "life_sim_social_loop"
        if flags["coop_live_service"]:
            return "cooperative_live_service_shooter"
        if flags["looter_shooter"]:
            return "cooperative_live_service_shooter" if flags["coop_live_service"] else "looter_shooter_progression"
        if flags["narrative_openworld"]:
            return "narrative_openworld_immersion"
        if flags["deckbuilder"]:
            return "deckbuilding_run_planning"
        if flags["automation"]:
            return "automation_factory_optimization"
        if flags["turn_based"]:
            return "turn_based_tactical_pressure"
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
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"]["player_fit"]
        if negative
        else POSITIVE_BUNDLES["core_play_mastery"]["player_fit"],
    )["player_fit"]


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
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"] if negative else POSITIVE_BUNDLES["core_play_mastery"],
    )["title"]


def build_experience_summary(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"] if negative else POSITIVE_BUNDLES["core_play_mastery"],
    )["summary"]


def build_headline_theme(
    *,
    aspect: str,
    theme: str | None,
    genres: list[str] | None,
    negative: bool,
) -> str:
    subtype = infer_copy_subtype(aspect=aspect, theme=theme, genres=genres, negative=negative)
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"] if negative else POSITIVE_BUNDLES["core_play_mastery"],
    )["headline"]


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
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"] if negative else POSITIVE_BUNDLES["core_play_mastery"],
    )["evidence_title"]


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
    mapping = NEGATIVE_BUNDLES if negative else POSITIVE_BUNDLES
    return mapping.get(
        subtype,
        NEGATIVE_BUNDLES["stability_interruptions"] if negative else POSITIVE_BUNDLES["core_play_mastery"],
    )["evidence_summary"]


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


def _looks_like_internal_theme(theme: str | None) -> bool:
    value = str(theme or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if "/" in value:
        return True
    bad_fragments = ("리스크", "사인", "실제 플레이 만족", "체감", "반응", "경험이다")
    return any(fragment in lowered for fragment in bad_fragments) or len(value) <= 4
