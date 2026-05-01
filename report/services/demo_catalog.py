"""Demo game catalog helpers for read-only serving scope."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_DEMO_GAMES: list[dict[str, Any]] = [
    {"appid": 2456740, "name": "인조이", "enabled_for_demo": True},
    {"appid": 1049590, "name": "이터널 리턴", "enabled_for_demo": True},
    {"appid": 252490, "name": "러스트", "enabled_for_demo": True},
    {"appid": 230410, "name": "워프레임", "enabled_for_demo": True},
    {"appid": 381210, "name": "데드 바이 데이라이트", "enabled_for_demo": True},
    {"appid": 413150, "name": "스타듀 밸리", "enabled_for_demo": True},
    {"appid": 292030, "name": "위쳐 3 와일드 헌트", "enabled_for_demo": True},
    {"appid": 1086940, "name": "발더스 게이트 3", "enabled_for_demo": True},
]

MANUAL_DEMO_GAME_OVERRIDES: dict[int, dict[str, Any]] = {
    440: {
        "name_en": "Team Fortress 2",
        "name_ko": "팀 포트리스 2",
        "aliases": ["팀포", "팀포2", "TF2"],
    },
    550: {
        "name_en": "Left 4 Dead 2",
        "name_ko": "레프트 4 데드 2",
        "aliases": ["레프트4데드2", "레포데2", "L4D2"],
    },
    570: {
        "name_en": "Dota 2",
        "name_ko": "도타 2",
        "aliases": ["도타", "도타2", "Dota2"],
    },
    620: {
        "name_en": "Portal 2",
        "name_ko": "포탈 2",
        "aliases": ["포탈", "포탈2", "Portal2"],
    },
    730: {
        "name_en": "Counter-Strike 2",
        "name_ko": "카운터 스트라이크 2",
        "aliases": ["카스", "카스2", "카운터스트라이크2", "CS2"],
    },
    105600: {
        "name_en": "Terraria",
        "name_ko": "테라리아",
        "aliases": ["테라"],
    },
    108600: {
        "name_en": "Project Zomboid",
        "name_ko": "프로젝트 좀보이드",
        "aliases": ["프좀", "좀보이드", "PZ"],
    },
    230410: {
        "name_en": "Warframe",
        "name_ko": "워프레임",
        "aliases": ["워프"],
    },
    236850: {
        "name_en": "Europa Universalis IV",
        "name_ko": "유로파 유니버설리스 4",
        "aliases": ["유로파4", "유로파", "EU4"],
    },
    252490: {
        "name_en": "Rust",
        "name_ko": "러스트",
        "aliases": [],
    },
    294100: {
        "name_en": "RimWorld",
        "name_ko": "림월드",
        "aliases": ["림월"],
    },
    359550: {
        "name_en": "Tom Clancy's Rainbow Six Siege",
        "name_ko": "레인보우 식스 시즈",
        "aliases": ["레식", "레식시즈", "R6", "R6S"],
    },
    367520: {
        "name_en": "Hollow Knight",
        "name_ko": "할로우 나이트",
        "aliases": ["할나", "할나이트", "HK"],
    },
    394360: {
        "name_en": "Hearts of Iron IV",
        "name_ko": "하츠 오브 아이언 4",
        "aliases": ["호이4", "하오아4", "HOI4"],
    },
    413150: {
        "name_en": "Stardew Valley",
        "name_ko": "스타듀 밸리",
        "aliases": ["스타듀밸리", "스타듀", "Stardew", "SV"],
    },
    427520: {
        "name_en": "Factorio",
        "name_ko": "팩토리오",
        "aliases": ["팩토"],
    },
    526870: {
        "name_en": "Satisfactory",
        "name_ko": "새티스팩토리",
        "aliases": ["새팩", "새티", "Satis"],
    },
    553850: {
        "name_en": "HELLDIVERS 2",
        "name_ko": "헬다이버즈 2",
        "aliases": ["헬다이버즈2", "헬다2", "헬다", "HD2"],
    },
    739630: {
        "name_en": "Phasmophobia",
        "name_ko": "파스모포비아",
        "aliases": ["파스모", "파스", "Phasmo"],
    },
    814380: {
        "name_en": "Sekiro: Shadows Die Twice",
        "name_ko": "세키로: 섀도우 다이 트와이스",
        "aliases": ["세키로", "세키", "Sekiro"],
    },
    892970: {
        "name_en": "Valheim",
        "name_ko": "발하임",
        "aliases": [],
    },
    949230: {
        "name_en": "Cities: Skylines II",
        "name_ko": "시티즈: 스카이라인 2",
        "aliases": [
            "시티즈 스카이라인",
            "시티즈 스카이라인 2",
            "시티즈2",
            "시티즈",
            "시스카",
            "시스카2",
            "Cities Skylines 2",
        ],
    },
    1085660: {
        "name_en": "Destiny 2",
        "name_ko": "데스티니 가디언즈",
        "aliases": ["데스티니2", "데가", "데스가", "Destiny"],
    },
    1145350: {
        "name_en": "Hades II",
        "name_ko": "하데스 2",
        "aliases": ["하데스2", "Hades 2"],
    },
    1158310: {
        "name_en": "Crusader Kings III",
        "name_ko": "크루세이더 킹즈 3",
        "aliases": ["크킹3", "CK3", "Crusader Kings 3"],
    },
    1172470: {
        "name_en": "Apex Legends",
        "name_ko": "에이펙스 레전드",
        "aliases": ["에펙", "에이펙스", "Apex"],
    },
    1364780: {
        "name_en": "Street Fighter 6",
        "name_ko": "스트리트 파이터 6",
        "aliases": ["스파", "스파6", "SF6", "Street Fighter VI"],
    },
    1623730: {
        "name_en": "Palworld",
        "name_ko": "팰월드",
        "aliases": ["팰", "Pal"],
    },
    1778820: {
        "name_en": "TEKKEN 8",
        "name_ko": "철권 8",
        "aliases": ["철권", "철권8", "Tekken 8", "Tekken8"],
    },
    2000950: {
        "name_en": "Call of Duty",
        "name_ko": "콜 오브 듀티",
        "aliases": ["콜옵", "콜오브듀티", "COD"],
    },
    2054970: {
        "name_en": "Dragon's Dogma 2",
        "name_ko": "드래곤즈 도그마 2",
        "aliases": ["드도2", "드래곤즈도그마2"],
    },
    2246340: {
        "name_en": "Monster Hunter Wilds",
        "name_ko": "몬스터 헌터 와일즈",
        "aliases": ["몬헌 와일즈", "몬헌와일즈", "와일즈", "MHWilds"],
    },
    2357570: {
        "name_en": "Overwatch 2",
        "name_ko": "오버워치 2",
        "aliases": ["오버워치", "옵치", "옵치2", "OW2"],
    },
    2483190: {
        "name_en": "Forza Horizon",
        "name_ko": "포르자 호라이즌",
        "aliases": ["포호", "포르자", "Forza"],
    },
    2537590: {
        "name_en": "Microsoft Flight Simulator 2024",
        "name_ko": "마이크로소프트 플라이트 시뮬레이터 2024",
        "aliases": ["플심", "플심2024", "MSFS2024", "Flight Simulator 2024"],
    },
    2909400: {
        "name_en": "FINAL FANTASY",
        "name_ko": "파이널 판타지",
        "aliases": ["파판", "파이널판타지", "FF", "Final Fantasy"],
    },
    3405690: {
        "name_en": "EA SPORTS FC 26",
        "name_ko": "EA SPORTS FC 26",
        "aliases": ["피파26", "FC26", "EAFC26", "FIFA26", "피파"],
    },
}


def _alias_key(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return ""
    compact = re.sub(r"[^0-9a-z가-힣]+", "", normalized)
    return compact or normalized


def _push_alias(target: list[str], seen: set[str], value: Any) -> None:
    alias = str(value or "").strip()
    key = _alias_key(alias)
    if not alias or not key or key in seen:
        return
    target.append(alias)
    seen.add(key)


def _normalize_aliases(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    aliases: list[str] = []
    seen: set[str] = set()
    for item in value:
        alias = str(item or "").strip()
        key = _alias_key(alias)
        if not alias or key in seen:
            continue
        aliases.append(alias)
        seen.add(key)
    return aliases


def _apply_manual_override(entry: dict[str, Any]) -> dict[str, Any]:
    appid = entry.get("appid")
    if not isinstance(appid, int):
        return entry

    override = MANUAL_DEMO_GAME_OVERRIDES.get(appid)
    if not isinstance(override, dict):
        return entry

    merged = dict(entry)
    if override.get("name_en"):
        merged["name_en"] = str(override["name_en"]).strip()
    if override.get("name_ko"):
        merged["name_ko"] = str(override["name_ko"]).strip()

    merged_aliases = _normalize_aliases(
        [*(merged.get("aliases") or []), *(override.get("aliases") or [])]
    )
    merged["aliases"] = merged_aliases
    return merged


def _split_parenthetical_variants(name: str) -> list[str]:
    text = str(name or "").strip()
    if not text:
        return []

    variants = [text]
    match = re.match(r"^(?P<outer>.*?)\s*\((?P<inner>.+?)\)\s*$", text)
    if match:
        outer = match.group("outer").strip()
        inner = match.group("inner").strip()
        if outer:
            variants.append(outer)
        if inner:
            variants.append(inner)
    return variants


def _roman_to_arabic_token(token: str) -> str | None:
    mapping = {
        "i": "1",
        "ii": "2",
        "iii": "3",
        "iv": "4",
        "v": "5",
        "vi": "6",
        "vii": "7",
        "viii": "8",
        "ix": "9",
        "x": "10",
    }
    return mapping.get(token.casefold())


def _arabic_to_roman_token(token: str) -> str | None:
    mapping = {
        "1": "I",
        "2": "II",
        "3": "III",
        "4": "IV",
        "5": "V",
        "6": "VI",
        "7": "VII",
        "8": "VIII",
        "9": "IX",
        "10": "X",
    }
    return mapping.get(token)


def _english_token_variants(name: str) -> list[str]:
    text = str(name or "").strip()
    if not text:
        return []

    variants: list[str] = []
    cleaned = re.sub(r"(?i)'s\b", "", text)
    tokens = re.findall(r"[A-Za-z0-9]+", cleaned)
    if not tokens:
        return variants

    if len(tokens) < 2:
        return variants

    roman_swapped = []
    arabic_swapped = []
    changed_roman = False
    changed_arabic = False
    for token in tokens:
        roman = _roman_to_arabic_token(token)
        arabic = _arabic_to_roman_token(token)
        if roman:
            roman_swapped.append(roman)
            changed_roman = True
        else:
            roman_swapped.append(token)
        if arabic:
            arabic_swapped.append(arabic)
            changed_arabic = True
        else:
            arabic_swapped.append(token)

    if changed_roman:
        variants.append(" ".join(roman_swapped))
    if changed_arabic:
        variants.append(" ".join(arabic_swapped))

    significant_tokens = [
        token for token in tokens
        if token.casefold() not in {"the", "of", "and", "a", "an", "to"}
    ]
    if 2 <= len(significant_tokens) <= 5:
        acronym = "".join(
            token if token.isdigit() else token[0].upper()
            for token in significant_tokens
        )
        if len(acronym) >= 2:
            variants.append(acronym)

    return variants


def _name_variants(name: str) -> list[str]:
    text = str(name or "").strip()
    if not text:
        return []

    variants: list[str] = []
    seen: set[str] = set()
    for base in _split_parenthetical_variants(text):
        _push_alias(variants, seen, base)
        compact = re.sub(r"\s+", "", base)
        if compact != base:
            _push_alias(variants, seen, compact)

        normalized_punct = re.sub(r"[:'’!,.®™-]+", " ", base)
        normalized_punct = re.sub(r"\s+", " ", normalized_punct).strip()
        if normalized_punct and normalized_punct != base:
            _push_alias(variants, seen, normalized_punct)
            _push_alias(variants, seen, normalized_punct.replace(" ", ""))

        if ":" in base:
            prefix = base.split(":", 1)[0].strip()
            if prefix:
                _push_alias(variants, seen, prefix)
                _push_alias(variants, seen, prefix.replace(" ", ""))

        suffix_trimmed = re.sub(
            r"\s+(Enhanced|Legacy|Remastered|GOTY Edition|Game of the Year Edition)$",
            "",
            base,
            flags=re.IGNORECASE,
        ).strip()
        if suffix_trimmed and suffix_trimmed != base:
            _push_alias(variants, seen, suffix_trimmed)
            _push_alias(variants, seen, suffix_trimmed.replace(" ", ""))

        for english_variant in _english_token_variants(base):
            _push_alias(variants, seen, english_variant)

    return variants


def generate_demo_game_aliases(
    *,
    name: str | None,
    name_en: str | None = None,
    name_ko: str | None = None,
    existing_aliases: list[str] | None = None,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    for candidate in [
        *(existing_aliases or []),
        *(_name_variants(name_ko or "")),
        *(_name_variants(name_en or "")),
        *(_name_variants(name or "")),
    ]:
        _push_alias(aliases, seen, candidate)

    canonical_texts = {
        str(value or "").strip().casefold()
        for value in [name, name_en, name_ko]
        if str(value or "").strip()
    }
    return [
        alias
        for alias in aliases
        if str(alias or "").strip().casefold() not in canonical_texts
    ]


def load_demo_games(catalog_path: str | Path | None) -> list[dict[str, Any]]:
    """Load predefined demo games from JSON file, fallback to defaults."""
    if catalog_path is None:
        return [dict(item) for item in DEFAULT_DEMO_GAMES]

    path = Path(catalog_path)
    if not path.exists():
        return [dict(item) for item in DEFAULT_DEMO_GAMES]

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("demo catalog must be a list.")

    normalized: list[dict[str, Any]] = []
    explicit_empty_catalog = len(payload) == 0
    seen: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        appid = item.get("appid")
        if not isinstance(appid, int) or appid in seen:
            continue
        seen.add(appid)
        normalized.append(
            _apply_manual_override(
                {
                "appid": appid,
                "name": str(item.get("name") or f"appid-{appid}"),
                "name_en": str(item.get("name_en")).strip() if item.get("name_en") else None,
                "name_ko": str(item.get("name_ko")).strip() if item.get("name_ko") else None,
                "aliases": _normalize_aliases(item.get("aliases")),
                "enabled_for_demo": bool(item.get("enabled_for_demo", True)),
                }
            )
        )

    if not normalized and not explicit_empty_catalog:
        return [dict(item) for item in DEFAULT_DEMO_GAMES]
    return normalized


def build_demo_game_index(games: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Return appid-keyed map for quick allow-list checks."""
    return {
        int(item["appid"]): item
        for item in games
        if item.get("enabled_for_demo", True)
    }


