"""Build dry-run repair plans from semantic report QA failures."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.quality.repair import apply_safe_repair_actions, build_repair_plan


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


def plan_appid(appid: int, *, apply_safe_only: bool = False) -> dict[str, Any]:
    report_path = resolve_report_path(appid)
    if report_path is None:
        return {
            "appid": appid,
            "status": "missing_report",
            "can_apply_safely": False,
            "actions": [],
            "holds": [
                {
                    "hold_type": "missing_report",
                    "reason": "report payload file was not found.",
                }
            ],
        }
    report_payload = load_json(report_path)
    plan = build_repair_plan(report_payload)
    apply_summary = {
        "applied_count": 0,
        "skipped_count": 0,
        "applied": [],
        "skipped": [],
    }
    mode = "dry_run"
    if apply_safe_only:
        next_payload, apply_summary = apply_safe_repair_actions(report_payload, plan)
        if apply_summary.get("applied_count", 0):
            write_json(report_path, next_payload)
            plan = build_repair_plan(next_payload)
        mode = "safe_only_apply"

    plan.update(
        {
            "appid": appid,
            "game_name": str((report_payload.get("game", {}) or {}).get("name", "")),
            "report_path": str(report_path.relative_to(BACKEND_DIR)),
            "mode": mode,
            "safe_apply": apply_summary,
        }
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appids", nargs="+", type=int, required=True)
    parser.add_argument(
        "--apply-safe-only",
        action="store_true",
        help="Apply only deterministic safe actions, currently duplicate evidence block drops.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "reports" / "report_repair_plan.json",
    )
    args = parser.parse_args()

    rows = [plan_appid(appid, apply_safe_only=args.apply_safe_only) for appid in args.appids]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "safe_only_apply" if args.apply_safe_only else "dry_run",
        "appids": list(args.appids),
        "safe_applied_count": sum(int((row.get("safe_apply") or {}).get("applied_count", 0) or 0) for row in rows),
        "repairable_count": sum(1 for row in rows if row.get("status") == "repairable"),
        "repairable_needs_review_count": sum(1 for row in rows if row.get("status") == "repairable_needs_review"),
        "repairable_with_holds_count": sum(1 for row in rows if row.get("status") == "repairable_with_holds"),
        "hold_count": sum(1 for row in rows if row.get("status") == "hold"),
        "rows": rows,
    }
    write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
