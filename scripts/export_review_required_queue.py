"""Export review-required repair actions into a human-readable Markdown queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data" / "report"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_review_required_markdown(payload: dict[str, Any]) -> str:
    rows = list(payload.get("rows", []) or [])
    review_count = sum(_review_action_count(row) for row in rows)
    hold_count = sum(len(list(row.get("holds", []) or [])) for row in rows)
    lines: list[str] = [
        "# Review Required Queue",
        "",
        f"- Source mode: `{payload.get('mode', 'unknown')}`",
        f"- Appids: `{', '.join(str(item) for item in list(payload.get('appids', []) or [])) or '-'}`",
        f"- Review-required actions: `{review_count}`",
        f"- Holds: `{hold_count}`",
        "",
        "> 이 문서는 자동 적용용이 아닙니다. `review_required`는 사람이 근거와 문맥을 확인한 뒤 수동 채택 여부를 판단해야 하는 후보입니다.",
        "",
    ]

    for row in rows:
        actions = _review_actions(row)
        holds = list(row.get("holds", []) or [])
        if not actions and not holds:
            continue
        lines.extend(_render_game_section(row, actions, holds))

    if len(lines) <= 9:
        lines.extend(["## Empty", "", "검토할 `review_required` 또는 hold 항목이 없습니다.", ""])

    return "\n".join(lines).rstrip() + "\n"


def _render_game_section(
    row: dict[str, Any],
    actions: list[dict[str, Any]],
    holds: list[dict[str, Any]],
) -> list[str]:
    game_name = str(row.get("game_name") or "Unknown Game")
    appid = row.get("appid", "-")
    lines = [
        f"## {game_name} ({appid})",
        "",
        f"- QA status: `{row.get('status', 'unknown')}`",
        f"- Semantic status: `{row.get('semantic_status', 'unknown')}`",
        f"- Failures: `{row.get('failure_count', 0)}` / critical `{row.get('critical_failure_count', 0)}`",
        f"- Report path: `{row.get('report_path', '-')}`",
        "",
    ]

    if actions:
        lines.extend(["### Review-Required Actions", ""])
        for index, action in enumerate(actions, start=1):
            lines.extend(_render_action(index, action))

    if holds:
        lines.extend(["### Holds", ""])
        for index, hold in enumerate(holds, start=1):
            lines.extend(_render_hold(index, hold))

    return lines


def _render_action(index: int, action: dict[str, Any]) -> list[str]:
    lines = [
        f"#### Action {index}: `{action.get('field', '-')}`",
        "",
        f"- Action: `{action.get('action', '-')}`",
        f"- Failure type: `{action.get('failure_type', '-')}`",
        f"- Claim id: `{action.get('claim_id', '-')}`",
        f"- Safety: `{action.get('safety_level', '-')}`",
        f"- Reason: {action.get('reason', '-')}",
        "",
        "**Current text**",
        "",
        _code_block(_format_value(action.get("current_text"))),
        "",
        "**Suggested replacement**",
        "",
        _code_block(_format_value(action.get("replacement_text"))),
        "",
    ]
    phrases = [str(item) for item in list(action.get("phrases_used", []) or []) if str(item).strip()]
    if phrases:
        lines.extend(["**Phrases used**", ""])
        lines.extend([f"- {phrase}" for phrase in phrases[:6]])
        lines.append("")
    lines.extend(
        [
            "**Decision checklist**",
            "",
            "- 실제 evidence claim과 suggested replacement가 같은 주제를 말하는가?",
            "- 기존 문장보다 구매 판단에 더 직접적으로 도움이 되는가?",
            "- 같은 claim을 같은 슬롯군에 반복 사용하지 않는가?",
            "- phrase가 리뷰 원문 잡음이 아니라 의미 있는 표현인가?",
            "",
            "**Operator decision**: `pending`",
            "",
        ]
    )
    return lines


def _render_hold(index: int, hold: dict[str, Any]) -> list[str]:
    return [
        f"#### Hold {index}: `{hold.get('field') or hold.get('claim_id') or '-'}`",
        "",
        f"- Hold type: `{hold.get('hold_type', '-')}`",
        f"- Failure type: `{hold.get('failure_type', '-')}`",
        f"- Claim id: `{hold.get('claim_id', '-')}`",
        f"- Reason: {hold.get('reason', '-')}",
        "",
        "**Blocked text**",
        "",
        _code_block(_format_value(hold.get("text"))),
        "",
    ]


def _review_actions(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action
        for action in list(row.get("actions", []) or [])
        if str(action.get("safety_level", "")).strip() == "review_required"
    ]


def _review_action_count(row: dict[str, Any]) -> int:
    return len(_review_actions(row))


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dict):
        title = str(value.get("title", "")).strip()
        summary = str(value.get("summary", "")).strip()
        if title or summary:
            return "\n".join(part for part in (f"제목: {title}" if title else "", f"설명: {summary}" if summary else "") if part)
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value) or "-"
    return str(value).strip() or "-"


def _code_block(value: str) -> str:
    safe_value = str(value or "-").replace("```", "'''")
    return f"```text\n{safe_value}\n```"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR / "reports" / "report_repair_plan.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "reports" / "report_review_required_queue.md",
    )
    args = parser.parse_args()

    payload = load_json(args.input)
    markdown = build_review_required_markdown(payload)
    write_text(args.output, markdown)
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
