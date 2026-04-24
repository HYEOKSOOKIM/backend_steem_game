"""Multi-stage LLM writer for consumer-facing purchase decision reports."""

from __future__ import annotations

import json
import os
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

PLAN_SYSTEM_PROMPT = """
You generate a report plan from consensus review signals.

Rules:
- Consensus-first: high mention_count themes are primary.
- Grounding: use only provided JSON. No invented facts.
- Keep it concise and decision-oriented for buyers.
- If game_context.is_free is true, do not use buy_on_sale.
- JSON only.
""".strip()

CORE_SYSTEM_PROMPT = """
Write the core buyer-facing decision section.

Rules:
- Use only provided plan and consensus data.
- Avoid analytics jargon.
- Do not mention counts, ratios, or signal terminology.
- Make it readable in a few seconds.
- If game_context.is_free is true, prefer free_play_recommended/play_now/try_lightly.
- Write like polished in-product UX copy for a game report, not like an analyst report.
- Keep each field short and natural in Korean UI.
- The headline is the main takeaway. The buy_timing_summary should complement it, not repeat it.
- Focus on player experience and purchase context.
- Avoid abstract analysis wording and internal framing.
- Prefer short, direct, buyer-facing sentences.
- One key idea per sentence.
- Keep genre context aligned with the game. Do not introduce genre-specific metaphors that the game does not support.
- If the game is a shooter, battle royale, sports, simulation, or management title, avoid boss-fight / pattern-learning phrasing unless the provided evidence clearly supports it.
- Keep good_for and not_good_for close to the provided seed persona items and player_fit_signals.
- Each good_for / not_good_for item must be a short noun phrase for a player type, not a sentence.
- End each persona item as a compact phrase such as "...플레이어", "...유저", or "...분".
- Do not end persona items with sentence endings such as "이다", "입니다", "좋아요", or "필요합니다".
- Do not invent a new player persona if the provided seed already gives a genre-safe one.
- Avoid expressions like:
  "지적이 있습니다", "불만이 많습니다", "가능성이 큽니다", "체감", "포인트", "리스크", "반복되면", "지원합니다", "이어집니다"
- JSON only.
""".strip()

STRENGTHS_SYSTEM_PROMPT = """
Write top_strengths section only.

Rules:
- Use high-consensus positive signals first.
- Describe player experience, not categories or metrics.
- Return 2~3 concise items.
- Write like polished in-product UX copy for a game report.
- Each title should feel like a short, scan-friendly card heading.
- Each summary should be 1~2 short sentences max.
- Explain why this feels good to play in plain language.
- Do not restate the title in the summary.
- Do not describe analysis logic, metrics, consensus, or category labels.
- Keep genre context aligned with the game. Avoid importing boss-fight, raid, farming, or management language unless the provided evidence supports it.
- Avoid analyst/report phrasing such as:
  "지적이 있습니다", "불만이 많습니다", "가능성이 큽니다", "체감", "포인트", "리스크", "이어집니다"
- JSON only.
""".strip()

RISKS_SYSTEM_PROMPT = """
Write top_risks section only.

Rules:
- Use high-consensus negative signals first.
- Describe buyer-facing pain points, not category labels.
- Return 2~3 concise items.
- Write like polished in-product UX copy for a game report.
- Each title should feel like a short, scan-friendly card heading.
- Each summary should be 1~2 short sentences max.
- State what may feel disappointing, tiring, or frustrating in real play.
- Keep the tone calm and practical, not alarmist or academic.
- Do not restate the title in the summary.
- Keep genre context aligned with the game. Avoid dragging in genre-specific pain points that do not match the provided evidence.
- Avoid analyst/report phrasing such as:
  "지적이 있습니다", "불만이 많습니다", "가능성이 큽니다", "체감", "포인트", "리스크", "이어집니다"
- JSON only.
""".strip()

