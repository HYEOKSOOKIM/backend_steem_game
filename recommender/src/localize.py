from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path


CONFIDENCE_KO = {
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
}

GENRE_KO = {
    "Action": "액션",
    "Adventure": "어드벤처",
    "Massively Multiplayer": "대규모 멀티플레이",
    "RPG": "RPG",
    "Strategy": "전략",
    "Free To Play": "무료 플레이",
    "Casual": "캐주얼",
    "Indie": "인디",
    "Simulation": "시뮬레이션",
    "Sports": "스포츠",
    "Racing": "레이싱",
    "Survival": "생존",
    "FPS": "FPS",
    "Horror": "호러",
}

_EN_RE = re.compile(r"[A-Za-z]")
_DEFAULT_TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-tc-big-en-ko"
_LAST_CHECKIN: dict[str, object] = {
    "ready": None,
    "checked_at": None,
    "model": None,
    "cache_dir": None,
    "error": "",
}


def confidence_to_ko(label: str) -> str:
    return CONFIDENCE_KO.get((label or "").lower(), label or "정보 없음")


def genre_to_ko(genre: str) -> str:
    return GENRE_KO.get(genre, genre)


def _looks_english(text: str) -> bool:
    return bool(_EN_RE.search(text or ""))


def _runtime_info() -> tuple[str, str]:
    model_name = (os.getenv("TRANSLATION_MODEL") or _DEFAULT_TRANSLATION_MODEL).strip()
    cache_dir = os.getenv("HF_HOME")
    if not cache_dir:
        # Keep model cache inside project to avoid user-profile cache lock/permission issues.
        cache_dir = str(Path(__file__).resolve().parents[2] / ".hf_cache")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = cache_dir
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(Path(cache_dir) / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(Path(cache_dir) / "transformers")
    return model_name, cache_dir


@lru_cache(maxsize=1)
def _load_translator():
    # Lazy-load translator only when needed.
    model_name, _ = _runtime_info()
    from transformers import pipeline

    return pipeline("translation_en_to_ko", model=model_name)


def warmup_translation_checkin() -> dict[str, object]:
    model_name, cache_dir = _runtime_info()
    ready = False
    error = ""
    try:
        translator = _load_translator()
        out = translator("Great game with fun gameplay.", max_length=64)
        ready = bool(isinstance(out, list) and out and out[0].get("translation_text"))
        if not ready:
            error = "empty_translation_output"
    except Exception as exc:
        error = repr(exc)

    _LAST_CHECKIN.update(
        {
            "ready": ready,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "cache_dir": cache_dir,
            "error": error,
        }
    )
    return dict(_LAST_CHECKIN)


def get_translation_checkin_status() -> dict[str, object]:
    if _LAST_CHECKIN.get("model") is None or _LAST_CHECKIN.get("cache_dir") is None:
        model_name, cache_dir = _runtime_info()
        _LAST_CHECKIN.update({"model": model_name, "cache_dir": cache_dir})
    return dict(_LAST_CHECKIN)


def translate_en_to_ko(text: str) -> str:
    if not text:
        return text
    if not _looks_english(text):
        return text
    try:
        translator = _load_translator()
        out = translator(text, max_length=512)
        if isinstance(out, list) and out:
            return out[0].get("translation_text", text)
    except Exception:
        return text
    return text
