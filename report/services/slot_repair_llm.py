"""LLM slot repairer for QA-failed report fields."""

from __future__ import annotations

import json
import os
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


SYSTEM_PROMPT = """
너는 게임 리뷰 리포트의 부분 보정 전용 편집자다.

목표:
- QA에서 실패한 슬롯 하나만 고친다.
- 제공된 evidence claim 밖의 새 사실을 만들지 않는다.
- 다른 게임 장르 문맥을 끌어오지 않는다.
- 고칠 수 없으면 drop을 선택한다.

규칙:
1) 현재 field 하나만 수정한다.
2) claim title/theme/why/snippets 범위 안에서만 다시 쓴다.
3) generic한 분석 문구를 쓰지 않는다.
4) good_for / not_good_for 는 짧은 플레이어 유형 명사구로 쓴다.
5) top_strengths / top_risks 는 title + summary 카드 형식으로 쓴다.
6) JSON만 반환한다.

출력 형식:
{
  "mode": "replace" | "drop",
  "field": "exact field name",
  "value": "string or object when mode=replace"
}
""".strip()


class OpenAISlotRepairer:
    """Repair one failed report slot at a time."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_SLOT_REPAIR_MODEL", "gpt-4.1-mini")
        self._client = (
            OpenAI(api_key=self.api_key)
            if OpenAI is not None and self.api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def repair_slot(
        self,
        *,
        report_payload: dict[str, Any],
        repair_action: dict[str, Any],
        claim: dict[str, Any] | None,
        timeout_seconds: int = 25,
        retry_limit: int = 1,
    ) -> dict[str, Any] | None:
        if self._client is None:
            return None

        field = str(repair_action.get("field", "") or "").strip()
        game = dict(report_payload.get("game", {}) or {})
        report_display = dict(report_payload.get("report_display", {}) or {})
        current_text = str(repair_action.get("current_text", "") or "").strip()
        if not current_text and field:
            current_text = _read_current_field(report_display, field)

        user_payload = {
            "game": {
                "name": str(game.get("name", "") or ""),
                "genres": list(game.get("genres", []) or []),
                "is_free": bool(game.get("is_free")),
            },
            "repair_action": {
                "action": str(repair_action.get("action", "") or ""),
                "failure_type": str(repair_action.get("failure_type", "") or ""),
                "field": field,
                "current_text": current_text,
                "suggested_replacement": repair_action.get("replacement_text"),
            },
            "grounding_claim": _compact_claim(claim),
            "rules": {
                "preserve_scope": True,
                "allow_drop": True,
                "avoid_genre_drift": True,
                "avoid_new_facts": True,
            },
        }

        prompt = (
            "아래 JSON을 바탕으로 QA 실패 슬롯 하나만 고치세요. "
            "evidence claim을 벗어나면 안 됩니다.\n\n"
            f"{json.dumps(user_payload, ensure_ascii=False)}"
        )

        for _ in range(retry_limit + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    continue
                payload = json.loads(content)
                validated = _validate_repair_payload(payload, field=field)
                if validated is not None:
                    return validated
            except Exception:
                continue
        return None


def _compact_claim(claim: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(claim, dict):
        return None
    return {
        "claim_id": claim.get("claim_id"),
        "section": claim.get("section"),
        "stance": claim.get("stance"),
        "title": claim.get("title"),
        "theme": claim.get("theme"),
        "why_it_matters": claim.get("why_it_matters"),
        "evidence_snippets": list(claim.get("evidence_snippets", []) or [])[:3],
        "candidate_snippets": list(claim.get("evidence_candidate_snippets", []) or [])[:4],
    }


def _read_current_field(report_display: dict[str, Any], field: str) -> str:
    if field in {"headline", "buy_timing_summary"}:
        return str(report_display.get(field, "") or "").strip()
    if field == "recent_state.summary":
        state = dict(report_display.get("recent_state", {}) or {})
        return str(state.get("summary", "") or "").strip()
    group, index = _parse_indexed_field(field)
    if group in {"good_for", "not_good_for"} and index is not None:
        items = list(report_display.get(group, []) or [])
        if 1 <= index <= len(items):
            return str(items[index - 1] or "").strip()
    if group in {"top_strengths", "top_risks"} and index is not None:
        items = list(report_display.get(group, []) or [])
        if 1 <= index <= len(items) and isinstance(items[index - 1], dict):
            item = items[index - 1]
            return f"{item.get('title', '')} {item.get('summary', '')}".strip()
    return ""


def _validate_repair_payload(payload: Any, *, field: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    mode = str(payload.get("mode", "") or "").strip().lower()
    result_field = str(payload.get("field", "") or field).strip()
    if result_field != field:
        return None
    if mode == "drop":
        return {"mode": "drop", "field": result_field}
    if mode != "replace":
        return None

    value = payload.get("value")
    group, _ = _parse_indexed_field(field)
    if field in {"headline", "buy_timing_summary", "recent_state.summary"} or group in {"good_for", "not_good_for"}:
        if not isinstance(value, str) or not value.strip():
            return None
        return {"mode": "replace", "field": result_field, "value": value.strip()}
    if group in {"top_strengths", "top_risks"}:
        if not isinstance(value, dict):
            return None
        title = str(value.get("title", "") or "").strip()
        summary = str(value.get("summary", "") or "").strip()
        if not title or not summary:
            return None
        return {
            "mode": "replace",
            "field": result_field,
            "value": {"title": title, "summary": summary},
        }
    if field.startswith("evidence_sections."):
        if not isinstance(value, dict):
            return None
        title = str(value.get("title", "") or "").strip()
        why = str(value.get("why_it_matters", "") or "").strip()
        explanation = str(value.get("explanation", "") or "").strip()
        if not title or not why or not explanation:
            return None
        return {
            "mode": "replace",
            "field": result_field,
            "value": {
                "title": title,
                "why_it_matters": why,
                "explanation": explanation,
            },
        }
    return None


def _parse_indexed_field(field: str) -> tuple[str, int | None]:
    if "[" not in field or not field.endswith("]"):
        return field, None
    group, _, tail = field.partition("[")
    try:
        index = int(tail[:-1])
    except ValueError:
        return group, None
    return group, index
