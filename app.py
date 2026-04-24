"""Application entrypoint for the backend API service."""

from __future__ import annotations

import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # pragma: no cover - exercised only when FastAPI is missing.
    FastAPI = None
    CORSMiddleware = None

from recommender.api.routes import recommend_router
from report.api.routes import router

logger = logging.getLogger(__name__)


def _load_allowed_origins() -> list[str]:
    raw = os.getenv("BACKEND_CORS_ORIGINS", "")
    values = [item.strip() for item in raw.split(",")]
    origins = [item for item in values if item]
    if origins:
        return origins
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def create_app():
    """Create the backend application instance."""
    if FastAPI is None:
        raise RuntimeError("fastapi is required to run the backend application.")

    app = FastAPI(title="steam-insights-api")

    if CORSMiddleware is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_load_allowed_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/")
    def index() -> dict[str, str]:
        """Return a minimal backend service status."""
        return {"service": "steam-insights-api", "status": "ok"}

    if router is not None:
        app.include_router(router)

    if recommend_router is not None:
        app.include_router(recommend_router)

    @app.on_event("startup")
    def _warmup_on_startup() -> None:
        if (os.getenv("RECOMMENDER_WARMUP_ON_STARTUP") or "1").strip() != "1":
            return
        try:
            from recommender.api.routes import _ensure_db_schema_ready, _is_db_ready, _resolve_db_path
            from recommender.src.config import load_settings
            from recommender.src.localize import translate_en_to_ko
            from recommender.src.ranker import recommend_games

            _ensure_db_schema_ready()
            if not _is_db_ready():
                logger.info("[warmup] skipped: recommender db not ready")
                return

            started = time.perf_counter()
            settings = load_settings()
            recommend_games(
                db_path=_resolve_db_path(),
                query=(os.getenv("RECOMMENDER_WARMUP_QUERY") or "힐링 싱글 추천"),
                top_k=1,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
            )
            # Warm translator cache as well (used for evidence localization in response payload).
            translate_en_to_ko("Great game with fun gameplay.")
            elapsed = round((time.perf_counter() - started) * 1000.0, 2)
            logger.info("[warmup] completed in %sms", elapsed)
        except Exception as exc:
            logger.warning("[warmup] failed: %s", exc)

    return app


app = create_app() if FastAPI is not None else None