RECENT_STATE_SYSTEM_PROMPT = """
Write recent_state section only.

Rules:
- Reflect recent trend from provided signals only.
- Keep one concise buyer-facing summary without metric wording.
- Return one clear status + one short summary.
- Write like polished in-product UX copy for a game report.
- The summary should describe the recent mood of reviews in plain Korean.
- Keep it to one short, natural sentence.
- Do not explain the analysis or mention counts/ratios.
- Keep the wording aligned with the game's genre and actual play context.
- Avoid analyst/report phrasing such as:
  "지적이 있습니다", "불만이 많습니다", "가능성이 큽니다", "체감", "포인트", "리스크", "이어집니다"
- JSON only.
""".strip()

ALLOWED_RECOMMENDATIONS = {
    "buy_now",
    "buy_on_sale",
    "wait",
    "not_recommended",
    "free_play_recommended",
    "play_now",
    "try_lightly",
}
RECOMMENDATION_ENUM_TEXT = (
    "buy_now|buy_on_sale|wait|not_recommended|free_play_recommended|play_now|try_lightly"
)


class OpenAIReportWriter:
    """Generate report plan and display sections using section-specific prompts."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        plan_model: str | None = None,
        display_model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        fallback_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.plan_model = plan_model or os.getenv("OPENAI_REPORT_PLAN_MODEL", fallback_model)
        self.display_model = display_model or os.getenv("OPENAI_REPORT_DISPLAY_MODEL", "gpt-4.1-mini")
        self._client = (
            OpenAI(api_key=self.api_key)
            if OpenAI is not None and self.api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def generate_report_plan(
        self,
        *,
        consensus_payload: dict[str, Any],
        seed_plan: dict[str, Any],
        timeout_seconds: int = 25,
        retry_limit: int = 1,
    ) -> dict[str, Any] | None:
        """Stage 1: generate report_plan."""
        if self._client is None:
            return None

        user_payload = {
            "task": "report_plan",
            "seed_plan": seed_plan,
            "consensus_payload": consensus_payload,
            "output_contract": {
                "decision_anchor": {
                    "buy_recommendation": RECOMMENDATION_ENUM_TEXT,
                    "primary_reason_ids": ["string", "string"],
                    "rationale_short": "string",
                },
                "section_blueprint": {
                    "strength_block_count": "int(2~3)",
                    "risk_block_count": "int(2~3)",
                    "evidence_per_block": "int(2~3)",
                },
                "theme_priorities": {
                    "strengths": [{"reason_id": "string", "aspect": "string", "theme": "string"}],
                    "risks": [{"reason_id": "string", "aspect": "string", "theme": "string"}],
                },
            },
        }
        candidate = self._chat_json(
            model=self.plan_model,
            system_prompt=PLAN_SYSTEM_PROMPT,
            user_payload=user_payload,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        if _validate_report_plan(candidate):
            return candidate
        return None

    def generate_report_display(
        self,
        *,
        consensus_payload: dict[str, Any],
        report_plan: dict[str, Any],
        seed_display: dict[str, Any],
        timeout_seconds: int = 25,
        retry_limit: int = 1,
    ) -> dict[str, Any] | None:
        """Stage 2: generate display sections with section-specific prompts."""
        if self._client is None:
            return None

        core = self._generate_core_section(
            consensus_payload=consensus_payload,
            report_plan=report_plan,
            seed_display=seed_display,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        strengths = self._generate_strengths_section(
            consensus_payload=consensus_payload,
            report_plan=report_plan,
            seed_display=seed_display,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        risks = self._generate_risks_section(
            consensus_payload=consensus_payload,
            report_plan=report_plan,
            seed_display=seed_display,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        recent_state = self._generate_recent_state_section(
            consensus_payload=consensus_payload,
            report_plan=report_plan,
            seed_display=seed_display,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )

        if not core or not strengths or not risks or not recent_state:
            return None

        payload = {
            **core,
            "top_strengths": strengths.get("top_strengths", []),
            "top_risks": risks.get("top_risks", []),
            "recent_state": recent_state.get("recent_state"),
        }
        if _validate_report_display(payload):
            return payload
        return None

    def _generate_core_section(
        self,
        *,
        consensus_payload: dict[str, Any],
        report_plan: dict[str, Any],
        seed_display: dict[str, Any],
        timeout_seconds: int,
        retry_limit: int,
    ) -> dict[str, Any] | None:
        user_payload = {
            "task": "display_core",
            "report_plan": report_plan,
            "seed_display": {
                "headline": seed_display.get("headline"),
                "buy_recommendation": seed_display.get("buy_recommendation"),
                "buy_timing_summary": seed_display.get("buy_timing_summary"),
                "good_for": seed_display.get("good_for", []),
                "not_good_for": seed_display.get("not_good_for", []),
                "player_fit_signals": seed_display.get("player_fit_signals", {}),
            },
            "consensus_payload": consensus_payload,
            "output_contract": {
                "headline": "string",
                "buy_recommendation": RECOMMENDATION_ENUM_TEXT,
                "buy_timing_summary": "string",
                "good_for": ["string"],
                "not_good_for": ["string"],
            },
        }
        candidate = self._chat_json(
            model=self.display_model,
            system_prompt=CORE_SYSTEM_PROMPT,
            user_payload=user_payload,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        if _validate_core_section(candidate):
            return candidate
        return None

    def _generate_strengths_section(
        self,
        *,
        consensus_payload: dict[str, Any],
        report_plan: dict[str, Any],
        seed_display: dict[str, Any],
        timeout_seconds: int,
        retry_limit: int,
    ) -> dict[str, Any] | None:
        user_payload = {
            "task": "top_strengths",
            "report_plan": report_plan,
            "seed_top_strengths": seed_display.get("top_strengths", []),
            "consensus_payload": consensus_payload,
            "output_contract": {
                "top_strengths": [{"title": "string", "summary": "string"}],
            },
        }
        candidate = self._chat_json(
            model=self.display_model,
            system_prompt=STRENGTHS_SYSTEM_PROMPT,
            user_payload=user_payload,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        if _validate_strengths_section(candidate):
            return candidate
        return None

    def _generate_risks_section(
        self,
        *,
        consensus_payload: dict[str, Any],
        report_plan: dict[str, Any],
        seed_display: dict[str, Any],
        timeout_seconds: int,
        retry_limit: int,
    ) -> dict[str, Any] | None:
        user_payload = {
            "task": "top_risks",
            "report_plan": report_plan,
            "seed_top_risks": seed_display.get("top_risks", []),
            "consensus_payload": consensus_payload,
            "output_contract": {
                "top_risks": [{"title": "string", "summary": "string"}],
            },
        }
        candidate = self._chat_json(
            model=self.display_model,
            system_prompt=RISKS_SYSTEM_PROMPT,
            user_payload=user_payload,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        if _validate_risks_section(candidate):
            return candidate
        return None

    def _generate_recent_state_section(
        self,
        *,
        consensus_payload: dict[str, Any],
        report_plan: dict[str, Any],
        seed_display: dict[str, Any],
        timeout_seconds: int,
        retry_limit: int,
    ) -> dict[str, Any] | None:
        user_payload = {
            "task": "recent_state",
            "report_plan": report_plan,
            "seed_recent_state": seed_display.get("recent_state", {}),
            "consensus_payload": consensus_payload,
            "output_contract": {
                "recent_state": {
                    "status": "improving|stable|declining|mixed|insufficient_data",
                    "summary": "string",
                },
            },
        }
        candidate = self._chat_json(
            model=self.display_model,
            system_prompt=RECENT_STATE_SYSTEM_PROMPT,
            user_payload=user_payload,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
        )
        if _validate_recent_state_section(candidate):
            return candidate
        return None

    def _chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        timeout_seconds: int,
        retry_limit: int,
    ) -> dict[str, Any] | None:
        if self._client is None:
            return None
        prompt = (
            "다음 입력을 기반으로 JSON만 반환하세요. "
            "입력 데이터 밖의 사실을 만들지 마세요.\n\n"
            f"{json.dumps(user_payload, ensure_ascii=False)}"
        )
        for _ in range(retry_limit + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    continue
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return None


def validate_structured_report_payload(payload: Any) -> bool:
    """Validate final multi-stage contract."""
    if not isinstance(payload, dict):
        return False
    if not _validate_report_plan(payload.get("report_plan")):
        return False
    if not _validate_report_display(payload.get("report_display")):
        return False
    if not _validate_evidence_sections(payload.get("evidence_sections")):
        return False
    return True


def _validate_report_plan(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    decision = value.get("decision_anchor")
    if not isinstance(decision, dict):
        return False
    if decision.get("buy_recommendation") not in ALLOWED_RECOMMENDATIONS:
        return False
    if not isinstance(decision.get("primary_reason_ids"), list):
        return False
    if not isinstance(decision.get("rationale_short"), str):
        return False
    blueprint = value.get("section_blueprint")
    if not isinstance(blueprint, dict):
        return False
    if not isinstance(blueprint.get("strength_block_count"), int):
        return False
    if not isinstance(blueprint.get("risk_block_count"), int):
        return False
    evidence_per_block = int(blueprint.get("evidence_per_block", 0))
    if evidence_per_block < 2 or evidence_per_block > 3:
        return False
    priorities = value.get("theme_priorities")
    if not isinstance(priorities, dict):
        return False
    if not isinstance(priorities.get("strengths"), list):
        return False
    if not isinstance(priorities.get("risks"), list):
        return False
    return True


def _validate_core_section(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("headline"), str):
        return False
    if value.get("buy_recommendation") not in ALLOWED_RECOMMENDATIONS:
        return False
    if not isinstance(value.get("buy_timing_summary"), str):
        return False
    if not isinstance(value.get("good_for"), list):
        return False
    if not isinstance(value.get("not_good_for"), list):
        return False
    return True


def _validate_strengths_section(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    items = value.get("top_strengths")
    if not isinstance(items, list):
        return False
    if len(items) < 2 or len(items) > 3:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("title"), str):
            return False
        if not isinstance(item.get("summary"), str):
            return False
    return True


def _validate_risks_section(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    items = value.get("top_risks")
    if not isinstance(items, list):
        return False
    if len(items) < 2 or len(items) > 3:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("title"), str):
            return False
        if not isinstance(item.get("summary"), str):
            return False
    return True


def _validate_recent_state_section(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    state = value.get("recent_state")
    if not isinstance(state, dict):
        return False
    if state.get("status") not in {
        "improving",
        "stable",
        "declining",
        "mixed",
        "insufficient_data",
    }:
        return False
    if not isinstance(state.get("summary"), str):
        return False
    return True


def _validate_report_display(value: Any) -> bool:
    if not _validate_core_section(value):
        return False
    if not isinstance(value.get("top_strengths"), list):
        return False
    if not isinstance(value.get("top_risks"), list):
        return False
    if not _validate_recent_state_section({"recent_state": value.get("recent_state")}):
        return False
    return True


def _validate_evidence_sections(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    strengths = value.get("strengths")
    risks = value.get("risks")
    if not isinstance(strengths, list) or not isinstance(risks, list):
        return False
    for block in strengths:
        if not _validate_evidence_block(block, expected_stance="positive"):
            return False
    for block in risks:
        if not _validate_evidence_block(block, expected_stance="negative"):
            return False
    return True


def _validate_evidence_block(block: Any, *, expected_stance: str) -> bool:
    if not isinstance(block, dict):
        return False
    if not isinstance(block.get("block_id"), str):
        return False
    if not isinstance(block.get("title"), str):
        return False
    if not isinstance(block.get("why_it_matters"), str):
        return False
    if not isinstance(block.get("explanation"), str):
        return False
    if block.get("stance") != expected_stance:
        return False
    if block.get("consensus_level") not in {"high", "medium"}:
        return False
    if not isinstance(block.get("mention_count"), int):
        return False
    snippets = block.get("evidence_snippets")
    if not isinstance(snippets, list):
        return False
    if len(snippets) < 2 or len(snippets) > 3:
        return False
    if any(not isinstance(snippet, str) for snippet in snippets):
        return False
    return True
