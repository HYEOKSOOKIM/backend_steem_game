"""Run slot-level repair on QA-failed reports without full regeneration."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality.repair import (
    apply_review_repair_actions,
    apply_safe_repair_actions,
    build_repair_plan,
)
from report.quality.semantic_gate import evaluate_report_semantics
from report.services.slot_repair_llm import OpenAISlotRepairer


def _load_env() -> None:
    for path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_report_path(appid: int) -> Path | None:
    report_dir = DATA_DIR / "report"
    exact = report_dir / f"{appid}.json"
    if exact.exists():
        return exact
    named = sorted(
        path
        for path in report_dir.glob("*.json")
        if path.name.startswith(f"{appid}(") and path.name.endswith(".json")
    )
    if named:
        return max(named, key=lambda path: path.stat().st_mtime)
    loose = sorted(report_dir.glob(f"{appid}*.json"))
    if loose:
        return max(loose, key=lambda path: path.stat().st_mtime)
    return None


def repair_appid(
    appid: int,
    *,
    max_rounds: int,
    repairer: OpenAISlotRepairer | None,
) -> dict[str, Any]:
    report_path = resolve_report_path(appid)
    if report_path is None:
        return {
            "appid": appid,
            "status_before": "missing_report",
            "status_after": "missing_report",
            "rounds_completed": 0,
            "report_path": None,
        }

    payload = load_json(report_path)
    initial_result = evaluate_report_semantics(payload)
    before = initial_result
    round_summaries: list[dict[str, Any]] = []

    for round_index in range(1, max_rounds + 1):
        plan = build_repair_plan(payload, semantic_result=before if round_index == 1 else None)
        safe_payload, safe_summary = apply_safe_repair_actions(payload, plan)
        safe_applied = int(safe_summary.get("applied_count", 0) or 0)
        if safe_applied:
            payload = safe_payload
            plan = build_repair_plan(payload)

        review_payload, review_summary = apply_review_repair_actions(
            payload,
            repair_plan=plan,
            llm_repairer=repairer,
        )
        review_applied = int(review_summary.get("applied_count", 0) or 0)
        total_applied = safe_applied + review_applied
        payload = review_payload if review_applied else payload
        after_round = evaluate_report_semantics(payload)
        round_summaries.append(
            {
                "round": round_index,
                "status_before": plan.get("semantic_status"),
                "plan_status": plan.get("status"),
                "safe_applied_count": safe_applied,
                "review_applied_count": review_applied,
                "applied_count": total_applied,
                "status_after": after_round.get("status"),
                "failure_count_after": after_round.get("failure_count"),
                "critical_failure_count_after": after_round.get("critical_failure_count"),
                "review_summary": review_summary,
            }
        )
        before = after_round
        if total_applied <= 0 or after_round.get("status") == "pass":
            break

    write_json(report_path, payload)
    final_result = evaluate_report_semantics(payload)
    return {
        "appid": appid,
        "game_name": str((payload.get("game", {}) or {}).get("name", "")),
        "report_path": str(report_path.relative_to(BACKEND_DIR)),
        "status_before": initial_result.get("status"),
        "status_after": final_result.get("status"),
        "failure_count_after": final_result.get("failure_count"),
        "critical_failure_count_after": final_result.get("critical_failure_count"),
        "rounds_completed": len(round_summaries),
        "rounds": round_summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appids", nargs="+", type=int, required=True)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "reports" / "report_slot_repair.json",
    )
    parser.add_argument("--model", default=None, help="Optional slot repair model override")
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    repairer = OpenAISlotRepairer(model=args.model)
    if repairer is not None and not repairer.available:
        repairer = None

    rows = [
        repair_appid(
            appid,
            max_rounds=max(1, int(args.max_rounds)),
            repairer=repairer,
        )
        for appid in args.appids
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "appids": list(args.appids),
        "model": repairer.model if repairer is not None else None,
        "pass_count": sum(1 for row in rows if row.get("status_after") == "pass"),
        "fail_count": sum(1 for row in rows if row.get("status_after") == "fail"),
        "warn_count": sum(1 for row in rows if row.get("status_after") == "warn"),
        "rows": rows,
    }
    write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
