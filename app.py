"""Application entrypoint for the backend API service."""

from __future__ import annotations

import os

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

    return app


app = create_app() if FastAPI is not None else None
