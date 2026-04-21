"""Generate JSON and Markdown quality reports for normalization benchmark cohorts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"
DEFAULT_OUTPUT_PATH = DATA_DIR / "reports" / "batch_quality_report.json"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


DEFAULT_COHORT: list[dict[str, Any]] = [
    {
        "appid": 1091500,
        "game_name": "사이버펑크 2077",
        "primary_bucket": "RPG / 스토리 중심",
        "secondary_tags": ["정식 출시"],
        "expected_failure_pattern": "감성형 praise와 성능/버그 불만이 한 리뷰 안에 섞이는 경우",
    },
    {
        "appid": 1174180,
        "game_name": "레드 데드 리뎀션 2",
        "primary_bucket": "RPG / 스토리 중심",
        "secondary_tags": ["정식 출시"],
        "expected_failure_pattern": "장문 몰입형 감상에서 실제 이슈와 분위기 praise를 분리하기 어려운 경우",
    },
    {
        "appid": 1222670,
        "game_name": "더 심즈 4",
        "primary_bucket": "시뮬레이션 / 라이프심",
        "secondary_tags": ["정식 출시"],
        "expected_failure_pattern": "커스터마이징, 건축, 생활 콘텐츠 표현이 여러 주제로 동시에 겹치는 경우",
    },
    {
        "appid": 252490,
        "game_name": "러스트",
        "primary_bucket": "생존 / 제작 / 샌드박스",
        "secondary_tags": ["멀티플레이"],
        "expected_failure_pattern": "생존 스트레스, 제작, 레이드, 갈등 표현이 짧고 거칠게 섞이는 경우",
    },
    {
        "appid": 230410,
        "game_name": "워프레임",
        "primary_bucket": "액션 / 슈터",
        "secondary_tags": ["라이브서비스"],
        "expected_failure_pattern": "파밍 praise와 반복 피로감, 운영/업데이트 평가가 함께 나오는 경우",
    },
    {
        "appid": 1145350,
        "game_name": "하데스 II",
        "primary_bucket": "로그라이크 / 로그라이트",
        "secondary_tags": ["얼리액세스"],
        "expected_failure_pattern": "빌드, 반복성, 중독성 praise를 단순 긍정 감상과 구분하기 어려운 경우",
    },
    {
        "appid": 381210,
        "game_name": "데드 바이 데이라이트",
        "primary_bucket": "호러 / 긴장감 중심",
        "secondary_tags": ["멀티플레이", "라이브서비스"],
        "expected_failure_pattern": "짧고 감정적인 리뷰에서 실제 밸런스/매칭 불만을 추출하기 어려운 경우",
    },
    {
        "appid": 275850,
        "game_name": "노 맨즈 스카이",
        "primary_bucket": "생존 / 제작 / 샌드박스",
        "secondary_tags": ["정식 출시"],
        "expected_failure_pattern": "탐험 감상, 콘텐츠 볼륨, 최적화, 반복 플레이 표현이 넓게 섞이는 경우",
    },
]


def load_cohort(appids: list[int] | None = None) -> list[dict[str, Any]]:
    """Load the default cohort, optionally filtered to explicit appids."""
    if not appids:
        return list(DEFAULT_COHORT)

    appid_set = set(appids)
    filtered = [item for item in DEFAULT_COHORT if item["appid"] in appid_set]
    known_appids = {item["appid"] for item in filtered}

    for appid in appids:
        if appid not in known_appids:
            filtered.append(
                {
                    "appid": appid,
                    "game_name": str(appid),
                    "primary_bucket": "미분류",
                    "secondary_tags": [],
                    "expected_failure_pattern": "사용자 지정 appid",
                }
            )

    return filtered


def load_json_file(path: Path) -> Any:
    """Read a UTF-8 encoded JSON file."""
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def normalize_cohort_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one cohort item to the expected report shape."""
    return {
        "appid": int(item["appid"]),
        "game_name": item.get("game_name") or str(item["appid"]),
        "primary_bucket": item.get("primary_bucket") or "미분류",
        "secondary_tags": list(item.get("secondary_tags") or []),
        "expected_failure_pattern": item.get("expected_failure_pattern") or "사용자 지정 appid",
    }