def save_demo_games(catalog_path: str | Path, games: list[dict[str, Any]]) -> Path:
    """Persist normalized demo catalog entries."""
    path = Path(catalog_path)
    normalized = load_demo_games(None)
    if games:
        seen: set[int] = set()
        normalized = []
        for item in games:
            if not isinstance(item, dict):
                continue
            appid = item.get("appid")
            if not isinstance(appid, int) or appid in seen:
                continue
            seen.add(appid)
            normalized.append(
                _apply_manual_override(
                    {
                    "appid": appid,
                    "name": str(item.get("name") or f"appid-{appid}"),
                    "name_en": str(item.get("name_en")).strip() if item.get("name_en") else None,
                    "name_ko": str(item.get("name_ko")).strip() if item.get("name_ko") else None,
                    "aliases": _normalize_aliases(item.get("aliases")),
                    "enabled_for_demo": bool(item.get("enabled_for_demo", True)),
                    }
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def upsert_demo_game(
    catalog_path: str | Path,
    *,
    appid: int,
    name: str,
    name_en: str | None = None,
    name_ko: str | None = None,
    aliases: list[str] | None = None,
    enabled_for_demo: bool = True,
) -> Path:
    """Insert or update one catalog entry."""
    games = load_demo_games(catalog_path)
    updated = False
    for item in games:
        if int(item.get("appid", -1)) != appid:
            continue
        item["name"] = str(name or item.get("name") or f"appid-{appid}")
        item["name_en"] = str(name_en).strip() if name_en else item.get("name_en")
        item["name_ko"] = str(name_ko).strip() if name_ko else item.get("name_ko")
        item["aliases"] = generate_demo_game_aliases(
            name=item.get("name"),
            name_en=item.get("name_en"),
            name_ko=item.get("name_ko"),
            existing_aliases=[*(item.get("aliases") or []), *(aliases or [])],
        )
        manual = MANUAL_DEMO_GAME_OVERRIDES.get(appid, {})
        if manual.get("name_en"):
            item["name_en"] = str(manual["name_en"]).strip()
        if manual.get("name_ko"):
            item["name_ko"] = str(manual["name_ko"]).strip()
        item["aliases"] = _normalize_aliases([*(item.get("aliases") or []), *(manual.get("aliases") or [])])
        item["enabled_for_demo"] = bool(enabled_for_demo)
        updated = True
        break
    if not updated:
        final_name = str(name or f"appid-{appid}")
        games.append(
            _apply_manual_override(
                {
                "appid": int(appid),
                "name": final_name,
                "name_en": str(name_en).strip() if name_en else None,
                "name_ko": str(name_ko).strip() if name_ko else None,
                "aliases": generate_demo_game_aliases(
                    name=final_name,
                    name_en=name_en,
                    name_ko=name_ko,
                    existing_aliases=aliases,
                ),
                "enabled_for_demo": bool(enabled_for_demo),
                }
            )
        )
    games.sort(key=lambda item: int(item.get("appid", 0)))
    return save_demo_games(catalog_path, games)


def remove_demo_games(catalog_path: str | Path, appids: set[int]) -> Path:
    """Remove multiple appids from the public demo catalog."""
    games = load_demo_games(catalog_path)
    kept = [item for item in games if int(item.get("appid", -1)) not in appids]
    return save_demo_games(catalog_path, kept)
