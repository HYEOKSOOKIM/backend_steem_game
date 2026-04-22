from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from .chroma_store import query_profiles_from_chroma
from .db import get_connection

_MODEL_CACHE: dict[str, SentenceTransformer] = {}


@dataclass
class ResolvedGame:
    app_id: int
    name: str


def _deserialize_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _norm_token(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _confidence_label(recent_count: int, median_playtime: float) -> str:
    if recent_count >= 80 and median_playtime >= 120:
        return "high"
    if recent_count >= 30:
        return "medium"
    return "low"


def _get_model(model_name: str) -> SentenceTransformer:
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

    lower = token.lower()
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
        (lower, lower, lower),
    ).fetchone()
    if exact is not None:
        return ResolvedGame(app_id=int(exact["app_id"]), name=str(exact["name"] or ""))

    rows = conn.execute(
        """
        SELECT g.app_id, COALESCE(NULLIF(g.name_ko, ''), NULLIF(g.name_en, ''), g.name) AS name
        FROM games g
        JOIN game_profiles p ON p.app_id = g.app_id
        WHERE LOWER(COALESCE(g.name_ko, '')) LIKE ?
           OR LOWER(COALESCE(g.name_en, '')) LIKE ?
           OR LOWER(g.name) LIKE ?
        LIMIT 120
        """,
        (f"%{lower}%", f"%{lower}%", f"%{lower}%"),
    ).fetchall()
    if not rows:
        return None

    best = None
    best_score = -1.0
    for row in rows:
        name = str(row["name"] or "")
        score = SequenceMatcher(None, lower, name.lower()).ratio()
        if lower in name.lower():
            score += 0.35
        if score > best_score:
            best_score = score
            best = row

    if best is None:
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

        if dislike_sim >= dislike_sim_threshold:
            continue
        if len(overlap_tags) >= 2:
            continue

        recent_count = int(row.get("recent_review_count") or 0)
        median_playtime = float(row.get("median_playtime_1y") or 0.0)
        like_similarity = float(row.get("similarity") or 0.0)

        penalty = (0.30 * dislike_sim) + (0.02 * len(overlap_genres)) + (0.04 * len(overlap_tags))
        final_score = like_similarity - penalty

        ranked.append(
            {
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
        )

    ranked.sort(
        key=lambda x: (
            float(x.get("_final_score", 0.0)),
            float(x.get("similarity", 0.0)),
            int(x.get("recent_review_count", 0)),
        ),
        reverse=True,
    )

    results = ranked[:top_k]
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
