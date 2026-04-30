from __future__ import annotations

import json
import re
from pathlib import Path

_NON_WORD_RE = re.compile(r"[^0-9a-z가-힣]+", flags=re.IGNORECASE)
_CACHE: dict[str, tuple[float, dict[int, list[str]], dict[str, list[int]]]] = {}


def _norm_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _compact_text(text: str) -> str:
    return _NON_WORD_RE.sub("", _norm_text(text))


def _default_alias_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "recommender" / "game_aliases_ko.json"


def _load_aliases(path: Path | None = None) -> tuple[dict[int, list[str]], dict[str, list[int]]]:
    alias_path = path or _default_alias_path()
    if not alias_path.exists():
        return {}, {}

    cache_key = str(alias_path.resolve())
    mtime = float(alias_path.stat().st_mtime)
    cached = _CACHE.get(cache_key)
    if cached is not None and float(cached[0]) == mtime:
        return cached[1], cached[2]

    raw = json.loads(alias_path.read_text(encoding="utf-8"))
    by_app: dict[int, list[str]] = {}
    alias_to_ids: dict[str, list[int]] = {}

    for k, aliases in (raw or {}).items():
        try:
            app_id = int(str(k).strip())
        except Exception:
            continue
        vals = aliases if isinstance(aliases, list) else []
        seen: set[str] = set()
        packed: list[str] = []
        for a in vals:
            t = str(a or "").strip()
            if not t:
                continue
            if t in seen:
                continue
            seen.add(t)
            packed.append(t)
            n = _norm_text(t)
            c = _compact_text(t)
            for key in (n, c):
                if not key:
                    continue
                alias_to_ids.setdefault(key, [])
                if app_id not in alias_to_ids[key]:
                    alias_to_ids[key].append(app_id)
        if packed:
            by_app[app_id] = packed

    _CACHE[cache_key] = (mtime, by_app, alias_to_ids)
    return by_app, alias_to_ids


def lookup_alias_app_ids(text: str, path: Path | None = None) -> list[int]:
    _, alias_to_ids = _load_aliases(path)
    n = _norm_text(text)
    c = _compact_text(text)
    out: list[int] = []
    for key in (n, c):
        if not key:
            continue
        ids = alias_to_ids.get(key, [])
        for app_id in ids:
            if app_id not in out:
                out.append(app_id)
    return out


def get_aliases_by_app_id(path: Path | None = None) -> dict[int, list[str]]:
    by_app, _ = _load_aliases(path)
    return by_app


def norm_text(text: str) -> str:
    return _norm_text(text)


def compact_text(text: str) -> str:
    return _compact_text(text)

