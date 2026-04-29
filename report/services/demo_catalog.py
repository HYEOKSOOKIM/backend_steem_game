"""Demo game catalog helpers for read-only serving scope."""

from __future__ import annotations

import json
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
    seen: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        appid = item.get("appid")
        if not isinstance(appid, int) or appid in seen:
            continue
        seen.add(appid)
        normalized.append(
            {
                "appid": appid,
                "name": str(item.get("name") or f"appid-{appid}"),
                "enabled_for_demo": bool(item.get("enabled_for_demo", True)),
            }
        )

    if not normalized:
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
                {
                    "appid": appid,
                    "name": str(item.get("name") or f"appid-{appid}"),
                    "enabled_for_demo": bool(item.get("enabled_for_demo", True)),
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def upsert_demo_game(catalog_path: str | Path, *, appid: int, name: str, enabled_for_demo: bool = True) -> Path:
    """Insert or update one catalog entry."""
    games = load_demo_games(catalog_path)
    updated = False
    for item in games:
        if int(item.get("appid", -1)) != appid:
            continue
        item["name"] = str(name or item.get("name") or f"appid-{appid}")
        item["enabled_for_demo"] = bool(enabled_for_demo)
        updated = True
        break
    if not updated:
        games.append(
            {
                "appid": int(appid),
                "name": str(name or f"appid-{appid}"),
                "enabled_for_demo": bool(enabled_for_demo),
            }
        )
    games.sort(key=lambda item: int(item.get("appid", 0)))
    return save_demo_games(catalog_path, games)


def remove_demo_games(catalog_path: str | Path, appids: set[int]) -> Path:
    """Remove multiple appids from the public demo catalog."""
    games = load_demo_games(catalog_path)
    kept = [item for item in games if int(item.get("appid", -1)) not in appids]
    return save_demo_games(catalog_path, kept)
