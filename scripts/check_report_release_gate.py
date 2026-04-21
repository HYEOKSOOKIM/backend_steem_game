"""Release gate checker for buyer-facing report quality."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"
LEGACY_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_COHORT_FILE = DATA_DIR / "catalog" / "cohort_v2_32.json"
DEFAULT_OUTPUT = DATA_DIR / "reports" / "report_release_gate.json"

FORBIDDEN_LABELS = (
    "조작 / 규칙 학습 난이도",
    "전투 손맛 / 액션 호평",
    "스토리 / 서사 몰입",
    "스토리/서사 몰입",
    "최적화 문제",
    "일반 버그",
    "가격 / 과금 불만",
    "가격/ 과금 불만",
    "DLC / 확장팩 언급",
    "반복 / 목적성 부족",
    "매칭 / 서버 문제",
    "밸런스 불만",
    "번역/현지화 품질",
    "건축 조작 불편",
    "콘텐츠 부족",
    "세이브 / 진행 유실",
)

EVIDENCE_POSITIVE_HINTS = {
    "재밌",
    "재미",
    "꿀잼",
    "갓겜",
    "할만",
    "good",
    "best",
    "재밌",
    "재미",
    "좋",
    "만족",
    "몰입",
    "훌륭",
    "손맛",
    "추천",
}

EVIDENCE_NEGATIVE_HINTS = {
    "핵",
    "해킹",
    "정지",
    "밴",
    "팅김",
    "팅기",
    "강퇴",
    "안티치트",
    "팀킬",
    "최적화",
    "불안정",
    "말썽",
    "어뷰징",
    "hack",
    "cheat",
    "ban",
    "kick",
    "disconnect",
    "stutter",
    "lag",
    "crash",
    "불편",
    "문제",
    "버그",
    "오류",
    "렉",
    "프레임",
    "끊김",
    "튕김",
    "지루",
    "답답",
    "하락",
    "스트레스",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def resolve_report_path(appid: int) -> Path | None:
    for report_dir in (DATA_DIR / "report", LEGACY_DATA_DIR / "report"):
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


def collect_text_targets(report_payload: dict[str, Any]) -> list[str]:
    report_display = dict(report_payload.get("report_display", {}) or {})
    evidence_sections = dict(report_payload.get("evidence_sections", {}) or {})

    targets: list[str] = []
    if isinstance(report_display.get("headline"), str):
        targets.append(str(report_display.get("headline", "")))

    for item in list(report_display.get("top_strengths", []) or []):
        if isinstance(item, dict) and isinstance(item.get("title"), str):
            targets.append(str(item.get("title", "")))
    for item in list(report_display.get("top_risks", []) or []):
        if isinstance(item, dict) and isinstance(item.get("title"), str):
            targets.append(str(item.get("title", "")))

    for stance_key in ("strengths", "risks"):
        for block in list(evidence_sections.get(stance_key, []) or []):
            if isinstance(block, dict) and isinstance(block.get("title"), str):
                targets.append(str(block.get("title", "")))

    return targets


def count_forbidden_label_exposure(texts: list[str]) -> tuple[int, list[dict[str, str]]]:
    exposure_count = 0
    hits: list[dict[str, str]] = []
    for text in texts:
        normalized = " ".join(str(text).split()).strip()
        if not normalized:
            continue
        for label in FORBIDDEN_LABELS:
            if label in normalized:
                exposure_count += 1
                hits.append({"text": normalized, "label": label})
                break
    return exposure_count, hits


def _classify_snippet_stance(text: str) -> str | None:
    normalized = str(text or "").lower()
    if not normalized:
        return None
    pos_hits = sum(1 for token in EVIDENCE_POSITIVE_HINTS if token in normalized)
    neg_hits = sum(1 for token in EVIDENCE_NEGATIVE_HINTS if token in normalized)
    if pos_hits >= neg_hits + 1:
        return "positive"
    if neg_hits >= pos_hits + 1:
        return "negative"
    return None


def _collect_evidence_alignment_metrics(report_payload: dict[str, Any]) -> dict[str, Any]:
    evidence_sections = dict(report_payload.get("evidence_sections", {}) or {})
    mismatch_count = 0
    checked_count = 0
    unknown_count = 0
    quality_level_counts = {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0}
    quality_level_counts_by_section = {
        "strengths": {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0},
        "risks": {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0},
    }
    mismatch_samples: list[dict[str, str]] = []

    for expected_stance, section_key in (("positive", "strengths"), ("negative", "risks")):
        for block in list(evidence_sections.get(section_key, []) or []):
            title = str(block.get("title", "")).strip()
            quality_level = str(block.get("evidence_quality_level", "")).strip().lower()
            if quality_level not in {"strict", "relaxed", "guaranteed_fill"}:
                quality_level = "unknown"
            quality_level_counts[quality_level] += 1
            quality_level_counts_by_section[section_key][quality_level] += 1
            for snippet in list(block.get("evidence_snippets", []) or []):
                stance = _classify_snippet_stance(str(snippet))
                if stance is None:
                    unknown_count += 1
                    continue
                checked_count += 1
                if stance != expected_stance:
                    mismatch_count += 1
                    if len(mismatch_samples) < 5:
                        mismatch_samples.append(
                            {
                                "expected_stance": expected_stance,
                                "detected_stance": stance,
                                "block_title": title,
                                "snippet": str(snippet)[:240],
                            }
                        )

    mismatch_rate = (mismatch_count / checked_count) if checked_count > 0 else 0.0
    evaluated_total = checked_count + unknown_count
    unknown_rate = (unknown_count / evaluated_total) if evaluated_total > 0 else 0.0
    return {
        "evidence_checked_snippet_count": checked_count,
        "evidence_unknown_snippet_count": unknown_count,
        "evidence_unknown_snippet_rate": round(unknown_rate, 4),
        "evidence_mismatch_count": mismatch_count,
        "evidence_mismatch_rate": round(mismatch_rate, 4),
        "evidence_mismatch_samples": mismatch_samples,
        "evidence_quality_level_counts": quality_level_counts,
        "evidence_quality_level_counts_by_section": quality_level_counts_by_section,
    }


def evaluate_report(appid: int, game_name: str, report_payload: dict[str, Any]) -> dict[str, Any]:
    report_display = dict(report_payload.get("report_display", {}) or {})
    evidence_sections = dict(report_payload.get("evidence_sections", {}) or {})

    buy_recommendation = str(report_display.get("buy_recommendation", "")).strip()
    headline = str(report_display.get("headline", "")).strip()
    timing = str(report_display.get("buy_timing_summary", "")).strip()
    good_for = list(report_display.get("good_for", []) or [])
    not_good_for = list(report_display.get("not_good_for", []) or [])

    strengths = list(evidence_sections.get("strengths", []) or [])
    risks = list(evidence_sections.get("risks", []) or [])

    decision_core_ready = bool(buy_recommendation and headline and timing)
    fit_ready = bool(good_for and not_good_for)
    evidence_ready = bool(strengths and risks)

    text_targets = collect_text_targets(report_payload)
    forbidden_count, forbidden_hits = count_forbidden_label_exposure(text_targets)

    quick_score = 0
    quick_score += 1 if decision_core_ready else 0
    quick_score += 1 if fit_ready else 0
    quick_score += 1 if evidence_ready else 0
    quick_score += 1 if forbidden_count == 0 else 0

    row = {
        "appid": appid,
        "game_name": game_name,
        "decision_core_ready": decision_core_ready,
        "fit_ready": fit_ready,
        "evidence_ready": evidence_ready,
        "forbidden_label_exposure_count": forbidden_count,
        "forbidden_label_hits_sample": forbidden_hits[:5],
        "quick_decision_score_4": quick_score,
    }
    row.update(_collect_evidence_alignment_metrics(report_payload))
    return row


def _calculate_quality_level_distribution(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0}
    strengths = {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0}
    risks = {"strict": 0, "relaxed": 0, "guaranteed_fill": 0, "unknown": 0}

    for row in results:
        counts = dict(row.get("evidence_quality_level_counts", {}) or {})
        section_counts = dict(row.get("evidence_quality_level_counts_by_section", {}) or {})
        for key in total:
            total[key] += int(counts.get(key, 0) or 0)
            strengths[key] += int((section_counts.get("strengths", {}) or {}).get(key, 0) or 0)
            risks[key] += int((section_counts.get("risks", {}) or {}).get(key, 0) or 0)

    total_blocks = sum(total.values())
    strength_blocks = sum(strengths.values())
    risk_blocks = sum(risks.values())

    def _with_ratio(counts: dict[str, int], base: int) -> dict[str, dict[str, float | int]]:
        payload: dict[str, dict[str, float | int]] = {}
        for key, value in counts.items():
            payload[key] = {
                "count": int(value),
                "ratio": round((value / base), 4) if base > 0 else 0.0,
            }
        return payload

    return {
        "total_blocks": total_blocks,
        "strength_blocks": strength_blocks,
        "risk_blocks": risk_blocks,
        "all": _with_ratio(total, total_blocks),
        "strengths": _with_ratio(strengths, strength_blocks),
        "risks": _with_ratio(risks, risk_blocks),
    }


def load_cohort(cohort_file: Path) -> list[dict[str, Any]]:
    payload = load_json(cohort_file)
    if isinstance(payload, dict) and isinstance(payload.get("cohort"), list):
        return list(payload.get("cohort", []))
    if isinstance(payload, list):
        return list(payload)
    raise ValueError("cohort file must be a list or object with 'cohort' field")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 리포트 릴리즈 게이트 결과",
        "",
        f"- 생성 시각: `{payload['generated_at']}`",
        f"- 코호트 파일: `{payload['cohort_file']}`",
        f"- 평가 대상: `{payload['evaluated_game_count']}`",
        f"- 누락 리포트: `{payload['missing_report_count']}`",
        f"- 최소 통과 점수: `{payload['min_score']}`",
        f"- unknown_snippet_rate 상한: `{payload['max_unknown_snippet_rate']}`",
        f"- 전체 통과: `{payload['gate_passed']}`",
        "",
        "| appid | 게임 | 점수(4) | 핵심결론 | 적합성 | 근거 | 금지라벨 | 불일치율 | unknown 비율 | 품질단계(s/r/g/u) | 통과 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]

    for row in payload.get("results", []):
        q_counts = dict(row.get("evidence_quality_level_counts", {}) or {})
        q_compact = "{s}/{r}/{g}/{u}".format(
            s=int(q_counts.get("strict", 0) or 0),
            r=int(q_counts.get("relaxed", 0) or 0),
            g=int(q_counts.get("guaranteed_fill", 0) or 0),
            u=int(q_counts.get("unknown", 0) or 0),
        )
        lines.append(
            "| {appid} | {game_name} | {score} | {core} | {fit} | {ev} | {forbidden} | {mismatch_rate} | {unknown_rate} | {q} | {passed} |".format(
                appid=row.get("appid"),
                game_name=row.get("game_name"),
                score=row.get("quick_decision_score_4"),
                core="Y" if row.get("decision_core_ready") else "N",
                fit="Y" if row.get("fit_ready") else "N",
                ev="Y" if row.get("evidence_ready") else "N",
                forbidden=row.get("forbidden_label_exposure_count"),
                mismatch_rate=row.get("evidence_mismatch_rate"),
                unknown_rate=row.get("evidence_unknown_snippet_rate"),
                q=q_compact,
                passed="Y" if row.get("passed") else "N",
            )
        )

    quality_dist = dict(payload.get("evidence_quality_level_distribution", {}) or {})
    if quality_dist:
        lines.extend(["", "## Evidence Quality Level 분포", ""])
        lines.append(
            "| scope | strict | relaxed | guaranteed_fill | unknown |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for scope_key in ("all", "strengths", "risks"):
            dist = dict(quality_dist.get(scope_key, {}) or {})
            lines.append(
                "| {scope} | {s} | {r} | {g} | {u} |".format(
                    scope=scope_key,
                    s=f"{dist.get('strict', {}).get('count', 0)} ({dist.get('strict', {}).get('ratio', 0.0)})",
                    r=f"{dist.get('relaxed', {}).get('count', 0)} ({dist.get('relaxed', {}).get('ratio', 0.0)})",
                    g=f"{dist.get('guaranteed_fill', {}).get('count', 0)} ({dist.get('guaranteed_fill', {}).get('ratio', 0.0)})",
                    u=f"{dist.get('unknown', {}).get('count', 0)} ({dist.get('unknown', {}).get('ratio', 0.0)})",
                )
            )

    if payload.get("missing_reports"):
        lines.extend(["", "## 누락 리포트", ""])
        for item in payload["missing_reports"]:
            lines.append(f"- `{item['appid']}` {item['game_name']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release gate checks for report outputs.")
    parser.add_argument(
        "--cohort-file",
        type=Path,
        default=DEFAULT_COHORT_FILE,
        help="Path to cohort json file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to output JSON",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=4,
        help="Minimum quick_decision_score_4 required to pass",
    )
    parser.add_argument(
        "--max-unknown-snippet-rate",
        type=float,
        default=0.40,
        help="Auxiliary gate upper bound for evidence_unknown_snippet_rate",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cohort = load_cohort(args.cohort_file)

    results: list[dict[str, Any]] = []
    missing_reports: list[dict[str, Any]] = []

    for item in cohort:
        appid = int(item["appid"])
        game_name = str(item.get("game_name") or appid)
        report_path = resolve_report_path(appid)
        if report_path is None:
            missing_reports.append({"appid": appid, "game_name": game_name})
            continue
        report_payload = load_json(report_path)
        row = evaluate_report(appid, game_name, report_payload)
        row["report_path"] = str(report_path)
        row["unknown_snippet_rate_exceeded"] = (
            float(row.get("evidence_unknown_snippet_rate", 0.0)) > float(args.max_unknown_snippet_rate)
        )
        row["passed"] = (
            int(row["quick_decision_score_4"]) >= int(args.min_score)
            and not bool(row["unknown_snippet_rate_exceeded"])
        )
        results.append(row)

    gate_passed = (
        bool(results)
        and not missing_reports
        and all(bool(row.get("passed")) for row in results)
    )

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "cohort_file": str(args.cohort_file),
        "min_score": int(args.min_score),
        "max_unknown_snippet_rate": float(args.max_unknown_snippet_rate),
        "evaluated_game_count": len(results),
        "missing_report_count": len(missing_reports),
        "missing_reports": missing_reports,
        "gate_passed": gate_passed,
        "evidence_quality_level_distribution": _calculate_quality_level_distribution(results),
        "results": results,
    }

    write_json(args.output, payload)
    write_markdown(args.output.with_suffix(".md"), payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "markdown_output": str(args.output.with_suffix(".md")),
                "evaluated_game_count": len(results),
                "missing_report_count": len(missing_reports),
                "gate_passed": gate_passed,
            },
            ensure_ascii=False,
        )
    )
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
