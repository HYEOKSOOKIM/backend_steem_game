from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np

from .chroma_store import query_profiles_from_chroma
from .db import get_connection

_MODEL_CACHE: dict[str, Any] = {}
_SEM_NAME_INDEX_CACHE: dict[str, tuple[list[int], list[str], np.ndarray]] = {}
_NON_WORD_RE = re.compile(r"[^0-9a-z가-힣]+", flags=re.IGNORECASE)
APP_ID_RE = re.compile(r'data-ds-appid="(\d+)"')
STEAM_SEARCH_RESULTS_URL = "https://store.steampowered.com/search/results/"


@dataclass
class ResolvedGame:
    app_id: int
    name: str


def _deserialize_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _norm_token(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _compact_token(text: str) -> str:
    return _NON_WORD_RE.sub("", _norm_token(text))


def _build_query_forms(token: str) -> list[str]:
    base = _norm_token(token)
    compact = _compact_token(token)
    out: list[str] = []
    if base:
        out.append(base)
    if compact and compact not in out:
        out.append(compact)
    # Expand trailing numeric versions: e.g. "gta5" -> "gta 5", "gta v"
    m = re.match(r"^([a-z가-힣]+)(\d+)$", compact)
    if m:
        head, num = m.groups()
        spaced = f"{head} {num}"
        if spaced not in out:
            out.append(spaced)
        roman_map = {
            "1": "i",
            "2": "ii",
            "3": "iii",
            "4": "iv",
            "5": "v",
            "6": "vi",
            "7": "vii",
            "8": "viii",
            "9": "ix",
            "10": "x",
        }
        roman = roman_map.get(num)
        if roman:
            roman_form = f"{head} {roman}"
            if roman_form not in out:
                out.append(roman_form)
    # Include compact variants too (e.g. "gta v" -> "gtav")
    compact_forms = [_compact_token(x) for x in out]
    for c in compact_forms:
        if c and c not in out:
            out.append(c)
    return out


def _name_acronym(text: str) -> str:
    parts = [p for p in _NON_WORD_RE.split(_norm_token(text)) if p]
    if not parts:
        return ""
    return "".join(p[0] for p in parts if p and p[0].isalnum())


def _semantic_name_index(conn, model_name: str) -> tuple[list[int], list[str], np.ndarray]:
    key = model_name
    cached = _SEM_NAME_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    model = _get_model(model_name)
    rows = conn.execute(
        """
        SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
        FROM games g
        JOIN game_profiles p ON p.app_id = g.app_id
        """
    ).fetchall()
    app_ids = [int(r["app_id"]) for r in rows]
    names = [str(r["name"] or "") for r in rows]
    if names:
        vecs = model.encode(
            names,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        mat = np.asarray(vecs, dtype=np.float32)
    else:
        mat = np.zeros((0, 384), dtype=np.float32)
    out = (app_ids, names, mat)
    _SEM_NAME_INDEX_CACHE[key] = out
    return out


def _semantic_resolve_single_game(
    conn,
    token: str,
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    threshold: float = 0.54,
) -> ResolvedGame | None:
    text = (token or "").strip()
    if not text:
        return None
    try:
        model = _get_model(model_name)
        app_ids, names, mat = _semantic_name_index(conn, model_name=model_name)
        if mat.shape[0] == 0:
            return None
        q = model.encode([text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
        sims = np.dot(mat, np.asarray(q, dtype=np.float32))
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim < threshold:
            return None
        return ResolvedGame(app_id=int(app_ids[best_idx]), name=str(names[best_idx]))
    except Exception:
        return None


def _http_get_json(url: str, params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params)}"
    backoff = 0.8
    for attempt in range(retries):
        try:
            with urlopen(full_url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.8
                continue
            raise
        except URLError:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.6
                continue
            raise
    return {}


def _search_steam_app_ids(query: str, limit: int = 10) -> list[int]:
    q = (query or "").strip()
    if not q:
        return []
    try:
        payload = _http_get_json(
            STEAM_SEARCH_RESULTS_URL,
            {
                "query": q,
                "start": 0,
                "count": 25,
                "dynamic_data": "",
                "sort_by": "_ASC",
                "supportedlang": "koreana,english",
                "infinite": 1,
            },
        )
    except Exception:
        return []
    html = str(payload.get("results_html") or "")
    ids: list[int] = []
    for m in APP_ID_RE.findall(html):
        try:
            app_id = int(m)
        except Exception:
            continue
        if app_id not in ids:
            ids.append(app_id)
        if len(ids) >= limit:
            break
    return ids


def _confidence_label(recent_count: int, median_playtime: float) -> str:
    if recent_count >= 80 and median_playtime >= 120:
        return "high"
    if recent_count >= 30:
        return "medium"
    return "low"


def _get_model(model_name: str):
    # Lazy import so lightweight endpoints (e.g. /suggest) stay fast.
    from sentence_transformers import SentenceTransformer

    model = _MODEL_CACHE.get(model_name)
    if model is None:
        local_only_first = (os.getenv("PREFERENCE_FALLBACK_LOCAL_ONLY") or "1").strip() == "1"
        if local_only_first:
            model = SentenceTransformer(model_name, local_files_only=True)
            _MODEL_CACHE[model_name] = model
            return model

        offline = os.getenv("HF_HUB_OFFLINE", "").strip() == "1" or os.getenv(
            "TRANSFORMERS_OFFLINE", ""
        ).strip() == "1"
        try:
            if offline:
                model = SentenceTransformer(model_name)
            else:
                model = SentenceTransformer(model_name)
        except Exception as exc:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            try:
                model = SentenceTransformer(model_name)
            except Exception:
                try:
                    model = SentenceTransformer(model_name, local_files_only=True)
                except Exception:
                    raise exc
        _MODEL_CACHE[model_name] = model
    return model


def _resolve_single_game(conn, raw: str) -> ResolvedGame | None:
    token = (raw or "").strip()
    if not token:
        return None

    if token.isdigit():
        row = conn.execute(
            """
            SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
            FROM games g
            JOIN game_profiles p ON p.app_id = g.app_id
            WHERE g.app_id = ?
            LIMIT 1
            """,
            (int(token),),
        ).fetchone()
        if row is not None:
            return ResolvedGame(app_id=int(row["app_id"]), name=str(row["name"] or ""))

    candidates = _build_query_forms(token)

    for cand in candidates:
        exact = conn.execute(
            """
            SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
            FROM games g
            JOIN game_profiles p ON p.app_id = g.app_id
            WHERE LOWER(COALESCE(g.name_ko, '')) = ?
               OR LOWER(COALESCE(g.name_en, '')) = ?
               OR LOWER(g.name) = ?
            LIMIT 1
            """,
            (cand, cand, cand),
        ).fetchone()
        if exact is not None:
            return ResolvedGame(app_id=int(exact["app_id"]), name=str(exact["name"] or ""))

    rows: list[Any] = []
    seen_ids: set[int] = set()
    for cand in candidates:
        part = conn.execute(
            """
            SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
            FROM games g
            JOIN game_profiles p ON p.app_id = g.app_id
            WHERE LOWER(COALESCE(g.name_ko, '')) LIKE ?
               OR LOWER(COALESCE(g.name_en, '')) LIKE ?
               OR LOWER(g.name) LIKE ?
            LIMIT 120
            """,
            (f"%{cand}%", f"%{cand}%", f"%{cand}%"),
        ).fetchall()
        for row in part:
            app_id = int(row["app_id"])
            if app_id in seen_ids:
                continue
            seen_ids.add(app_id)
            rows.append(row)

    if not rows:
        # Remote safety-net first: search Steam by query and map app_id back into local DB.
        for q in candidates:
            app_ids = _search_steam_app_ids(q, limit=8)
            for app_id in app_ids:
                row = conn.execute(
                    """
                    SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
                    FROM games g
                    JOIN game_profiles p ON p.app_id = g.app_id
                    WHERE g.app_id = ?
                    LIMIT 1
                    """,
                    (app_id,),
                ).fetchone()
                if row is not None:
                    return ResolvedGame(app_id=int(row["app_id"]), name=str(row["name"] or ""))

        # Final local safety-net: broad fuzzy scan across all indexed game names.
        rows = conn.execute(
            """
            SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
            FROM games g
            JOIN game_profiles p ON p.app_id = g.app_id
            """
        ).fetchall()
        if not rows:
            return None

    query_compact = _compact_token(token)
    query_compact_forms = {_compact_token(x) for x in candidates if _compact_token(x)}
    if not query_compact:
        return None

    best = None
    best_score = -1.0
    for row in rows:
        name = str(row["name"] or "")
        name_norm = _norm_token(name)
        name_compact = _compact_token(name)
        name_acro = _name_acronym(name)
        score = SequenceMatcher(None, query_compact, name_compact).ratio()
        if any(f and (name_acro == f or name_acro.startswith(f)) for f in query_compact_forms):
            score = max(score, 1.2)
        if query_compact and query_compact in name_compact:
            score += 0.35
        if name_acro:
            if name_acro in query_compact_forms or query_compact in name_acro:
                score += 0.45
            if any(f in name_acro for f in query_compact_forms):
                score += 0.20
        # Keep a light signal from space-preserved normalization as tie-breaker.
        score += 0.05 * SequenceMatcher(None, _norm_token(token), name_norm).ratio()
        if score > best_score:
            best_score = score
            best = row

    if best is None:
        sem = _semantic_resolve_single_game(conn, token)
        return sem
    if best_score < 0.74:
        sem = _semantic_resolve_single_game(conn, token)
        if sem is not None:
            return sem
        return None
    return ResolvedGame(app_id=int(best["app_id"]), name=str(best["name"] or ""))


def _resolve_games(conn, values: list[str]) -> tuple[list[ResolvedGame], list[str]]:
    seen: set[int] = set()
    out: list[ResolvedGame] = []
    unresolved: list[str] = []
    for raw in values:
        token = str(raw or "").strip()
        if not token:
            continue
        resolved = _resolve_single_game(conn, token)
        if resolved is None:
            unresolved.append(token)
            continue
        if resolved.app_id in seen:
            continue
        seen.add(resolved.app_id)
        out.append(resolved)
    return out, unresolved


def _load_profile_vectors(conn, app_ids: list[int]) -> dict[int, np.ndarray]:
    if not app_ids:
        return {}
    placeholders = ",".join("?" for _ in app_ids)
    rows = conn.execute(
        f"""
        SELECT app_id, profile_embedding
        FROM game_profiles
        WHERE app_id IN ({placeholders})
          AND profile_embedding IS NOT NULL
        """,
        tuple(int(x) for x in app_ids),
    ).fetchall()

    out: dict[int, np.ndarray] = {}
    for row in rows:
        vec = _deserialize_vector(row["profile_embedding"]).astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        out[int(row["app_id"])] = vec
    return out


def _load_game_topics(conn, app_ids: list[int]) -> tuple[set[str], set[str]]:
    if not app_ids:
        return set(), set()
    placeholders = ",".join("?" for _ in app_ids)
    rows = conn.execute(
        f"""
        SELECT genres, tags
        FROM games
        WHERE app_id IN ({placeholders})
        """,
        tuple(int(x) for x in app_ids),
    ).fetchall()

    genres_out: set[str] = set()
    tags_out: set[str] = set()
    for row in rows:
        try:
            genres = json.loads(row["genres"] or "[]")
        except Exception:
            genres = []
        try:
            tags = json.loads(row["tags"] or "[]")
        except Exception:
            tags = []

        for g in genres:
            t = _norm_token(str(g))
            if t:
                genres_out.add(t)
        for tag in tags:
            t = _norm_token(str(tag))
            if t:
                tags_out.add(t)

    return genres_out, tags_out


def _build_like_vector(like_vectors: list[np.ndarray]) -> np.ndarray:
    like_mean = np.mean(np.stack(like_vectors), axis=0).astype(np.float32)
    norm = float(np.linalg.norm(like_mean))
    if norm > 0:
        like_mean = like_mean / norm
    return like_mean


def _build_text_like_vector(liked_texts: list[str], model_name: str) -> np.ndarray:
    model = _get_model(model_name)
    likes = [x.strip() for x in liked_texts if str(x).strip()]
    if not likes:
        raise ValueError("at least one liked text is required")
    like_vecs = model.encode(likes, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
    like_mean = np.mean(np.asarray(like_vecs, dtype=np.float32), axis=0).astype(np.float32)
    norm = float(np.linalg.norm(like_mean))
    if norm > 0:
        like_mean = like_mean / norm
    return like_mean


def recommend_from_preferences(
    db_path: Path,
    liked_games: list[str],
    disliked_games: list[str] | None = None,
    top_k: int = 5,
    chroma_path: str | None = None,
    chroma_collection: str | None = None,
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    openai_api_key: str | None = None,
    openai_model: str = "gpt-4.1-mini",
) -> dict[str, Any]:
    disliked_games = disliked_games or []
    top_k = max(1, min(20, int(top_k)))

    with get_connection(Path(db_path), readonly=True) as conn:
        liked_resolved, liked_unresolved = _resolve_games(conn, liked_games)
        disliked_resolved, disliked_unresolved = _resolve_games(conn, disliked_games)

    liked_text = ", ".join(x.strip() for x in liked_games if str(x).strip())
    disliked_text = ", ".join(x.strip() for x in disliked_games if str(x).strip())
    if disliked_text:
        query_text = (
            f"좋아했던 게임: {liked_text}. "
            f"비선호 게임: {disliked_text}. "
            "이 취향을 반영해서 스팀 게임을 추천해줘."
        )
    else:
        query_text = f"좋아했던 게임: {liked_text}. 이 취향을 반영해서 스팀 게임을 추천해줘."

    from .ranker import recommend_games

    result = recommend_games(
        db_path=Path(db_path),
        query=query_text,
        top_k=top_k,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
    )

    base_mode = str(result.get("mode") or "query")
    result["mode"] = f"preference_nlq::{base_mode}"
    result["query"] = query_text
    result["resolved"] = {
        "liked": [{"app_id": x.app_id, "name": x.name} for x in liked_resolved],
        "disliked": [{"app_id": x.app_id, "name": x.name} for x in disliked_resolved],
        "liked_unresolved": liked_unresolved,
        "disliked_unresolved": disliked_unresolved,
    }
    return result


def suggest_games(
    db_path: Path,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    q = _norm_token(query)
    compact = _compact_token(query)
    limit = max(1, min(30, int(limit)))

    with get_connection(Path(db_path), readonly=True) as conn:
        if not q and not compact:
            rows = conn.execute(
                """
                SELECT g.app_id,
                       COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS display_name,
                       g.name_en,
                       g.name_ko,
                       p.recent_review_count
                FROM games g
                JOIN game_profiles p ON p.app_id = g.app_id
                ORDER BY COALESCE(p.recent_review_count, 0) DESC, g.app_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            prefix = f"{q}%"
            contains = f"%{q}%"
            cprefix = f"{compact}%"
            ccontains = f"%{compact}%"
            rows = conn.execute(
                """
                SELECT g.app_id,
                       COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS display_name,
                       g.name_en,
                       g.name_ko,
                       p.recent_review_count,
                       CASE
                         WHEN LOWER(COALESCE(g.name_ko, '')) LIKE ? THEN 8
                         WHEN LOWER(COALESCE(g.name_en, '')) LIKE ? THEN 7
                         WHEN LOWER(g.name) LIKE ? THEN 6
                         WHEN REPLACE(LOWER(COALESCE(g.name_ko, '')), ' ', '') LIKE ? THEN 5
                         WHEN REPLACE(LOWER(COALESCE(g.name_en, '')), ' ', '') LIKE ? THEN 4
                         WHEN LOWER(COALESCE(g.name_ko, '')) LIKE ? THEN 3
                         WHEN LOWER(COALESCE(g.name_en, '')) LIKE ? THEN 2
                         WHEN LOWER(g.name) LIKE ? THEN 1
                         WHEN REPLACE(LOWER(COALESCE(g.name_ko, '')), ' ', '') LIKE ? THEN 1
                         WHEN REPLACE(LOWER(COALESCE(g.name_en, '')), ' ', '') LIKE ? THEN 1
                         ELSE 0
                       END AS score
                FROM games g
                JOIN game_profiles p ON p.app_id = g.app_id
                WHERE (
                    LOWER(COALESCE(g.name_ko, '')) LIKE ?
                 OR LOWER(COALESCE(g.name_en, '')) LIKE ?
                 OR LOWER(g.name) LIKE ?
                 OR REPLACE(LOWER(COALESCE(g.name_ko, '')), ' ', '') LIKE ?
                 OR REPLACE(LOWER(COALESCE(g.name_en, '')), ' ', '') LIKE ?
                )
                ORDER BY score DESC, COALESCE(p.recent_review_count, 0) DESC, g.app_id DESC
                LIMIT ?
                """,
                (
                    prefix,
                    prefix,
                    prefix,
                    cprefix,
                    cprefix,
                    contains,
                    contains,
                    contains,
                    ccontains,
                    ccontains,
                    contains,
                    contains,
                    contains,
                    ccontains,
                    ccontains,
                    limit,
                ),
            ).fetchall()

            if not rows and compact:
                # Acronym fallback for short aliases like "gta", "rdr", etc.
                all_rows = conn.execute(
                    """
                    SELECT g.app_id,
                           COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS display_name,
                           g.name_en,
                           g.name_ko,
                           p.recent_review_count
                    FROM games g
                    JOIN game_profiles p ON p.app_id = g.app_id
                    """
                ).fetchall()
                scored: list[tuple[int, int, Any]] = []
                for row in all_rows:
                    display = str(row["display_name"] or "")
                    acro = _name_acronym(display)
                    if not acro:
                        continue
                    if acro.startswith(compact):
                        score = 2
                    elif compact in acro:
                        score = 1
                    else:
                        continue
                    scored.append((score, int(row["recent_review_count"] or 0), row))
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                rows = [x[2] for x in scored[:limit]]

    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "app_id": int(row["app_id"]),
                "name": str(row["display_name"] or ""),
                "name_en": str(row["name_en"] or ""),
                "name_ko": str(row["name_ko"] or ""),
            }
        )
    return out
