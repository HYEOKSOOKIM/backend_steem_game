"""Recommendation API routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:
    APIRouter = None
    HTTPException = None
    JSONResponse = None
    BaseModel = object

APP_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = APP_ROOT / "data"
RECOMMENDER_DATA_ROOT = DATA_ROOT / "recommender"
DB_PATH = RECOMMENDER_DATA_ROOT / "steam_mvp.db"
LEGACY_DB_PATH = DATA_ROOT / "steam_mvp.db"
CHROMA_PATH = RECOMMENDER_DATA_ROOT / "chroma_v2"
LEGACY_CHROMA_PATH = DATA_ROOT / "chroma_v2"


def _is_db_ready() -> bool:
    return DB_PATH.exists() or LEGACY_DB_PATH.exists()


def _resolve_db_path() -> Path:
    if DB_PATH.exists():
        return DB_PATH
    return LEGACY_DB_PATH


def _ensure_db_schema_ready() -> None:
    if not _is_db_ready():
        return
    from recommender.src.db import init_db

    init_db(_resolve_db_path())


if APIRouter is not None:
    recommend_router = APIRouter(prefix="/api/recommend")

    def _normalize_game_tokens(values: list[Any] | None) -> tuple[list[str], list[int]]:
        names: list[str] = []
        app_ids: list[int] = []
        for v in list(values or []):
            if v is None:
                continue
            if isinstance(v, dict):
                raw_id = v.get("app_id")
                if raw_id is not None and str(raw_id).strip().isdigit():
                    app_ids.append(int(str(raw_id).strip()))
                raw_name = v.get("name")
                if raw_name is not None:
                    nm = str(raw_name).strip()
                    if nm:
                        names.append(nm)
                continue
            s = str(v).strip()
            if not s:
                continue
            if s.isdigit():
                app_ids.append(int(s))
            else:
                names.append(s)
        # Keep order while removing duplicates.
        uniq_names: list[str] = []
        seen_names: set[str] = set()
        for n in names:
            k = n.lower()
            if k in seen_names:
                continue
            seen_names.add(k)
            uniq_names.append(n)
        uniq_ids: list[int] = []
        seen_ids: set[int] = set()
        for i in app_ids:
            if i in seen_ids:
                continue
            seen_ids.add(i)
            uniq_ids.append(i)
        return uniq_names, uniq_ids

    class RecommendRequest(BaseModel):
        query: str
        top_k: int = 5
        played_games: list[Any] = []
        played_app_ids: list[int] = []
        liked_games: list[Any] = []
        disliked_games: list[Any] = []
        liked_app_ids: list[int] = []
        disliked_app_ids: list[int] = []
        require_korean_support: bool = False

    class PreferenceRecommendRequest(BaseModel):
        liked_games: list[Any]
        disliked_games: list[Any] = []
        top_k: int = 5

    @recommend_router.get("/health")
    def recommend_health() -> dict[str, Any]:
        from recommender.src.localize import get_translation_checkin_status

        return {
            "status": "ok",
            "db_ready": _is_db_ready(),
            "translation_checkin": get_translation_checkin_status(),
        }

    @recommend_router.get("/suggest")
    def recommend_suggest(q: str = "", limit: int = 10) -> JSONResponse:
        if not _is_db_ready():
            raise HTTPException(
                status_code=503,
                detail="Recommendation DB is not ready. Check backend/data/recommender.",
            )
        _ensure_db_schema_ready()
        try:
            from recommender.src.preference_recommender import suggest_games

            rows = suggest_games(
                db_path=_resolve_db_path(),
                query=q,
                limit=limit,
            )
            return JSONResponse({"query": q, "count": len(rows), "items": rows})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @recommend_router.post("")
    def recommend(req: RecommendRequest) -> JSONResponse:
        route_start = time.perf_counter()
        if not _is_db_ready():
            raise HTTPException(
                status_code=503,
                detail="Recommendation DB is not ready. Check backend/data/recommender.",
            )
        _ensure_db_schema_ready()

        try:
            from recommender.src.config import load_settings
            from recommender.src.db import get_connection
            from recommender.src.preference_recommender import _resolve_games
            from recommender.src.ranker import recommend_games
            from recommender.src.web_ui import _prepare_result_payload

            settings = load_settings()
            played_names, played_ids_from_tokens = _normalize_game_tokens(req.played_games)
            liked_names, liked_ids_from_tokens = _normalize_game_tokens(req.liked_games)
            disliked_names, disliked_ids_from_tokens = _normalize_game_tokens(req.disliked_games)
            exclude_app_ids: set[int] = {
                int(x)
                for x in list(req.played_app_ids or [])
                if str(x).strip().isdigit()
            }
            exclude_app_ids.update(int(x) for x in played_ids_from_tokens if str(x).strip().isdigit())
            played_resolved: list[dict[str, Any]] = []
            played_unresolved: list[str] = []
            liked_resolved: list[dict[str, Any]] = []
            liked_unresolved: list[str] = []
            disliked_resolved: list[dict[str, Any]] = []
            disliked_unresolved: list[str] = []
            if played_names:
                with get_connection(_resolve_db_path(), readonly=True) as conn:
                    resolved, unresolved = _resolve_games(conn, list(played_names or []))
                exclude_app_ids.update(int(x.app_id) for x in resolved)
                played_resolved = [{"app_id": int(x.app_id), "name": str(x.name)} for x in resolved]
                played_unresolved = [str(x) for x in unresolved]

            liked_app_ids_set: set[int] = {
                int(x)
                for x in list(req.liked_app_ids or [])
                if str(x).strip().isdigit()
            }
            liked_app_ids_set.update(int(x) for x in liked_ids_from_tokens if str(x).strip().isdigit())
            disliked_app_ids_set: set[int] = {
                int(x)
                for x in list(req.disliked_app_ids or [])
                if str(x).strip().isdigit()
            }
            disliked_app_ids_set.update(int(x) for x in disliked_ids_from_tokens if str(x).strip().isdigit())
            with get_connection(_resolve_db_path(), readonly=True) as conn:
                if liked_names:
                    resolved, unresolved = _resolve_games(conn, list(liked_names or []))
                    liked_app_ids_set.update(int(x.app_id) for x in resolved)
                    liked_resolved = [{"app_id": int(x.app_id), "name": str(x.name)} for x in resolved]
                    liked_unresolved = [str(x) for x in unresolved]
                if disliked_names:
                    resolved, unresolved = _resolve_games(conn, list(disliked_names or []))
                    disliked_app_ids_set.update(int(x.app_id) for x in resolved)
                    disliked_resolved = [{"app_id": int(x.app_id), "name": str(x.name)} for x in resolved]
                    disliked_unresolved = [str(x) for x in unresolved]

            # Always exclude all user-input games from recommendations.
            exclude_app_ids.update(liked_app_ids_set)
            exclude_app_ids.update(disliked_app_ids_set)

            result = recommend_games(
                db_path=_resolve_db_path(),
                query=req.query,
                top_k=req.top_k,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
                exclude_app_ids=sorted(exclude_app_ids),
                liked_app_ids=sorted(liked_app_ids_set),
                disliked_app_ids=sorted(disliked_app_ids_set),
                preference_weight=0.10,
                require_korean_support=bool(req.require_korean_support),
            )
            payload = _prepare_result_payload(result, query=req.query, top_k=req.top_k)

            llm_errors = list(result.get("llm_errors", []) or [])
            if not payload.get("results"):
                joined = " ".join(str(x) for x in llm_errors).lower()
                if "embedding_model_load_failed" in joined or "huggingface.co" in joined:
                    payload["empty_reason"] = "Recommendation model could not be loaded. Check network/model cache."
                elif "chroma_required" in joined:
                    payload["empty_reason"] = "Recommendation index query failed. Check Chroma path."
                else:
                    payload["empty_reason"] = "No recommendation results. Try another query."
            else:
                payload["empty_reason"] = ""

            payload["meta"] = {
                "mode": result.get("mode"),
                "normalized_input_query": result.get("normalized_input_query"),
                "rewritten_query": result.get("rewritten_query"),
                "effective_query": result.get("effective_query"),
                "reference_game": result.get("reference_game"),
                "similar_to_fallback": result.get("similar_to_fallback"),
                "parsed_query": result.get("parsed_query"),
                "require_korean_support": bool(req.require_korean_support),
                "excluded_app_ids": sorted(exclude_app_ids),
                "played_resolved": played_resolved,
                "played_unresolved": played_unresolved,
                "liked_resolved": liked_resolved,
                "liked_unresolved": liked_unresolved,
                "disliked_resolved": disliked_resolved,
                "disliked_unresolved": disliked_unresolved,
                "perf": result.get("perf") or {},
                "route_total_ms": round((time.perf_counter() - route_start) * 1000.0, 2),
                "generated_at": result.get("generated_at"),
            }
            return JSONResponse(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @recommend_router.post("/preference")
    def recommend_by_preference(req: PreferenceRecommendRequest) -> JSONResponse:
        if not _is_db_ready():
            raise HTTPException(
                status_code=503,
                detail="Recommendation DB is not ready. Check backend/data/recommender.",
            )
        _ensure_db_schema_ready()

        try:
            import os

            from recommender.src.config import load_settings
            from recommender.src.preference_recommender import recommend_from_preferences
            from recommender.src.web_ui import _prepare_result_payload

            settings = load_settings()
            liked_names, liked_ids_from_tokens = _normalize_game_tokens(req.liked_games)
            disliked_names, disliked_ids_from_tokens = _normalize_game_tokens(req.disliked_games)
            liked_input = list(liked_names) + [str(x) for x in liked_ids_from_tokens]
            disliked_input = list(disliked_names) + [str(x) for x in disliked_ids_from_tokens]
            result = recommend_from_preferences(
                db_path=_resolve_db_path(),
                liked_games=liked_input,
                disliked_games=disliked_input,
                top_k=req.top_k,
                chroma_path=(os.getenv("CHROMA_PATH") or "").strip() or None,
                chroma_collection=(os.getenv("CHROMA_COLLECTION") or "").strip() or None,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
            )
            payload = _prepare_result_payload(
                result,
                query="취향 기반 추천",
                top_k=req.top_k,
            )
            payload["meta"] = {
                "mode": result.get("mode"),
                "resolved": result.get("resolved"),
                "generated_at": result.get("generated_at"),
            }
            if not payload.get("results"):
                payload["empty_reason"] = "입력한 선호/비선호 게임으로 추천 결과를 만들지 못했습니다."
            else:
                payload["empty_reason"] = ""
            payload["llm_errors"] = [str(x) for x in (result.get("llm_errors", []) or [])][:8]
            return JSONResponse(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

else:
    recommend_router = None