def load_cohort_from_file(cohort_path: Path) -> list[dict[str, Any]]:
    """Load a cohort list from a JSON file."""
    payload = load_json_file(cohort_path)
    items = payload.get("cohort") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("cohort file must contain a JSON list or an object with 'cohort'")
    return [normalize_cohort_item(item) for item in items]


def resolve_cohort(
    appids: list[int] | None = None,
    cohort_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Resolve the report cohort from defaults or a custom JSON file."""
    base_cohort = (
        load_cohort_from_file(cohort_path)
        if cohort_path is not None
        else [normalize_cohort_item(item) for item in DEFAULT_COHORT]
    )

    if not appids:
        return list(base_cohort)

    appid_set = set(appids)
    filtered = [item for item in base_cohort if item["appid"] in appid_set]
    known_appids = {item["appid"] for item in filtered}

    for appid in appids:
        if appid not in known_appids:
            filtered.append(normalize_cohort_item({"appid": appid}))

    return filtered


def load_game_inputs(base_dir: Path, appid: int) -> dict[str, Any]:
    """Load raw, processed, analysis, and metadata files for one game."""
    data_dir = base_dir / "data"
    report_data_dir = data_dir / "report"
    if report_data_dir.exists():
        data_dir = report_data_dir
    elif not data_dir.exists():
        data_dir = base_dir

    def _resolve_section_path(section: str, target_appid: int) -> Path:
        section_dir = data_dir / section
        exact = section_dir / f"{target_appid}.json"
        if exact.exists():
            return exact

        named_candidates = sorted(
            path
            for path in section_dir.glob("*.json")
            if path.name.startswith(f"{target_appid}(") and path.name.endswith(".json")
        )
        if named_candidates:
            return max(named_candidates, key=lambda path: path.stat().st_mtime)

        loose_candidates = sorted(section_dir.glob(f"{target_appid}*.json"))
        if loose_candidates:
            return max(loose_candidates, key=lambda path: path.stat().st_mtime)

        return exact

    paths = {
        "raw": _resolve_section_path("raw", appid),
        "processed": _resolve_section_path("processed", appid),
        "analysis": _resolve_section_path("analysis", appid),
        "metadata": _resolve_section_path("metadata", appid),
    }

    missing_files = [name for name, path in paths.items() if not path.exists()]
    if missing_files:
        return {
            "appid": appid,
            "missing_files": missing_files,
            "paths": {name: str(path) for name, path in paths.items()},
        }

    return {
        "appid": appid,
        "raw": load_json_file(paths["raw"]),
        "processed": load_json_file(paths["processed"]),
        "analysis": load_json_file(paths["analysis"]),
        "metadata": load_json_file(paths["metadata"]),
        "missing_files": [],
        "paths": {name: str(path) for name, path in paths.items()},
    }


def summarize_processed_reviews(processed_reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate counts and counters from processed review records."""
    category_counter: Counter[str] = Counter()
    ambiguity_flag_counter: Counter[str] = Counter()
    counts = {
        "included_review_count": 0,
        "excluded_low_quality_count": 0,
        "excluded_non_korean_count": 0,
        "excluded_profanity_only_count": 0,
        "unclassified_included_count": 0,
        "canonical_theme_missing_count": 0,
        "ambiguity_flagged_count": 0,
    }

    for review in processed_reviews:
        rule_decision = review.get("rule_decision")
        included = bool(review.get("included_in_analysis"))
        category_tags = list(review.get("category_tags") or [])
        canonical_theme = review.get("canonical_theme")
        ambiguity_flags = list(review.get("ambiguity_flags") or [])

        if included:
            counts["included_review_count"] += 1
            category_counter.update(category_tags)

        if rule_decision == "exclude_low_quality":
            counts["excluded_low_quality_count"] += 1
        elif rule_decision == "exclude_non_korean":
            counts["excluded_non_korean_count"] += 1
        elif rule_decision == "exclude_profanity_only":
            counts["excluded_profanity_only_count"] += 1

        if included and not category_tags:
            counts["unclassified_included_count"] += 1

        if included and category_tags and canonical_theme is None:
            counts["canonical_theme_missing_count"] += 1

        if ambiguity_flags:
            counts["ambiguity_flagged_count"] += 1
            ambiguity_flag_counter.update(ambiguity_flags)

    counts["category_counter"] = dict(category_counter)
    counts["ambiguity_flag_counter"] = dict(ambiguity_flag_counter)
    return counts


def safe_ratio(numerator: int, denominator: int) -> float:
    """Return a rounded ratio or 0.0 when the denominator is zero."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def calculate_ratios(
    raw_review_count: int,
    included_review_count: int,
    summary_counts: dict[str, Any],
) -> dict[str, float]:
    """Compute report ratios from aggregate counts."""
    return {
        "included_ratio": safe_ratio(included_review_count, raw_review_count),
        "unclassified_included_ratio": safe_ratio(
            summary_counts["unclassified_included_count"],
            included_review_count,
        ),
        "canonical_theme_missing_ratio": safe_ratio(
            summary_counts["canonical_theme_missing_count"],
            included_review_count,
        ),
        "ambiguity_flagged_ratio": safe_ratio(
            summary_counts["ambiguity_flagged_count"],
            raw_review_count,
        ),
    }


def _sort_reviews_for_samples(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        reviews,
        key=lambda review: (
            int(review.get("timestamp_created") or 0),
            str(review.get("review_id") or ""),
        ),
        reverse=True,
    )


def _project_sample(
    review: dict[str, Any],
    *,
    include_category_tags: bool = False,
    include_hangul_ratio: bool = False,
) -> dict[str, Any]:
    sample = {
        "review_id": str(review.get("review_id")),
        "normalized_text": review.get("normalized_text"),
        "ambiguity_flags": list(review.get("ambiguity_flags") or []),
        "voted_up": review.get("voted_up"),
        "playtime_at_review_hours": review.get("playtime_at_review_hours"),
    }
    if include_category_tags:
        sample["category_tags"] = list(review.get("category_tags") or [])
        sample["canonical_theme"] = review.get("canonical_theme")
    if include_hangul_ratio:
        sample["hangul_ratio"] = review.get("hangul_ratio")
        sample["rule_decision"] = review.get("rule_decision")
    return sample


def extract_sample_reviews(
    processed_reviews: list[dict[str, Any]],
    *,
    unclassified_limit: int = 20,
    theme_missing_limit: int = 15,
    ambiguity_limit: int = 20,
    non_korean_limit: int = 10,
    low_quality_limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Extract representative review samples for key failure modes."""
    ordered_reviews = _sort_reviews_for_samples(processed_reviews)

    unclassified = [
        _project_sample(review)
        for review in ordered_reviews
        if review.get("included_in_analysis") and not (review.get("category_tags") or [])
    ][:unclassified_limit]

    theme_missing = [
        _project_sample(review, include_category_tags=True)
        for review in ordered_reviews
        if review.get("included_in_analysis")
        and (review.get("category_tags") or [])
        and review.get("canonical_theme") is None
    ][:theme_missing_limit]

    ambiguity = [
        _project_sample(review, include_category_tags=True)
        for review in ordered_reviews
        if review.get("ambiguity_flags")
    ][:ambiguity_limit]

    non_korean = [
        _project_sample(review, include_hangul_ratio=True)
        for review in ordered_reviews
        if review.get("rule_decision") == "exclude_non_korean"
    ][:non_korean_limit]

    low_quality = [
        _project_sample(review)
        for review in ordered_reviews
        if review.get("rule_decision") == "exclude_low_quality"
    ][:low_quality_limit]

    return {
        "top_unclassified_samples": unclassified,
        "top_theme_missing_samples": theme_missing,
        "top_ambiguity_samples": ambiguity,
        "top_non_korean_samples": non_korean,
        "top_low_quality_samples": low_quality,
    }


def build_top_categories(
    category_counter: dict[str, int],
    included_review_count: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the top categories with counts and shares."""
    return [
        {
            "category": category,
            "count": count,
            "share": safe_ratio(count, included_review_count),
        }
        for category, count in Counter(category_counter).most_common(limit)
    ]


def build_top_ambiguity_flags(
    ambiguity_flag_counter: dict[str, int],
    raw_review_count: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the top ambiguity flags with counts and shares."""
    return [
        {
            "flag": flag,
            "count": count,
            "share": safe_ratio(count, raw_review_count),
        }
        for flag, count in Counter(ambiguity_flag_counter).most_common(limit)
    ]


def build_notes(summary_record: dict[str, Any]) -> list[str]:
    """Create note messages from agreed threshold rules."""
    notes: list[str] = []
    raw_review_count = int(summary_record.get("raw_review_count") or 0)

    if summary_record.get("all_mode_cap_reached") is True:
        notes.append("부분 수집 상태이므로 해석에 주의 필요")

    if summary_record.get("unclassified_included_ratio", 0.0) >= 0.50:
        notes.append("현재 taxonomy가 게임 표현을 충분히 포착하지 못함")
    elif summary_record.get("unclassified_included_ratio", 0.0) >= 0.30:
        notes.append("카테고리 확장 또는 정규화 사전 보강 필요")

    if summary_record.get("canonical_theme_missing_ratio", 0.0) >= 0.30:
        notes.append("대표 테마 해석 신뢰도가 낮음")
    elif summary_record.get("canonical_theme_missing_ratio", 0.0) >= 0.15:
        notes.append("theme pattern 보강 필요")

    if summary_record.get("ambiguity_flagged_ratio", 0.0) >= 0.40:
        notes.append("ambiguity 기준 재정의 또는 LLM fallback 설계 보강 필요")
    elif summary_record.get("ambiguity_flagged_ratio", 0.0) >= 0.20:
        notes.append("규칙 경계 점검 필요")

    if safe_ratio(summary_record.get("excluded_non_korean_count", 0), raw_review_count) >= 0.10:
        notes.append("한국어 필터 점검 필요")

    if safe_ratio(summary_record.get("excluded_low_quality_count", 0), raw_review_count) >= 0.15:
        notes.append("저품질 규칙 또는 장르 특성 점검 필요")

    if summary_record.get("included_review_count", 0) < 200:
        notes.append("표본 수가 작아 해석에 주의 필요")

    return notes


def build_game_summary_record(
    cohort_item: dict[str, Any],
    game_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one final summary record for a single game."""
    raw_reviews = list(game_inputs["raw"])
    processed_reviews = list(game_inputs["processed"])
    analysis_data = dict(game_inputs["analysis"])
    metadata_data = dict(game_inputs["metadata"])

    raw_review_count = len(raw_reviews)
    summary_counts = summarize_processed_reviews(processed_reviews)
    ratio_fields = calculate_ratios(
        raw_review_count=raw_review_count,
        included_review_count=summary_counts["included_review_count"],
        summary_counts=summary_counts,
    )
    sample_reviews = extract_sample_reviews(processed_reviews)
    top_categories = build_top_categories(
        summary_counts["category_counter"],
        summary_counts["included_review_count"],
    )
    top_ambiguity_flags = build_top_ambiguity_flags(
        summary_counts["ambiguity_flag_counter"],
        raw_review_count,
    )

    summary_record = {
        "appid": cohort_item["appid"],
        "game_name": metadata_data.get("name") or cohort_item["game_name"],
        "primary_bucket": cohort_item["primary_bucket"],
        "secondary_tags": list(cohort_item.get("secondary_tags") or []),
        "expected_failure_pattern": cohort_item.get("expected_failure_pattern"),
        "raw_review_count": raw_review_count,
        "included_review_count": summary_counts["included_review_count"],
        "included_ratio": ratio_fields["included_ratio"],
        "excluded_low_quality_count": summary_counts["excluded_low_quality_count"],
        "excluded_non_korean_count": summary_counts["excluded_non_korean_count"],
        "excluded_profanity_only_count": summary_counts["excluded_profanity_only_count"],
        "unclassified_included_count": summary_counts["unclassified_included_count"],
        "unclassified_included_ratio": ratio_fields["unclassified_included_ratio"],
        "canonical_theme_missing_count": summary_counts["canonical_theme_missing_count"],
        "canonical_theme_missing_ratio": ratio_fields["canonical_theme_missing_ratio"],
        "ambiguity_flagged_count": summary_counts["ambiguity_flagged_count"],
        "ambiguity_flagged_ratio": ratio_fields["ambiguity_flagged_ratio"],
        "fetched_pages": analysis_data.get("fetched_pages"),
        "fetched_review_count": analysis_data.get("fetched_review_count"),
        "fetch_timeout_seconds": analysis_data.get("fetch_timeout_seconds"),
        "fetch_filter": analysis_data.get("fetch_filter"),
        "all_mode_page_cap": analysis_data.get("all_mode_page_cap"),
        "all_mode_cap_reached": analysis_data.get("all_mode_cap_reached"),
        "review_pages": analysis_data.get("review_pages"),
        "genres": list(metadata_data.get("genres") or []),
        "price_model": metadata_data.get("price_model"),
        "release_stage": metadata_data.get("release_stage"),
        "top_categories": top_categories,
        "top_ambiguity_flags": top_ambiguity_flags,
        **sample_reviews,
        "notes": [],
    }
    summary_record["notes"] = build_notes(summary_record)
    return summary_record


def _top_records(
    summary_records: list[dict[str, Any]],
    field_name: str,
    *,
    min_threshold: float | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    filtered = summary_records
    if min_threshold is not None:
        filtered = [record for record in filtered if float(record.get(field_name) or 0.0) >= min_threshold]
    ordered = sorted(filtered, key=lambda record: float(record.get(field_name) or 0.0), reverse=True)
    return [
        {
            "appid": record["appid"],
            "game_name": record["game_name"],
            "value": record.get(field_name),
        }
        for record in ordered[:limit]
    ]


def build_bucket_summaries(summary_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate report summaries by primary bucket."""
    bucket_groups: dict[str, list[dict[str, Any]]] = {}
    for record in summary_records:
        bucket_groups.setdefault(record["primary_bucket"], []).append(record)

    bucket_summaries: list[dict[str, Any]] = []
    for bucket_name, records in sorted(bucket_groups.items()):
        game_count = len(records)
        bucket_summaries.append(
            {
                "primary_bucket": bucket_name,
                "game_count": game_count,
                "avg_unclassified_included_ratio": round(
                    sum(record["unclassified_included_ratio"] for record in records) / game_count,
                    4,
                ),
                "avg_canonical_theme_missing_ratio": round(
                    sum(record["canonical_theme_missing_ratio"] for record in records) / game_count,
                    4,
                ),
                "avg_ambiguity_flagged_ratio": round(
                    sum(record["ambiguity_flagged_ratio"] for record in records) / game_count,
                    4,
                ),
                "games": [
                    {
                        "appid": record["appid"],
                        "game_name": record["game_name"],
                    }
                    for record in records
                ],
            }
        )
    return bucket_summaries


def build_batch_report(
    cohort: list[dict[str, Any]],
    summary_records: list[dict[str, Any]],
    skipped_games: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the top-level batch report JSON structure."""
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "cohort_size": len(cohort),
        "processed_game_count": len(summary_records),
        "skipped_game_count": len(skipped_games),
        "summary_records": summary_records,
        "skipped_games": skipped_games,
        "outliers": {
            "high_unclassified": _top_records(
                summary_records,
                "unclassified_included_ratio",
                min_threshold=0.30,
            ),
            "high_theme_missing": _top_records(
                summary_records,
                "canonical_theme_missing_ratio",
                min_threshold=0.15,
            ),
            "high_ambiguity": _top_records(
                summary_records,
                "ambiguity_flagged_ratio",
                min_threshold=0.20,
            ),
            "cap_reached": [
                {
                    "appid": record["appid"],
                    "game_name": record["game_name"],
                }
                for record in summary_records
                if record.get("all_mode_cap_reached") is True
            ],
        },
        "bucket_summaries": build_bucket_summaries(summary_records),
    }


def write_json_report(batch_report: dict[str, Any], output_path: Path) -> None:
    """Write the JSON quality report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(batch_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_markdown_report(batch_report: dict[str, Any], output_path: Path) -> None:
    """Write a concise Markdown quality report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# 정규화 벤치마크 리포트",
        "",
        f"- 생성 시각: `{batch_report['generated_at']}`",
        f"- 코호트 크기: `{batch_report['cohort_size']}`",
        f"- 처리된 게임 수: `{batch_report['processed_game_count']}`",
        f"- 건너뛴 게임 수: `{batch_report['skipped_game_count']}`",
        "",
        "## 게임별 요약",
        "",
        "| appid | 게임명 | 대표 버킷 | raw | 포함 | 미분류 비율 | 테마 누락 비율 | ambiguity 비율 | notes |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for record in batch_report["summary_records"]:
        notes = "; ".join(record.get("notes") or []) or "-"
        lines.append(
            "| {appid} | {game_name} | {primary_bucket} | {raw_review_count} | "
            "{included_review_count} | {unclassified_included_ratio:.4f} | "
            "{canonical_theme_missing_ratio:.4f} | {ambiguity_flagged_ratio:.4f} | {notes} |".format(
                appid=record["appid"],
                game_name=record["game_name"],
                primary_bucket=record["primary_bucket"],
                raw_review_count=record["raw_review_count"],
                included_review_count=record["included_review_count"],
                unclassified_included_ratio=record["unclassified_included_ratio"],
                canonical_theme_missing_ratio=record["canonical_theme_missing_ratio"],
                ambiguity_flagged_ratio=record["ambiguity_flagged_ratio"],
                notes=notes,
            )
        )

    if batch_report["skipped_games"]:
        lines.extend(
            [
                "",
                "## 건너뛴 게임",
                "",
                "| appid | 게임명 | 누락 파일 |",
                "|---|---|---|",
            ]
        )
        for item in batch_report["skipped_games"]:
            lines.append(
                f"| {item['appid']} | {item['game_name']} | {', '.join(item['missing_files'])} |"
            )

    if batch_report["bucket_summaries"]:
        lines.extend(
            [
                "",
                "## 버킷별 실패 패턴 요약",
                "",
                "| 대표 버킷 | 게임 수 | 평균 미분류 비율 | 평균 테마 누락 비율 | 평균 ambiguity 비율 | 포함 게임 |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for bucket_summary in batch_report["bucket_summaries"]:
            game_names = ", ".join(game["game_name"] for game in bucket_summary["games"])
            lines.append(
                "| {primary_bucket} | {game_count} | {avg_unclassified_included_ratio:.4f} | "
                "{avg_canonical_theme_missing_ratio:.4f} | {avg_ambiguity_flagged_ratio:.4f} | {games} |".format(
                    primary_bucket=bucket_summary["primary_bucket"],
                    game_count=bucket_summary["game_count"],
                    avg_unclassified_included_ratio=bucket_summary["avg_unclassified_included_ratio"],
                    avg_canonical_theme_missing_ratio=bucket_summary["avg_canonical_theme_missing_ratio"],
                    avg_ambiguity_flagged_ratio=bucket_summary["avg_ambiguity_flagged_ratio"],
                    games=game_names,
                )
            )

    lines.extend(
        [
            "",
            "## 이상치 요약",
            "",
            f"- 높은 미분류 비율: `{len(batch_report['outliers']['high_unclassified'])}`건",
            f"- 높은 테마 누락 비율: `{len(batch_report['outliers']['high_theme_missing'])}`건",
            f"- 높은 ambiguity 비율: `{len(batch_report['outliers']['high_ambiguity'])}`건",
            f"- 부분 수집 게임: `{len(batch_report['outliers']['cap_reached'])}`건",
        ]
    )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a normalization benchmark JSON report.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DATA_DIR,
        help="Path to report data directory (default: backend/data/report).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to the output JSON report.",
    )
    parser.add_argument(
        "--appids",
        nargs="*",
        type=int,
        help="Optional explicit appids to restrict the cohort.",
    )
    parser.add_argument(
        "--cohort-file",
        type=Path,
        help="Optional JSON cohort file path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cohort = resolve_cohort(args.appids, args.cohort_file)

    summary_records: list[dict[str, Any]] = []
    skipped_games: list[dict[str, Any]] = []

    for cohort_item in cohort:
        game_inputs = load_game_inputs(args.base_dir, cohort_item["appid"])
        if game_inputs["missing_files"]:
            skipped_games.append(
                {
                    "appid": cohort_item["appid"],
                    "game_name": cohort_item["game_name"],
                    "missing_files": game_inputs["missing_files"],
                    "paths": game_inputs["paths"],
                }
            )
            continue

        summary_records.append(build_game_summary_record(cohort_item, game_inputs))

    batch_report = build_batch_report(cohort, summary_records, skipped_games)
    write_json_report(batch_report, args.output)
    write_markdown_report(batch_report, args.output.with_suffix(".md"))

    print(
        json.dumps(
            {
                "output_path": str(args.output),
                "markdown_output_path": str(args.output.with_suffix(".md")),
                "cohort_file": str(args.cohort_file) if args.cohort_file else None,
                "processed_game_count": len(summary_records),
                "skipped_game_count": len(skipped_games),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
