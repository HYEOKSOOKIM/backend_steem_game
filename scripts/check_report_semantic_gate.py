"""Run deterministic semantic QA over generated report payloads."""

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

from report.quality import evaluate_report_semantics


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_payload_path(kind: str, appid: int) -> Path | None:
    root = DATA_DIR / kind
    exact = root / f"{appid}.json"
    if exact.exists():
        return exact
    named = sorted(
        path
        for path in root.glob("*.json")
        if path.name.startswith(f"{appid}(") and path.name.endswith(".json")
    )
    if named:
        return max(named, key=lambda path: path.stat().st_mtime)
    loose = sorted(root.glob(f"{appid}*.json"))
    if loose:
        return max(loose, key=lambda path: path.stat().st_mtime)
    return None


def evaluate_appid(appid: int) -> dict[str, Any]:
    report_path = resolve_payload_path("report", appid)
    analysis_path = resolve_payload_path("analysis", appid)
    if report_path is None:
        return {
            "appid": appid,
            "status": "missing_report",
            "report_path": None,
            "failure_count": 1,
            "critical_failure_count": 1,
            "failures": [
                {
                    "type": "missing_report",
                    "severity": "critical",
                    "message": "report payload file was not found.",
                }
            ],
        }

    report_payload = load_json(report_path)
    analysis_payload = load_json(analysis_path) if analysis_path is not None else None
    result = evaluate_report_semantics(report_payload, analysis_payload=analysis_payload)
    result.update(
        {
            "appid": appid,
            "game_name": str((report_payload.get("game", {}) or {}).get("name", "")),
            "report_path": str(report_path.relative_to(BACKEND_DIR)),
            "analysis_path": str(analysis_path.relative_to(BACKEND_DIR)) if analysis_path else None,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appids", nargs="+", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "reports" / "report_semantic_gate.json",
    )
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    rows = [evaluate_appid(appid) for appid in args.appids]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "appids": list(args.appids),
        "fail_count": sum(1 for row in rows if row.get("status") == "fail"),
        "warn_count": sum(1 for row in rows if row.get("status") == "warn"),
        "pass_count": sum(1 for row in rows if row.get("status") == "pass"),
        "rows": rows,
    }
    write_json(args.output, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.fail_on_error and payload["fail_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
