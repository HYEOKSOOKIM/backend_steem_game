"""Manual offline pipeline runner for one Steam appid."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_ROOT = BACKEND_DIR / "data" / "report"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.pipeline.offline_pipeline import run_offline_pipeline_for_appid


def _load_env() -> None:
    """Load environment variables from common .env locations."""
    for path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)


def _print_precheck(*, use_llm_fallback: bool) -> None:
    """Print one-line runtime precheck for LLM settings."""
    key_status = "set" if bool(os.getenv("OPENAI_API_KEY")) else "missing"
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(
        f"[offline-pipeline] precheck: llm_requested={use_llm_fallback} "
        f"openai_key={key_status} model={model}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run offline ingestion + preprocessing + analysis for one appid."
    )
    parser.add_argument("--appid", type=int, required=True, help="Steam appid")
    parser.add_argument(
        "--review-pages",
        default="all",
        help="all or an integer between 1 and 200",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Result data root directory (default: backend/data/report)",
    )
    parser.add_argument(
        "--use-llm-fallback",
        action="store_true",
        help="Enable selective LLM fallback for ambiguous review subset",
    )
    parser.add_argument(
        "--max-llm-reviews",
        type=int,
        default=50,
        help="Maximum reviews passed to LLM fallback",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=int,
        default=20,
        help="Timeout seconds for each LLM call",
    )
    parser.add_argument(
        "--llm-retry-limit",
        type=int,
        default=2,
        help="Retry limit for each LLM call",
    )
    parser.add_argument(
        "--llm-min-confidence",
        type=float,
        default=0.70,
        help="Minimum confidence required to accept LLM output",
    )
    parser.add_argument(
        "--game-name",
        default=None,
        help="Optional override name used when Steam game name is missing",
    )
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    _print_precheck(use_llm_fallback=bool(args.use_llm_fallback))
    try:
        summary = run_offline_pipeline_for_appid(
            args.appid,
            data_root=args.data_root if args.data_root else DEFAULT_DATA_ROOT,
            review_pages=args.review_pages,
            use_llm_fallback=bool(args.use_llm_fallback),
            max_llm_reviews=args.max_llm_reviews,
            llm_timeout_seconds=args.llm_timeout_seconds,
            llm_retry_limit=args.llm_retry_limit,
            llm_min_confidence=args.llm_min_confidence,
            game_name=args.game_name,
            log_fetch_progress=True,
        )
    except Exception as exc:  # pragma: no cover - CLI surface.
        print(f"[offline-pipeline] failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI surface.
    raise SystemExit(main())
