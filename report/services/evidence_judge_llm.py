"""LLM judge for evidence snippet relevance (stance/theme consistency)."""

from __future__ import annotations

import json
import os
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


SYSTEM_PROMPT = """
너는 구매 리포트의 근거 스니펫 품질 심사관이다.

목표:
- 후보 스니펫 중에서 블록 주제(theme)와 입장(stance)에 가장 잘 맞는 스니펫만 고른다.
- 과장되거나 주제와 무관한 스니펫을 제외한다.

규칙:
1) stance 일치가 최우선이다. (positive/negative)
2) theme 및 why_it_matters와 의미적으로 가까운 스니펫을 우선한다.
3) 너무 일반적이거나 맥락이 약한 문장은 후순위로 둔다.
4) JSON만 반환한다.

출력 스키마:
{"selected_indices":[1,2,4]}
- selected_indices는 1-based 인덱스
- 최소 2개, 최대 3개
""".strip()


class OpenAIEvidenceJudge:
    """Select best snippet indices from evidence candidates."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_EVIDENCE_JUDGE_MODEL", "gpt-4o-mini")
        self._client = (
            OpenAI(api_key=self.api_key)
            if OpenAI is not None and self.api_key
            else None
        )
        self._cache: dict[str, list[int] | None] = {}

    @property
    def available(self) -> bool:
        return self._client is not None

    def judge(
        self,
        *,
        title: str,
        theme: str,
        why_it_matters: str,
        stance: str,
        candidates: list[str],
        timeout_seconds: int = 20,
        retry_limit: int = 1,
    ) -> list[int] | None:
        if self._client is None:
            return None

        normalized_candidates = [str(item).strip() for item in candidates if str(item).strip()]
        if len(normalized_candidates) < 2:
            return None

        cache_key = "||".join(
            [
                stance.strip().lower(),
                title.strip(),
                theme.strip(),
                why_it_matters.strip(),
                *normalized_candidates,
            ]
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        enumerated = "\n".join(
            f"{index + 1}. {candidate}"
            for index, candidate in enumerate(normalized_candidates)
        )
        user_prompt = (
            "아래 구매 근거 블록과 후보 스니펫을 읽고, 가장 적합한 스니펫 인덱스를 선택하세요.\n"
            f"- block_title: {title}\n"
            f"- block_theme: {theme}\n"
            f"- block_stance: {stance}\n"
            f"- why_it_matters: {why_it_matters}\n"
            "- 최소 2개, 최대 3개 선택\n"
            "- JSON only\n\n"
            f"candidates:\n{enumerated}"
        )

        result: list[int] | None = None
        for _ in range(retry_limit + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    continue
                payload = json.loads(content)
                validated = _validate_judge_payload(payload, candidate_count=len(normalized_candidates))
                if validated is not None:
                    result = validated
                    break
            except Exception:
                continue

        self._cache[cache_key] = result
        return result


def _validate_judge_payload(payload: Any, *, candidate_count: int) -> list[int] | None:
    if not isinstance(payload, dict):
        return None
    indices = payload.get("selected_indices")
    if not isinstance(indices, list):
        return None

    normalized: list[int] = []
    seen: set[int] = set()
    for value in indices:
        if isinstance(value, bool):
            continue
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if index < 1 or index > candidate_count:
            continue
        if index in seen:
            continue
        seen.add(index)
        normalized.append(index)

    if len(normalized) < 2 or len(normalized) > 3:
        return None
    return normalized
