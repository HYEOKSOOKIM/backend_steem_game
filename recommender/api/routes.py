"""Recommendation API routes."""

from __future__ import annotations

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


if APIRouter is not None:
    recommend_router = APIRouter(prefix="/api/recommend")

    class RecommendRequest(BaseModel):
        query: str
        top_k: int = 5

    @recommend_router.get("/health")
    def recommend_health() -> dict[str, Any]:
        return {"status": "ok", "db_ready": _is_db_ready()}

    @recommend_router.post("")
    def recommend(req: RecommendRequest) -> JSONResponse:
        if not _is_db_ready():
            raise HTTPException(
                status_code=503,
                detail="Recommendation DB is not ready. Check backend/data/recommender.",
            )

        try:
            from recommender.src.config import load_settings
            from recommender.src.ranker import recommend_games
            from recommender.src.web_ui import _prepare_result_payload

            settings = load_settings()
            result = recommend_games(
                db_path=_resolve_db_path(),
                query=req.query,
                top_k=req.top_k,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
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
                "generated_at": result.get("generated_at"),
            }
            return JSONResponse(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

else:
    recommend_router = None
