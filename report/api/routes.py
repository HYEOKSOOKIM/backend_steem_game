"""API routes for read-only serving and admin-only offline pipeline triggers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, HTTPException
except ImportError:  # pragma: no cover - exercised only when FastAPI is missing.
    APIRouter = None
    HTTPException = None

from report.pipeline.offline_pipeline import run_offline_pipeline_for_appid
from report.services.demo_catalog import build_demo_game_index, load_demo_games
from report.services.report_view import (
    build_consumer_report_from_snapshot,
    is_consumer_report_payload,
)
from report.storage.file_store import FileStore

APP_ROOT = Path(__file__).resolve().parents[2]
LEGACY_DATA_ROOT = APP_ROOT / "data"
DEFAULT_DATA_ROOT = LEGACY_DATA_ROOT / "report"


def _catalog_path(data_root: str | Path) -> Path:
    base = Path(data_root)
    preferred = base / "catalog" / "demo_games.json"
    if preferred.exists():
        return preferred
    legacy = LEGACY_DATA_ROOT / "catalog" / "demo_games.json"
    if legacy.exists():
        return legacy
    return preferred


def _load_demo_game_index(data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[int, dict[str, Any]]:
    games = load_demo_games(_catalog_path(data_root))
    return build_demo_game_index(games)


def _ensure_demo_game(appid: int, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    if not isinstance(appid, int):
        raise ValueError("appid must be an integer.")
    index = _load_demo_game_index(data_root)
    game = index.get(appid)
    if game is None:
        raise ValueError(f"appid {appid} is not enabled for demo serving.")
    return game


def list_demo_games(data_root: str | Path = DEFAULT_DATA_ROOT) -> list[dict[str, Any]]:
    """List predefined demo games with snapshot/report readiness."""
    index = _load_demo_game_index(data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)

    result: list[dict[str, Any]] = []
    for appid, game in sorted(index.items(), key=lambda item: item[0]):
        analysis_ready = _artifact_exists(lambda: store.read_analysis_result(appid))
        report_ready = _artifact_exists(lambda: store.read_report_view(appid)) or analysis_ready
        metadata = _safe_read(lambda: store.read_game_metadata(appid), {})
        result.append(
            {
                "appid": appid,
                "name": metadata.get("name") or game.get("name"),
                "enabled_for_demo": True,
                "analysis_ready": analysis_ready,
                "report_ready": report_ready,
            }
        )
    return result


def load_report(appid: int, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    """Load report payload for one game without triggering any analysis work."""
    _ensure_demo_game(appid, data_root=data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)

    report_payload = _safe_read(lambda: store.read_report_view(appid))
    if is_consumer_report_payload(report_payload):
        return report_payload

    analysis = store.read_analysis_result(appid)
    metadata = _safe_read(lambda: store.read_game_metadata(appid), {})
    processed = _safe_read(lambda: store.read_processed_reviews(appid), [])

    return build_consumer_report_from_snapshot(
        appid=appid,
        metadata=metadata,
        analysis=analysis,
        processed_reviews=processed,
        pipeline_run_id=analysis.get("pipeline_run_id"),
        source_review_count=analysis.get("source_review_count"),
    )


def load_analysis_result(appid: int, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    """Load stored analysis snapshot for one demo game."""
    _ensure_demo_game(appid, data_root=data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)
    return store.read_analysis_result(appid)


def load_raw_reviews(appid: int, data_root: str | Path = DEFAULT_DATA_ROOT) -> list[dict[str, Any]]:
    """Load stored raw review records for one demo game."""
    _ensure_demo_game(appid, data_root=data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)
    return store.read_raw_reviews(appid)


def load_processed_reviews(
    appid: int,
    data_root: str | Path = DEFAULT_DATA_ROOT,
) -> list[dict[str, Any]]:
    """Load stored processed review records for one demo game."""
    _ensure_demo_game(appid, data_root=data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)
    return store.read_processed_reviews(appid)


def load_game_metadata(appid: int, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    """Load stored game metadata for one demo game."""
    _ensure_demo_game(appid, data_root=data_root)
    store = FileStore(data_root, fallback_root_dir=LEGACY_DATA_ROOT)
    return store.read_game_metadata(appid)


def run_admin_ingest(payload: dict[str, Any], data_root: str | Path = DEFAULT_DATA_ROOT) -> dict[str, Any]:
    """Run offline pipeline manually via admin-only entrypoint."""
    appid = payload.get("appid")
    if not isinstance(appid, int):
        raise ValueError("appid must be provided as an integer.")
    _ensure_demo_game(appid, data_root=data_root)

    return run_offline_pipeline_for_appid(
        appid,
        data_root=data_root,
        review_pages=payload.get("review_pages", "all"),
        use_llm_fallback=bool(payload.get("use_llm_fallback", False)),
        max_llm_reviews=int(payload.get("max_llm_reviews", 50)),
        llm_timeout_seconds=int(payload.get("llm_timeout_seconds", 20)),
        llm_retry_limit=int(payload.get("llm_retry_limit", 2)),
        llm_min_confidence=float(payload.get("llm_min_confidence", 0.70)),
        game_name=payload.get("game_name"),
    )


def _artifact_exists(loader) -> bool:
    try:
        loader()
        return True
    except FileNotFoundError:
        return False


def _safe_read(loader, default=None):
    try:
        return loader()
    except FileNotFoundError:
        return default


if APIRouter is not None:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health():
        """Return a minimal health response."""
        return {"status": "ok"}

    @router.get("/games")
    def get_demo_games():
        """Return predefined demo games only."""
        return {"games": list_demo_games()}

    @router.get("/games/{appid}/report")
    def get_report(appid: int):
        """Return a consumer-facing report from stored snapshots."""
        try:
            return load_report(appid)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"report for appid {appid} is not ready",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/games/{appid}/analysis")
    def get_analysis(appid: int):
        """Return stored analysis artifact for one demo game."""
        try:
            return load_analysis_result(appid)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"analysis for appid {appid} was not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/games/{appid}/metadata")
    def get_metadata(appid: int):
        """Return stored metadata for one demo game."""
        try:
            return load_game_metadata(appid)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"metadata for appid {appid} was not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/games/{appid}/raw")
    def get_raw_reviews(appid: int):
        """Return stored raw reviews for one demo game (debug)."""
        try:
            return load_raw_reviews(appid)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"raw reviews for appid {appid} were not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/games/{appid}/processed")
    def get_processed_reviews(appid: int):
        """Return stored processed reviews for one demo game (debug)."""
        try:
            return load_processed_reviews(appid)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"processed reviews for appid {appid} were not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/admin/ingest")
    def admin_ingest(payload: dict[str, Any]):
        """Admin-only manual trigger for offline ingestion/analysis."""
        try:
            return run_admin_ingest(payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

else:  # pragma: no cover - exercised only when FastAPI is missing.
    router = None

