"""Export fixed top unclassified samples by bucket for normalization loops."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"
LEGACY_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_OUTPUT_PATH = DATA_DIR / "reports" / "fixed_unclassified_samples.json"

DEFAULT_COHORT: list[dict[str, Any]] = [
    {"appid": 1091500, "game_name": "사이버펑크 2077", "primary_bucket": "RPG / 스토리 중심"},
    {"appid": 1174180, "game_name": "레드 데드 리뎀션 2", "primary_bucket": "RPG / 스토리 중심"},
    {"appid": 1222670, "game_name": "더 심즈 4", "primary_bucket": "시뮬레이션 / 라이프심"},
    {"appid": 252490, "game_name": "러스트", "primary_bucket": "생존 / 제작 / 샌드박스"},
    {"appid": 230410, "game_name": "워프레임", "primary_bucket": "액션 / 슈터"},
    {"appid": 1145350, "game_name": "하데스 II", "primary_bucket": "로그라이크 / 로그라이트"},
    {"appid": 381210, "game_name": "데드 바이 데이라이트", "primary_bucket": "호러 / 긴장감 중심"},
    {"appid": 275850, "game_name": "노 맨즈 스카이", "primary_bucket": "생존 / 제작 / 샌드박스"},
]


def resolve_latest_file(section_dir: Path, appid: int) -> Path:
    exact = section_dir / f"{appid}.json"
    if exact.exists():
        return exact

    named = sorted(
        path
        for path in section_dir.glob("*.json")
        if path.name.startswith(f"{appid}(") and path.name.endswith(".json")
    )
    if named:
        return max(named, key=lambda path: path.stat().st_mtime)

    loose = sorted(section_dir.glob(f"{appid}*.json"))
    if loose:
        return max(loose, key=lambda path: path.stat().st_mtime)

    raise FileNotFoundError(f"processed file not found for appid {appid}")


def load_processed(appid: int) -> tuple[Path, list[dict[str, Any]]]:
    path = None
    for processed_dir in (DATA_DIR / "processed", LEGACY_DATA_DIR / "processed"):
        try:
            path = resolve_latest_file(processed_dir, appid)
            break
        except FileNotFoundError:
            continue
    if path is None:
        raise FileNotFoundError(f"processed file not found for appid {appid}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return path, data


def resolve_game_name(appid: int) -> str:
    """Resolve a readable game name from metadata filename or payload."""
    path = None
    for metadata_dir in (DATA_DIR / "metadata", LEGACY_DATA_DIR / "metadata"):
        try:
            path = resolve_latest_file(metadata_dir, appid)
            break
        except FileNotFoundError:
            continue
    if path is None:
        return str(appid)

    stem = path.stem
    prefix = f"{appid}("
    if stem.startswith(prefix) and stem.endswith(")"):
        name_in_file = stem[len(prefix):-1].strip()
        if name_in_file:
            return name_in_file

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        name = str(payload.get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass

    return str(appid)


def build_bucket_samples(cohort: list[dict[str, Any]], top_k: int) -> dict[str, list[dict[str, Any]]]:
    bucket_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for game in cohort:
        appid = int(game["appid"])
        game_name = str(game["game_name"])
        bucket = str(game["primary_bucket"])
        _path, processed = load_processed(appid)

        for row in processed:
            if not row.get("included_in_analysis"):
                continue
            if row.get("category_tags"):
                continue
            text = (row.get("normalized_text") or row.get("review_text") or "").strip()
            if not text:
                continue
            bucket_rows[bucket].append(
                {
                    "appid": appid,
                    "game_name": game_name,
                    "review_id": row.get("review_id"),
                    "text": text,
                    "ambiguity_flags": list(row.get("ambiguity_flags") or []),
                }
            )

    bucket_samples: dict[str, list[dict[str, Any]]] = {}
    for bucket, rows in bucket_rows.items():
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row["text"]
            entry = grouped.get(key)
            if entry is None:
                grouped[key] = {"count": 1, "sample": row}
            else:
                entry["count"] += 1

        ranked = sorted(
            grouped.values(),
            key=lambda item: (-item["count"], str(item["sample"]["review_id"])),
        )[:top_k]

        bucket_samples[bucket] = [
            {
                "count": item["count"],
                **item["sample"],
            }
            for item in ranked
        ]

    return bucket_samples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export fixed top unclassified samples by bucket.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Top unclassified samples per bucket (default: 20).",
    )
    parser.add_argument(
        "--appids",
        type=int,
        nargs="*",
        help="Optional explicit appids to filter the default cohort.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cohort = list(DEFAULT_COHORT)

    if args.appids:
        index = {int(item["appid"]): item for item in DEFAULT_COHORT}
        resolved: list[dict[str, Any]] = []
        for appid in args.appids:
            item = index.get(int(appid))
            if item is not None:
                resolved.append(dict(item))
                continue
            resolved.append(
                {
                    "appid": int(appid),
                    "game_name": resolve_game_name(int(appid)),
                    "primary_bucket": "미분류",
                }
            )
        cohort = resolved

    output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "top_k": args.top_k,
        "cohort_size": len(cohort),
        "cohort": cohort,
        "bucket_samples": build_bucket_samples(cohort, top_k=args.top_k),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(args.output), "cohort_size": len(cohort)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
