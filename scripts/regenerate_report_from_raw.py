"""Regenerate analysis/report artifacts from stored raw reviews."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_ROOT = BACKEND_DIR / "data" / "report"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.analysis.preprocess import preprocess_reviews
from report.models.schemas import GameMetadata, RawReview
from report.services.analysis_service import (
    build_analysis_result_from_processed,
    enrich_processed_reviews,
)
from report.services.demo_catalog import upsert_demo_game
from report.services.report_material_refiner import (
    OpenAIReportMaterialRefiner,
    ReportMaterialRefinerConfig,
    build_report_materials,
)
from report.services.report_view import build_report_ready_data
from report.storage.file_store import FileStore
from scripts.run_report_slot_repair import repair_appid
from report.services.slot_repair_llm import OpenAISlotRepairer


def _load_env() -> None:
    for path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)


def _model_preset_env(stage: str | None) -> dict[str, str]:
    normalized = str(stage or "").strip().lower()
    if not normalized:
        return {}
    if normalized == "qa":
        model = "gpt-4o-mini"
    elif normalized == "final":
        model = "gpt-4.1-mini"
    else:
        raise ValueError("llm-stage must be one of: qa, final")
    return {
        "OPENAI_MODEL": model,
        "OPENAI_REPORT_PLAN_MODEL": model,
        "OPENAI_REPORT_DISPLAY_MODEL": model,
        "OPENAI_REPORT_PROOFREADER_MODEL": model,
        "OPENAI_EVIDENCE_JUDGE_MODEL": model,
    }


@contextmanager
def _temporary_env(overrides: dict[str, str]):
    previous: dict[str, str | None] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _raw_review_from_dict(item: dict[str, Any], *, appid: int) -> RawReview:
    return RawReview(
        review_id=str(item.get("review_id", "")),
        appid=int(item.get("appid", appid) or appid),
        review_text=str(item.get("review_text", "") or ""),
        voted_up=bool(item.get("voted_up", False)),
        timestamp_created=int(item.get("timestamp_created", 0) or 0),
        timestamp_updated=(
            int(item["timestamp_updated"])
            if item.get("timestamp_updated") is not None
            else None
        ),
        playtime_forever=_float_or_none(item.get("playtime_forever")),
        playtime_at_review_hours=_float_or_none(item.get("playtime_at_review_hours")),
        num_reviews=_int_or_none(item.get("num_reviews")),
        author_steamid=str(item.get("author_steamid")) if item.get("author_steamid") else None,
    )


def _metadata_from_dict(item: dict[str, Any], *, appid: int) -> GameMetadata:
    allowed = set(GameMetadata.__dataclass_fields__.keys())
    payload = {key: value for key, value in dict(item or {}).items() if key in allowed}
    payload["appid"] = appid
    return GameMetadata(**payload)


def regenerate_from_raw(
    appid: int,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    use_llm_fallback: bool = True,
    max_llm_reviews: int = 50,
    llm_timeout_seconds: int = 20,
    llm_retry_limit: int = 2,
    llm_min_confidence: float = 0.70,
    auto_slot_repair: bool = True,
    slot_repair_max_rounds: int = 2,
) -> dict[str, Any]:
    store = FileStore(data_root)
    raw_payload = store.read_raw_reviews(appid)
    metadata_payload = store.read_game_metadata(appid)
    raw_reviews = [
        _raw_review_from_dict(item, appid=appid)
        for item in list(raw_payload or [])
        if isinstance(item, dict)
    ]
    metadata = _metadata_from_dict(metadata_payload, appid=appid)
    pipeline_run_id = f"{appid}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-raw"

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
        config = ReportMaterialRefinerConfig(
            enabled=True,
            max_llm_reviews=max_llm_reviews,
            timeout_seconds=llm_timeout_seconds,
            retry_limit=llm_retry_limit,
            min_confidence=llm_min_confidence,
        )
        report_materials, stats = build_report_materials(
            processed_reviews,
            analysis=analysis,
            config=config,
            refiner=OpenAIReportMaterialRefiner(),
        )
        llm_stats = stats.to_dict()

    analysis_payload = analysis.to_dict()
    analysis_payload.update(
        {
            "pipeline_run_id": pipeline_run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_review_count": len(raw_reviews),
            "review_pages": "stored_raw",
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

    game_name = metadata.name
    store.write_processed_reviews(appid, [review.to_dict() for review in processed_reviews], game_name=game_name)
    store.write_analysis_result(appid, analysis_payload, game_name=game_name)
    store.write_report_view(appid, report_view, game_name=game_name)
    upsert_demo_game(
        Path(data_root) / "catalog" / "demo_games.json",
        appid=appid,
        name=game_name or f"appid-{appid}",
        name_en=metadata.name_en,
        name_ko=metadata.name_ko,
        enabled_for_demo=True,
    )

    slot_repair_summary = None
    if auto_slot_repair:
        repairer = OpenAISlotRepairer()
        if not repairer.available:
            repairer = None
        slot_repair_summary = repair_appid(
            appid,
            max_rounds=max(1, int(slot_repair_max_rounds)),
            repairer=repairer,
        )

    return {
        "appid": appid,
        "pipeline_run_id": pipeline_run_id,
        "raw_review_count": len(raw_reviews),
        "processed_review_count": len(processed_reviews),
        "included_review_count": sum(1 for review in processed_reviews if review.included_in_analysis),
        "review_pages": "stored_raw",
        "llm_stats": llm_stats,
        "report_material_count": len(report_materials),
        "output_file_game_name": game_name,
        "catalog_updated": True,
        "slot_repair": slot_repair_summary,
        "semantic_status_after_repair": (
            slot_repair_summary.get("status_after")
            if isinstance(slot_repair_summary, dict)
            else None
        ),
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appid", type=int, required=True)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--use-llm-fallback", action="store_true")
    parser.add_argument("--max-llm-reviews", type=int, default=50)
    parser.add_argument("--llm-timeout-seconds", type=int, default=20)
    parser.add_argument("--llm-retry-limit", type=int, default=2)
    parser.add_argument("--llm-min-confidence", type=float, default=0.70)
    parser.add_argument("--llm-stage", choices=("qa", "final"), default=None)
    parser.add_argument("--no-auto-slot-repair", action="store_true")
    parser.add_argument("--slot-repair-max-rounds", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    env_overrides = _model_preset_env(args.llm_stage)
    with _temporary_env(env_overrides):
        summary = regenerate_from_raw(
            args.appid,
            data_root=args.data_root if args.data_root else DEFAULT_DATA_ROOT,
            use_llm_fallback=bool(args.use_llm_fallback),
            max_llm_reviews=int(args.max_llm_reviews),
            llm_timeout_seconds=int(args.llm_timeout_seconds),
            llm_retry_limit=int(args.llm_retry_limit),
            llm_min_confidence=float(args.llm_min_confidence),
            auto_slot_repair=not bool(args.no_auto_slot_repair),
            slot_repair_max_rounds=int(args.slot_repair_max_rounds),
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
