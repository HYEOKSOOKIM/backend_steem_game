"""Final Korean language proofreader for buyer-facing report text."""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


SYSTEM_PROMPT = """
너는 한국어 교정 편집기다.

목표:
- 의미를 바꾸지 않고 문법/조사/띄어쓰기만 자연스럽게 교정한다.

규칙:
1) 입력 문장의 사실/의도/톤을 바꾸지 말 것
2) 조사 오류(이/가, 을/를, 은/는 등) 교정
3) 띄어쓰기 교정
4) 문장을 과도하게 줄이거나 늘리지 말 것
5) 출력은 JSON only: {"text": "..."}
""".strip()


RULE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("버그이 ", "버그가 "),
    ("문제이 ", "문제가 "),
    ("이슈이 ", "이슈가 "),
    ("리스크이 ", "리스크가 "),
    ("불만이 거슬", "불만이 거슬"),
    ("가볍게  시작", "가볍게 시작"),
)


def rule_proofread_text(text: str) -> str:
    """Deterministic correction for common particle/spacing issues."""
    value = " ".join((text or "").split()).strip()
    if not value:
        return ""

    for before, after in RULE_REPLACEMENTS:
        value = value.replace(before, after)

    # Common grammar shape: "<noun>이 거슬리" -> "<noun>가 거슬리"
    value = re.sub(r"([0-9A-Za-z가-힣/]+)이 거슬", r"\1가 거슬", value)
    value = re.sub(r"([0-9A-Za-z가-힣/]+)이 필요", r"\1가 필요", value)
    value = re.sub(r"([0-9A-Za-z가-힣/]+)이 반복", r"\1가 반복", value)

    # Normalize punctuation spacing.
    value = re.sub(r"\s+([,.!?])", r"\1", value)
    value = re.sub(r"([,.!?])([가-힣A-Za-z0-9])", r"\1 \2", value)
    value = " ".join(value.split()).strip()
    return value


class KoreanReportProofreader:
    """Hybrid proofreader: deterministic rules + optional LLM correction."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_llm_texts: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_REPORT_PROOFREADER_MODEL", "gpt-4o-mini")
        self.max_llm_texts = max_llm_texts or int(os.getenv("REPORT_PROOFREAD_MAX_LLM_TEXTS", "24"))
        self._client = (
            OpenAI(api_key=self.api_key)
            if OpenAI is not None and self.api_key
            else None
        )
        self._cache: dict[str, str | None] = {}
        self._llm_calls = 0

    @property
    def available(self) -> bool:
        return self._client is not None

    def proofread_text(self, text: str, *, allow_llm: bool) -> str:
        """Run final correction while preserving original meaning."""
        base = rule_proofread_text(text)
        if not base:
            return base
        if not allow_llm:
            return base
        if self._client is None:
            return base
        if self._llm_calls >= self.max_llm_texts:
            return base

        cached = self._cache.get(base)
        if cached is not None:
            return cached

        candidate = self._proofread_with_llm(base)
        if candidate is None:
            self._cache[base] = base
            return base

        self._cache[base] = candidate
        return candidate

    def _proofread_with_llm(self, text: str) -> str | None:
        if self._client is None:
            return None
        self._llm_calls += 1
        prompt = (
            "다음 문장을 의미 변경 없이 교정하세요.\n"
            "- 조사/문법/띄어쓰기만 수정\n"
            "- JSON만 반환\n\n"
            f"입력:\n{text}"
        )
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=10,
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                return None
            payload = json.loads(content)
            return _validate_llm_text(payload, source=text)
        except Exception:
            return None


def _validate_llm_text(payload: Any, *, source: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if not isinstance(text, str):
        return None
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    # Guard against meaning drift via extreme length change.
    src_len = max(len(source.strip()), 1)
    ratio = len(normalized) / src_len
    if ratio < 0.55 or ratio > 1.8:
        return None
    return normalized

