"""Check normalization gate and emit rollback requirement on failure."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def aggregate_counts(report: dict[str, Any]) -> tuple[int, int]:
    included = 0
    unclassified = 0
    for row in report.get("summary_records", []):
        included += int(row.get("included_review_count", 0))
        unclassified += int(row.get("unclassified_included_count", 0))
    return included, unclassified


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check normalization gate using two batch quality reports.",
    )
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline report JSON path.")
    parser.add_argument("--current", type=Path, required=True, help="Current report JSON path.")
    parser.add_argument(
        "--max-included-drop-rate",
        type=float,
        default=0.10,
        help="Maximum allowed included_count drop rate (default: 0.10).",
    )
    parser.add_argument(
        "--require-unc-improvement",
        action="store_true",
        default=True,
        help="Require unclassified ratio improvement (default: enabled).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/report/reports/normalization_gate_result.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit non-zero when gate fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    baseline = load_report(args.baseline)
    current = load_report(args.current)

    baseline_included, baseline_unclassified = aggregate_counts(baseline)
    current_included, current_unclassified = aggregate_counts(current)

    included_drop_rate = safe_ratio(
        baseline_included - current_included,
        baseline_included,
    )
    baseline_unc_ratio = safe_ratio(baseline_unclassified, baseline_included)
    current_unc_ratio = safe_ratio(current_unclassified, current_included)
    unc_ratio_delta = current_unc_ratio - baseline_unc_ratio

    cond_included = included_drop_rate <= args.max_included_drop_rate
    cond_unc = (unc_ratio_delta < 0.0) if args.require_unc_improvement else True
    gate_pass = cond_included and cond_unc

    result = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "baseline_path": str(args.baseline),
        "current_path": str(args.current),
        "thresholds": {
            "max_included_drop_rate": args.max_included_drop_rate,
            "require_unc_improvement": args.require_unc_improvement,
        },
        "metrics": {
            "baseline_included_count": baseline_included,
            "current_included_count": current_included,
            "included_drop_rate": round(included_drop_rate, 4),
            "baseline_unclassified_ratio": round(baseline_unc_ratio, 4),
            "current_unclassified_ratio": round(current_unc_ratio, 4),
            "unc_ratio_delta": round(unc_ratio_delta, 4),
        },
        "gate": {
            "included_drop_pass": cond_included,
            "unc_improvement_pass": cond_unc,
            "gate_pass": gate_pass,
        },
        "rollback": {
            "required": not gate_pass,
            "baseline_restore_source": str(args.baseline),
            "criteria": "included_drop_rate > threshold OR unc_ratio_delta >= 0",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(args.output), "gate_pass": gate_pass}, ensure_ascii=False))

    if args.fail_on_gate and not gate_pass:
        sys.exit(2)


if __name__ == "__main__":
    main()

