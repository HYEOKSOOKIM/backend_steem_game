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

        like_ids = [x.app_id for x in liked_resolved]
        dislike_ids = [x.app_id for x in disliked_resolved]
        vectors = _load_profile_vectors(conn, like_ids + dislike_ids)
        disliked_genres, disliked_tags = _load_game_topics(conn, dislike_ids)

    like_vectors = [vectors[x.app_id] for x in liked_resolved if x.app_id in vectors]
    dislike_vectors = [vectors[x.app_id] for x in disliked_resolved if x.app_id in vectors]

    runtime_errors: list[str] = []
    mode = "preference_profile"

    query_vec: np.ndarray
    if like_vectors:
        # Step 1: rank candidates only by liked-game preference.
        query_vec = _build_like_vector(like_vectors)

        # Optional minor blend for unresolved liked names.
        if liked_unresolved:
            try:
                text_vec = _build_text_like_vector(liked_unresolved, embedding_model)
                query_vec = (0.9 * query_vec) + (0.1 * text_vec)
                norm = float(np.linalg.norm(query_vec))
                if norm > 0:
                    query_vec = query_vec / norm
                mode = "preference_profile_blended"
            except Exception as exc:
                runtime_errors.append(f"preference_text_blend_skipped: {exc}")
    else:
        # If no liked game can be resolved in DB, fallback to text-liked intent.
        try:
            query_vec = _build_text_like_vector(liked_unresolved or liked_games, embedding_model)
            mode = "preference_text_fallback"
            runtime_errors.append("preference_fallback_used: no_liked_game_embedding")
        except Exception:
            from .ranker import recommend_games

            like_text = ", ".join(x.strip() for x in (liked_games or []) if str(x).strip())
            dislike_text = ", ".join(x.strip() for x in (disliked_games or []) if str(x).strip())
            if dislike_text:
                query_text = (
                    f"I liked games such as {like_text}. "
                    f"I disliked games such as {dislike_text}. Recommend similar games."
                )
            else:
                query_text = f"I liked games such as {like_text}. Recommend similar games."

            fallback_result = recommend_games(
                db_path=Path(db_path),
                query=query_text,
                top_k=top_k,
                openai_api_key=openai_api_key,
                openai_model=openai_model,
            )
            fallback_errors = list(fallback_result.get("llm_errors", []) or [])
            fallback_errors.append("preference_fallback_used: natural_query_mode")
            fallback_result["llm_errors"] = fallback_errors
            fallback_result["mode"] = "preference_query_fallback"
            fallback_result["resolved"] = {
                "liked": [{"app_id": x.app_id, "name": x.name} for x in liked_resolved],
                "disliked": [{"app_id": x.app_id, "name": x.name} for x in disliked_resolved],
                "liked_unresolved": liked_unresolved,
                "disliked_unresolved": disliked_unresolved,
            }
            return fallback_result

    rows = query_profiles_from_chroma(
        db_path=Path(db_path),
        query_vector=query_vec,
        n_results=max(top_k * 20, 160),
        chroma_path=chroma_path,
        collection_name=chroma_collection,
    )

    exclude_ids = {x.app_id for x in liked_resolved}.union({x.app_id for x in disliked_resolved})
    dislike_sim_threshold = float(os.getenv("PREFERENCE_DISLIKE_EXCLUDE_SIM") or 0.62)

    ranked: list[dict[str, Any]] = []
    relaxed_ranked: list[dict[str, Any]] = []
    for row in rows:
        app_id = int(row.get("app_id") or 0)
        if app_id <= 0 or app_id in exclude_ids:
            continue

        genres = [str(x) for x in (row.get("genres") or [])]
        tags = [str(x) for x in (row.get("tags") or [])]
        cand_genres = {_norm_token(x) for x in genres if _norm_token(x)}
        cand_tags = {_norm_token(x) for x in tags if _norm_token(x)}

        overlap_genres = cand_genres.intersection(disliked_genres)
        overlap_tags = cand_tags.intersection(disliked_tags)

        # Step 2: remove candidates close to disliked games.
        dislike_sim = 0.0
        vec = row.get("vector")
        if dislike_vectors and isinstance(vec, np.ndarray):
            c_vec = np.asarray(vec, dtype=np.float32)
            c_norm = float(np.linalg.norm(c_vec))
            if c_norm > 0:
                c_vec = c_vec / c_norm
                dislike_sim = max(float(np.dot(c_vec, d_vec)) for d_vec in dislike_vectors)

        recent_count = int(row.get("recent_review_count") or 0)
        median_playtime = float(row.get("median_playtime_1y") or 0.0)
        like_similarity = float(row.get("similarity") or 0.0)

        penalty = (0.30 * dislike_sim) + (0.02 * len(overlap_genres)) + (0.04 * len(overlap_tags))
        final_score = like_similarity - penalty
        item = {
            "app_id": app_id,
            "name": str(row.get("name") or ""),
            "steam_url": f"https://store.steampowered.com/app/{app_id}/",
            "image_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg",
            "genres": genres,
            "tags": tags,
            "similarity": round(like_similarity, 4),
            "recent_review_count": recent_count,
            "positive_ratio_1y": round(float(row.get("positive_ratio_1y") or 0.0), 4),
            "median_playtime_1y": round(median_playtime, 1),
            "confidence": _confidence_label(recent_count, median_playtime),
            "reason_ko": "좋아한 게임 기준 추천 결과에서 비선호 게임과 겹치는 특성을 제외한 결과입니다.",
            "one_liner_ko": "",
            "evidence_reviews": [],
            "_final_score": final_score,
        }
        relaxed_ranked.append(item)

        if dislike_sim >= dislike_sim_threshold:
            continue
        if len(overlap_tags) >= 2:
            continue
        ranked.append(item)

    ranked.sort(
        key=lambda x: (
            float(x.get("_final_score", 0.0)),
            float(x.get("similarity", 0.0)),
            int(x.get("recent_review_count", 0)),
        ),
        reverse=True,
    )

    results = ranked[:top_k]
    if not results and relaxed_ranked:
        # Keep UX stable: if strict dislike filtering removes everything,
        # fall back to a relaxed list rather than returning an empty screen.
        runtime_errors.append("preference_filter_relaxed: strict_dislike_filter_removed_all")
        relaxed_ranked.sort(
            key=lambda x: (
                float(x.get("_final_score", 0.0)),
                float(x.get("similarity", 0.0)),
                int(x.get("recent_review_count", 0)),
            ),
            reverse=True,
        )
        results = relaxed_ranked[:top_k]
    for item in results:
        item.pop("_final_score", None)

    return {
        "query": "",
        "normalized_input_query": "",
        "rewritten_query": "",
        "effective_query": "",
        "mode": mode,
        "reference_game": None,
        "similar_to_fallback": None,
        "parsed_query": None,
        "results": results,
        "llm_errors": runtime_errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resolved": {
            "liked": [{"app_id": x.app_id, "name": x.name} for x in liked_resolved],
            "disliked": [{"app_id": x.app_id, "name": x.name} for x in disliked_resolved],
            "liked_unresolved": liked_unresolved,
            "disliked_unresolved": disliked_unresolved,
        },
    }


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
