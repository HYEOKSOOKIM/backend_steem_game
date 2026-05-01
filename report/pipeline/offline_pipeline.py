"""Offline-only ingestion and analysis entrypoint."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report.analysis.preprocess import preprocess_reviews
from report.models.schemas import RawReview
from report.services.demo_catalog import upsert_demo_game
from report.services.analysis_service import (
    build_analysis_result_from_processed,
    enrich_processed_reviews,
)
from report.services.report_material_refiner import (
    OpenAIReportMaterialRefiner,
    ReportMaterialRefinerConfig,
    build_report_materials,
)
from report.services.report_view import build_report_ready_data
from report.services.steam_reviews import (
    fetch_steam_game_metadata,
    fetch_steam_reviews,
    normalize_steam_game_metadata,
    normalize_steam_review_summary,
    normalize_steam_reviews,
)
from report.storage.file_store import FileStore

APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = APP_ROOT / "data" / "report"
MAX_NUMERIC_REVIEW_PAGES = 200


def run_offline_pipeline_for_appid(
    appid: int,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    review_pages: int | str = "all",
    use_llm_fallback: bool = True,
    max_llm_reviews: int = 50,
    llm_timeout_seconds: int = 20,
    llm_retry_limit: int = 2,
    llm_min_confidence: float = 0.70,
    game_name: str | None = None,
    log_fetch_progress: bool = False,
) -> dict[str, Any]:
    """Run full offline pipeline for one appid and persist artifacts."""
    parsed_pages = _parse_review_pages(review_pages)
    pipeline_run_id = f"{appid}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    steam_payload = fetch_steam_reviews(
        appid,
        max_pages=None if parsed_pages == "all" else parsed_pages,
        progress_callback=(
            _build_fetch_progress_callback(appid, parsed_pages)
            if log_fetch_progress
            else None
        ),
    )
    fetch_stats = steam_payload.get("_fetch_stats", {}) if isinstance(steam_payload, dict) else {}
    metadata_payload = fetch_steam_game_metadata(appid)
    metadata_payload_en = fetch_steam_game_metadata(appid, language="english")

    metadata = normalize_steam_game_metadata(appid, metadata_payload)
    metadata_en = normalize_steam_game_metadata(appid, metadata_payload_en)
    metadata.name_ko = metadata.name
    metadata.name_en = metadata_en.name or metadata.name
    metadata.name = metadata.name_ko or metadata.name_en or metadata.name
    for key, value in normalize_steam_review_summary(steam_payload).items():
        setattr(metadata, key, value)
    # Keep saved filenames aligned with Steam appdetails name by default.
    # Use manual name only when Steam metadata name is unavailable.
    output_game_name = metadata.name or game_name

    raw_reviews: list[RawReview] = normalize_steam_reviews(appid, steam_payload)
    deterministic_processed = preprocess_reviews(raw_reviews)
    processed_reviews = enrich_processed_reviews(deterministic_processed)
    analysis = build_analysis_result_from_processed(processed_reviews, appid=appid)

    llm_stats = {
        "considered": 0,
        "selected": 0,
        "invoked": 0,
        "success": 0,
        "schema_invalid": 0,
        "low_confidence": 0,
        "cache_hits": 0,
        "fallback_used": 0,
    }
    report_materials: list[dict[str, Any]] = []

    if use_llm_fallback:
        llm_config = ReportMaterialRefinerConfig(
            enabled=True,
            max_llm_reviews=max_llm_reviews,
            timeout_seconds=llm_timeout_seconds,
            retry_limit=llm_retry_limit,
            min_confidence=llm_min_confidence,
        )
        refiner = OpenAIReportMaterialRefiner()
        report_materials, stats = build_report_materials(
            processed_reviews,
            analysis=analysis,
            config=llm_config,
            refiner=refiner,
        )
        llm_stats = stats.to_dict()

    analysis_payload = analysis.to_dict()
    analysis_payload.update(
        {
            "pipeline_run_id": pipeline_run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_review_count": len(raw_reviews),
            "review_pages": parsed_pages,
            "fetched_pages": fetch_stats.get("pages_fetched"),
            "fetched_review_count": fetch_stats.get("deduped_review_count"),
            "fetch_timeout_seconds": fetch_stats.get("request_timeout_seconds"),
            "fetch_filter": fetch_stats.get("filter_type"),
            "all_mode_page_cap": fetch_stats.get("all_mode_page_cap"),
            "all_mode_cap_reached": fetch_stats.get("all_mode_cap_reached"),
            "llm_stats": llm_stats,
            "report_material_refiner": {
                "enabled": bool(use_llm_fallback),
                "max_llm_reviews": int(max_llm_reviews),
                "llm_min_confidence": float(llm_min_confidence),
                "material_count": len(report_materials),
                "stats": llm_stats,
            },
        }
    )

    report_view = build_report_ready_data(
        appid=appid,
        metadata=metadata,
        analysis=analysis,
        raw_reviews=raw_reviews,
        processed_reviews=processed_reviews,
        report_materials=report_materials,
        pipeline_run_id=pipeline_run_id,
    )

    store = FileStore(data_root)
    store.write_raw_reviews(
        appid,
        [review.to_dict() for review in raw_reviews],
        game_name=output_game_name,
    )
    store.write_processed_reviews(
        appid,
        [review.to_dict() for review in processed_reviews],
        game_name=output_game_name,
    )
    store.write_analysis_result(
        appid,
        analysis_payload,
        game_name=output_game_name,
    )
    store.write_game_metadata(
        appid,
        metadata.to_dict(),
        game_name=output_game_name,
    )
    store.write_report_view(
        appid,
        report_view,
        game_name=output_game_name,
    )
    catalog_path = Path(data_root) / "catalog" / "demo_games.json"
    upsert_demo_game(
        catalog_path,
        appid=appid,
        name=metadata.name or output_game_name or f"appid-{appid}",
        name_en=metadata.name_en,
        name_ko=metadata.name_ko,
        enabled_for_demo=True,
    )

    return {
        "appid": appid,
        "pipeline_run_id": pipeline_run_id,
        "raw_review_count": len(raw_reviews),
        "processed_review_count": len(processed_reviews),
        "included_review_count": sum(
            1 for review in processed_reviews if review.included_in_analysis
        ),
        "review_pages": parsed_pages,
        "llm_stats": llm_stats,
        "report_material_count": len(report_materials),
        "output_file_game_name": output_game_name,
        "catalog_updated": True,
    }


def _parse_review_pages(value: Any) -> int | str:
    if value is None:
        return "all"

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "all":
            return "all"
        if normalized.isdigit():
            value = int(normalized)
        else:
            raise ValueError(
                f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
            )

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
        )
    if value < 1 or value > MAX_NUMERIC_REVIEW_PAGES:
        raise ValueError(
            f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
        )
    return value


def _build_fetch_progress_callback(appid: int, parsed_pages: int | str):
    max_pages_display = (
        MAX_NUMERIC_REVIEW_PAGES if parsed_pages == "all" else int(parsed_pages)
    )

    def _callback(progress: dict[str, Any]) -> None:
        current_page = int(progress.get("page", 0))
        cumulative = int(progress.get("cumulative_unique_reviews", 0))
        page_count = int(progress.get("page_review_count", 0))
        page_new = int(progress.get("page_new_unique_reviews", 0))
        print(
            "[offline-pipeline] fetch-progress "
            f"appid={appid} "
            f"page={current_page}/{max_pages_display} "
            f"page_reviews={page_count} "
            f"new_unique={page_new} "
            f"cumulative_unique={cumulative}"
        )

    return _callback

