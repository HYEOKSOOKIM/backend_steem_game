"""File-backed job service for report generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from report.api.dto_report_v1 import ReportV1DTO
from report.pipeline.offline_pipeline import run_offline_pipeline_for_appid
from report.storage.file_store import FileStore

_JOB_LOCK = Lock()
_ACTIVE_JOB_STATUSES = {"queued", "running"}
_JOB_STORE_SCHEMA_VERSION = "report.jobs.v1"
_INTERRUPTED_JOB_ERROR_CODE = "interrupted_by_restart"
_REQUIRED_SNAPSHOT_FIELD_PATHS: tuple[tuple[str, ...], ...] = (
    ("schema_version",),
    ("app_id",),
    ("snapshot_at",),
    ("window_days",),
    ("data_quality",),
    ("data_quality", "review_count_total"),
    ("data_quality", "review_count_eligible"),
    ("snapshot",),
    ("snapshot", "decision_label"),
    ("snapshot", "decision_score"),
    ("snapshot", "decision_confidence"),
    ("category_distribution",),
    ("sentiment_x_category",),
    ("top_themes",),
    ("evidence_blocks",),
    ("trend",),
    ("trend", "summary"),
    ("trend", "summary", "direction"),
    ("reviewer_segment",),
    ("final_recommendation",),
    ("final_recommendation", "label"),
    ("final_recommendation", "reason_summary"),
    ("final_recommendation", "inputs"),
    ("final_recommendation", "inputs", "risk_index"),
    ("final_recommendation", "inputs", "confidence"),
    ("final_recommendation", "inputs", "trend_direction"),
)
_JOB_STORES_BY_ROOT: dict[str, dict[str, dict[str, Any]]] = {}
_JOB_STORE_LOADED_ROOTS: set[str] = set()


def create_report_job(
    payload: dict[str, Any],
    *,
    data_root: str,
) -> dict[str, Any]:
    """Create a queued job.

    Concurrency policy:
    - Only one active job (`queued`/`running`) is allowed per appid.
    - If an active job already exists for the same appid, return that job with `is_existing=True`.
    """
    appid = payload.get("appid")
    if not isinstance(appid, int):
        raise ValueError("appid must be provided as an integer.")

    normalized_root = _normalize_data_root(data_root)
    job_id = uuid4().hex
    now = _now_iso()
    params = {
        "appid": appid,
        "review_pages": payload.get("review_pages", "all"),
        "use_llm_fallback": bool(payload.get("use_llm_fallback", False)),
        "max_llm_reviews": int(payload.get("max_llm_reviews", 50)),
        "llm_timeout_seconds": int(payload.get("llm_timeout_seconds", 20)),
        "llm_retry_limit": int(payload.get("llm_retry_limit", 2)),
        "llm_min_confidence": float(payload.get("llm_min_confidence", 0.70)),
        "game_name": payload.get("game_name"),
        "data_root": normalized_root,
    }

    with _JOB_LOCK:
        _load_job_store_for_root_unlocked(normalized_root)
        existing = _find_active_job_for_appid_unlocked(appid, normalized_root)
        if existing is not None:
            snapshot = _normalize_job_snapshot(dict(existing))
            snapshot["is_existing"] = True
            return snapshot

        root_store = _JOB_STORES_BY_ROOT.setdefault(normalized_root, {})
        root_store[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "error_code": None,
            "error_message": None,
            "params": params,
            "result": None,
        }
        _persist_job_store_for_root_unlocked(normalized_root)

    created = get_report_job(job_id, data_root=normalized_root)
    created["is_existing"] = False
    return created


def get_report_job(job_id: str, *, data_root: str | None = None) -> dict[str, Any]:
    """Return one job snapshot."""
    normalized_root = _normalize_data_root(data_root) if data_root is not None else None
    with _JOB_LOCK:
        if normalized_root is not None:
            _load_job_store_for_root_unlocked(normalized_root)
        _, job = _find_job_by_id_unlocked(job_id)
        if job is None:
            raise ValueError(f"job_id {job_id} was not found.")
        return _normalize_job_snapshot(dict(job))


def run_report_job(job_id: str) -> None:
    """Execute one report job and update status."""
    with _JOB_LOCK:
        root_key, job = _find_job_by_id_unlocked(job_id)
        if job is None or root_key is None:
            return
        job["status"] = "running"
        job["progress"] = 10
        job["started_at"] = _now_iso()
        params = dict(job.get("params", {}))
        _persist_job_store_for_root_unlocked(root_key)

    try:
        result = run_offline_pipeline_for_appid(
            int(params["appid"]),
            data_root=str(params["data_root"]),
            review_pages=params["review_pages"],
            use_llm_fallback=bool(params["use_llm_fallback"]),
            max_llm_reviews=int(params["max_llm_reviews"]),
            llm_timeout_seconds=int(params["llm_timeout_seconds"]),
            llm_retry_limit=int(params["llm_retry_limit"]),
            llm_min_confidence=float(params["llm_min_confidence"]),
            game_name=params.get("game_name"),
        )
    except Exception as exc:  # pragma: no cover - failure path is runtime-dependent.
        _mark_job_failed(
            job_id,
            error_code="pipeline_runtime_error",
            error_message=str(exc),
        )
        return

    appid = int(params["appid"])
    _update_job_progress(job_id, progress=80)

    try:
        snapshot_payload = _read_report_snapshot_payload(str(params["data_root"]), appid)
    except FileNotFoundError:
        _mark_job_failed(
            job_id,
            error_code="snapshot_missing",
            error_message=f"report_snapshot for appid {appid} was not found after pipeline completion.",
        )
        return

    missing_field = _find_missing_required_snapshot_field(snapshot_payload)
    if missing_field is not None:
        _mark_job_failed(
            job_id,
            error_code="snapshot_required_missing",
            error_message=f"required snapshot field is missing: {missing_field}",
        )
        return

    try:
        validated_snapshot = ReportV1DTO.model_validate(snapshot_payload)
    except ValidationError as exc:
        _mark_job_failed(
            job_id,
            error_code="snapshot_invalid",
            error_message=_format_validation_error(exc),
        )
        return

    if int(validated_snapshot.app_id) != appid:
        _mark_job_failed(
            job_id,
            error_code="snapshot_invalid",
            error_message=f"snapshot app_id mismatch: expected {appid}, got {validated_snapshot.app_id}.",
        )
        return

    finished_at = _now_iso()
    snapshot_path = _resolve_snapshot_path(str(params["data_root"]), appid)
    standardized_result = {
        "app_id": appid,
        "pipeline_run_id": result.get("pipeline_run_id"),
        "snapshot_schema": str(validated_snapshot.schema_version),
        "snapshot_path": snapshot_path,
        "finished_at": finished_at,
        "raw_review_count": int(result.get("raw_review_count", 0)),
        "processed_review_count": int(result.get("processed_review_count", 0)),
        "included_review_count": int(result.get("included_review_count", 0)),
    }

    with _JOB_LOCK:
        root_key, current = _find_job_by_id_unlocked(job_id)
        if current is None or root_key is None:
            return
        current["status"] = "succeeded"
        current["progress"] = 100
        current["finished_at"] = finished_at
        current["error_code"] = None
        current["error_message"] = None
        current["result"] = standardized_result
        _persist_job_store_for_root_unlocked(root_key)


def _find_active_job_for_appid_unlocked(appid: int, data_root: str) -> dict[str, Any] | None:
    root_store = _JOB_STORES_BY_ROOT.get(data_root, {})
    for job in root_store.values():
        params = job.get("params", {})
        if not isinstance(params, dict):
            continue
        if int(params.get("appid", -1)) != appid:
            continue
        if str(job.get("status")) not in _ACTIVE_JOB_STATUSES:
            continue
        return job
    return None


def _find_job_by_id_unlocked(job_id: str) -> tuple[str | None, dict[str, Any] | None]:
    for root_key, root_store in _JOB_STORES_BY_ROOT.items():
        job = root_store.get(job_id)
        if job is not None:
            return root_key, job
    return None, None


def _load_job_store_for_root_unlocked(data_root: str) -> None:
    if data_root in _JOB_STORE_LOADED_ROOTS:
        return

    store = FileStore(data_root)
    jobs_payload: dict[str, Any] = {}
    try:
        stored = store.read_report_jobs()
        if isinstance(stored, dict):
            raw_jobs = stored.get("jobs", {})
            if isinstance(raw_jobs, dict):
                jobs_payload = raw_jobs
    except FileNotFoundError:
        jobs_payload = {}

    normalized_jobs: dict[str, dict[str, Any]] = {}
    has_recovered_jobs = False
    for raw_job_id, raw_job in jobs_payload.items():
        if not isinstance(raw_job, dict):
            continue
        normalized = dict(raw_job)
        normalized["job_id"] = str(normalized.get("job_id") or raw_job_id)
        normalized_params = normalized.get("params", {})
        if not isinstance(normalized_params, dict):
            normalized_params = {}
        normalized_params["data_root"] = data_root
        normalized["params"] = normalized_params
        normalized = _normalize_job_snapshot(normalized)
        if _should_recover_interrupted_job(normalized):
            _mark_recovered_interrupted_job(normalized)
            has_recovered_jobs = True
        normalized_jobs[str(raw_job_id)] = normalized

    _JOB_STORES_BY_ROOT[data_root] = normalized_jobs
    _JOB_STORE_LOADED_ROOTS.add(data_root)
    if has_recovered_jobs:
        _persist_job_store_for_root_unlocked(data_root)


def _persist_job_store_for_root_unlocked(data_root: str) -> None:
    store = FileStore(data_root)
    payload = {
        "schema_version": _JOB_STORE_SCHEMA_VERSION,
        "saved_at": _now_iso(),
        "jobs": _JOB_STORES_BY_ROOT.get(data_root, {}),
    }
    store.write_report_jobs(payload)


def _resolve_snapshot_path(data_root: str, appid: int) -> str | None:
    base = Path(data_root) / "report_snapshot"
    if not base.exists():
        return None
    candidates = sorted(
        base.glob(f"{appid}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return str(candidates[0])


def _read_report_snapshot_payload(data_root: str, appid: int) -> dict[str, Any]:
    store = FileStore(data_root)
    payload = store.read_report_snapshot(appid)
    if not isinstance(payload, dict):
        raise FileNotFoundError("report_snapshot payload is not an object")
    return payload


def _format_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "snapshot schema validation failed."
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", []))
    message = str(first.get("msg", "invalid value"))
    if location:
        return f"{location}: {message}"
    return message


def _mark_job_failed(job_id: str, *, error_code: str, error_message: str) -> None:
    finished_at = _now_iso()
    with _JOB_LOCK:
        root_key, current = _find_job_by_id_unlocked(job_id)
        if current is None or root_key is None:
            return
        current["status"] = "failed"
        current["progress"] = 100
        current["finished_at"] = finished_at
        current["error_code"] = error_code
        current["error_message"] = error_message
        current["result"] = None
        _persist_job_store_for_root_unlocked(root_key)


def _update_job_progress(job_id: str, *, progress: int) -> None:
    with _JOB_LOCK:
        root_key, current = _find_job_by_id_unlocked(job_id)
        if current is None or root_key is None:
            return
        current["progress"] = max(0, min(100, int(progress)))
        _persist_job_store_for_root_unlocked(root_key)


def _normalize_job_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    job.setdefault("progress", 0)
    job.setdefault("started_at", None)
    job.setdefault("finished_at", None)
    job.setdefault("error_code", None)
    job.setdefault("error_message", None)
    job.setdefault("result", None)
    return job


def _normalize_data_root(data_root: str | Path) -> str:
    return str(Path(data_root))


def _find_missing_required_snapshot_field(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "root"
    for field_path in _REQUIRED_SNAPSHOT_FIELD_PATHS:
        value, found = _try_get_nested_field(payload, field_path)
        if not found:
            return ".".join(field_path)
        if value is None:
            return ".".join(field_path)
        if isinstance(value, str) and not value.strip():
            return ".".join(field_path)
    return None


def _try_get_nested_field(payload: dict[str, Any], field_path: tuple[str, ...]) -> tuple[Any, bool]:
    current: Any = payload
    for key in field_path:
        if not isinstance(current, dict):
            return None, False
        if key not in current:
            return None, False
        current = current[key]
    return current, True


def _should_recover_interrupted_job(job: dict[str, Any]) -> bool:
    return str(job.get("status")) in _ACTIVE_JOB_STATUSES


def _mark_recovered_interrupted_job(job: dict[str, Any]) -> None:
    job["status"] = "failed"
    job["progress"] = 100
    job["finished_at"] = _now_iso()
    job["error_code"] = _INTERRUPTED_JOB_ERROR_CODE
    job["error_message"] = "job was interrupted by server restart before completion."
    job["result"] = None


def _clear_job_store_cache_for_test() -> None:
    """Reset in-memory caches for deterministic tests."""
    with _JOB_LOCK:
        _JOB_STORES_BY_ROOT.clear()
        _JOB_STORE_LOADED_ROOTS.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
