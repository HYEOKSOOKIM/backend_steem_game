"""Consumer-facing purchase decision report builders."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from report.analysis.rules import clean_markup_text
from report.models.schemas import AnalysisResult, GameMetadata, ProcessedReview, RawReview
from report.services.evidence_judge_llm import OpenAIEvidenceJudge
from report.services.korean_report_proofreader import KoreanReportProofreader
from report.services.player_fit_mapper import (
    build_display_theme,
    build_evidence_title,
    build_evidence_why_it_matters,
    build_experience_summary,
    build_fit_signal,
    build_headline_theme,
    build_player_fit_phrase,
)
from report.services.report_writer_llm import OpenAIReportWriter, validate_structured_report_payload

logger = logging.getLogger(__name__)

MIN_REPORT_REVIEW_COUNT = 100
REPORT_STATE_READY = "ready"
REPORT_STATE_INSUFFICIENT_REVIEWS = "insufficient_reviews"

CATEGORY_DISPLAY = {
    "balance": "밸런스",
    "performance": "성능/최적화",
    "bugs": "버그/안정성",
    "content_depth": "콘텐츠 볼륨",
    "difficulty": "진입 난이도",
    "difficulty_onboarding": "튜토리얼/초반 진입",
    "controls": "조작/UI",
    "matchmaking": "매칭/서버",
    "multiplayer": "멀티플레이",
    "localization": "번역/로컬라이징",
    "graphics": "그래픽/비주얼",
    "sound": "사운드",
    "monetization": "과금/가격",
    "gameplay": "전투/핵심 플레이",
    "story": "스토리/몰입",
    "customization": "커스터마이징",
    "building_ux": "건축/배치 UX",
    "save_progression": "저장/진행 안정성",
    "mod_support": "모드 지원/호환성",
}

NEGATIVE_THEME_HINTS = {
    "불편",
    "문제",
    "부족",
    "버그",
    "오류",
    "렉",
    "프레임",
    "튕김",
    "충돌",
    "지루",
    "반복",
    "과금",
    "스트레스",
    "하락",
    "느림",
    "불안정",
    "매칭",
    "서버",
}

POSITIVE_THEME_HINTS = {
    "재미",
    "몰입",
    "완성도",
    "호평",
    "좋음",
    "매력",
    "만족",
    "탄탄",
    "훌륭",
    "쾌감",
    "중독",
    "손맛",
}

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

ASPECT_EVIDENCE_HINTS = {
    "gameplay": ("전투", "타격", "손맛", "보스", "무기", "빌드", "스킬", "탐험"),
    "performance": ("프레임", "렉", "끊김", "최적화", "버벅", "튕김"),
    "bugs": ("버그", "오류", "에러", "멈춤", "충돌"),
    "monetization": ("가격", "과금", "현질", "유료", "결제", "확장팩"),
    "story": ("스토리", "서사", "몰입", "캐릭터", "연출"),
    "difficulty": ("난이도", "어려", "초보", "튜토리얼", "입문"),
    "difficulty_onboarding": ("튜토리얼", "설명", "가이드", "입문", "초반"),
    "graphics": ("그래픽", "비주얼", "연출", "아트", "풍경"),
    "sound": ("사운드", "음악", "bgm", "효과음", "음향"),
    "controls": ("조작", "ui", "키설정", "인터페이스", "입력"),
    "content_depth": ("볼륨", "콘텐츠", "반복", "파밍", "엔드게임"),
    "customization": ("커스터마이징", "외형", "빌드", "의상", "꾸미"),
    "save_progression": ("저장", "세이브", "진행", "롤백", "손실"),
    "matchmaking": ("매칭", "큐", "서버", "대기시간", "핑"),
    "multiplayer": ("멀티", "협동", "팀플", "파티", "네트워크"),
    "balance": ("밸런스", "메타", "너프", "버프", "불공정"),
    "localization": ("번역", "로컬", "자막", "텍스트", "오역"),
}

PAID_RECOMMENDATIONS = {"buy_now", "buy_on_sale", "wait", "not_recommended"}
FREE_RECOMMENDATIONS = {"free_play_recommended", "play_now", "try_lightly", "wait", "not_recommended"}
ALL_RECOMMENDATIONS = PAID_RECOMMENDATIONS | FREE_RECOMMENDATIONS

# Buyer-facing replacement layer (applied right before payload return).
# Keeps internal taxonomy intact while avoiding category-like labels in rendered text.
FORBIDDEN_LABEL_REPLACEMENTS: dict[str, str] = {
    "조작 / 규칙 학습 난이도": "초반 적응은 필요하지만 익숙해지면 손맛이 살아나는 플레이 구조",
    "전투 손맛 / 액션 호평": "전투가 반복될수록 손에 붙고 몰입이 올라가는 액션 경험",
    "스토리 / 서사 몰입": "세계관과 연출 덕분에 플레이를 계속하게 되는 몰입 경험",
    "스토리/서사 몰입": "세계관과 연출 덕분에 플레이를 계속하게 되는 몰입 경험",
    "최적화 문제": "프레임 저하나 끊김으로 전투/이동 흐름이 깨질 수 있는 리스크",
    "일반 버그": "예상치 못한 오류가 플레이 리듬을 끊을 수 있는 리스크",
    "가격/ 과금 불만": "가격 대비 만족도가 갈려 구매 타이밍을 따져봐야 하는 포인트",
    "가격 / 과금 불만": "가격 대비 만족도가 갈려 구매 타이밍을 따져봐야 하는 포인트",
    "DLC / 확장팩 언급": "추가 콘텐츠 가치가 확실할 때 만족도가 높아지는 포인트",
    "반복 / 목적성 부족": "중후반 반복감이 커지면 동기 유지가 떨어질 수 있는 리스크",
    "매칭 / 서버 문제": "매칭 대기나 서버 상태에 따라 체감 품질이 흔들릴 수 있는 리스크",
    "밸런스 불만": "특정 구간 불공정 체감이 누적되면 피로도가 높아질 수 있는 리스크",
    "번역/현지화 품질": "한국어 품질에 따라 몰입과 진입장벽이 크게 달라지는 포인트",
    "건축 조작 불편": "배치/건설 인터랙션이 익숙해지기 전 불편할 수 있는 구간",
    "콘텐츠 부족": "플레이 시간이 누적될수록 새로움이 빨리 소진될 수 있는 리스크",
    "세이브 / 진행 유실": "진행 데이터 안정성이 만족도를 크게 좌우하는 리스크",
}


def build_game_context_payload(appid: int, metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build consumer-facing game context with stable image fallbacks."""
    metadata_payload = metadata or {}
    header_image = _metadata_text(metadata_payload.get("header_image"))
    capsule_image = _metadata_text(metadata_payload.get("capsule_image"))
    capsule_imagev5 = _metadata_text(metadata_payload.get("capsule_imagev5"))

    return {
        "name": metadata_payload.get("name"),
        "genres": list(metadata_payload.get("genres", []) or []),
        "price_model": metadata_payload.get("price_model"),
        "is_free": metadata_payload.get("is_free"),
        "release_stage": metadata_payload.get("release_stage"),
        "release_date_text": metadata_payload.get("release_date_text"),
        "header_image": header_image or f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
        "capsule_image": capsule_image or f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_616x353.jpg",
        "capsule_imagev5": capsule_imagev5 or f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
        "short_description": _metadata_text(metadata_payload.get("short_description")),
        "steam_store_url": _metadata_text(metadata_payload.get("steam_store_url"))
        or f"https://store.steampowered.com/app/{appid}",
        "steam_recommendation_count": metadata_payload.get("steam_recommendation_count"),
        "steam_review_score_desc": _metadata_text(metadata_payload.get("steam_review_score_desc")),
        "steam_total_positive": metadata_payload.get("steam_total_positive"),
        "steam_total_negative": metadata_payload.get("steam_total_negative"),
        "steam_total_reviews": metadata_payload.get("steam_total_reviews"),
    }


def _metadata_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _report_state_for_review_count(source_review_count: Any) -> str:
    try:
        count = int(source_review_count or 0)
    except (TypeError, ValueError):
        count = 0
    if count < MIN_REPORT_REVIEW_COUNT:
        return REPORT_STATE_INSUFFICIENT_REVIEWS
    return REPORT_STATE_READY


def enrich_report_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach the current report availability policy to an existing payload."""
    next_payload = dict(payload)
    source_count = next_payload.get("source_review_count")
    next_payload["min_report_review_count"] = MIN_REPORT_REVIEW_COUNT
    next_payload["report_state"] = _report_state_for_review_count(source_count)
    return next_payload


def enrich_review_trend(payload: dict[str, Any], processed_reviews: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Attach monthly review sentiment trend when old report snapshots lack it."""
    existing_trend = payload.get("review_trend")
    if isinstance(existing_trend, dict) and existing_trend.get("granularity") == "month":
        return payload
    next_payload = dict(payload)
    next_payload["review_trend"] = build_review_trend_payload(processed_reviews or [])
    return next_payload


def build_review_trend_payload(processed_reviews: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Build monthly positive-ratio points from processed Steam reviews."""
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"positive": 0, "total": 0})
    for review in processed_reviews or []:
        timestamp = _safe_int(review.get("timestamp_created"))
        if timestamp is None or timestamp <= 0:
            continue
        bucket = _month_bucket_from_timestamp(timestamp)
        buckets[bucket]["total"] += 1
        if bool(review.get("voted_up")):
            buckets[bucket]["positive"] += 1

    points: list[dict[str, Any]] = []
    for bucket in sorted(buckets):
        total = buckets[bucket]["total"]
        positive = buckets[bucket]["positive"]
        points.append(
            {
                "month": bucket,
                "positive_count": positive,
                "review_count": total,
                "positive_ratio": round(positive / total, 4) if total > 0 else None,
            }
        )

    return {
        "granularity": "month",
        "metric": "positive_ratio",
        "points": points,
    }


def _month_bucket_from_timestamp(timestamp_created: int) -> str:
    dt = datetime.fromtimestamp(timestamp_created, tz=timezone.utc)
    return f"{dt.year}-{dt.month:02d}"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_consumer_report_payload(payload: Any) -> bool:
    """Return True when payload matches the multi-stage report contract."""
    return validate_structured_report_payload(payload)


def build_report_ready_data(
    *,
    appid: int,
    metadata: GameMetadata,
    analysis: AnalysisResult,
    raw_reviews: list[RawReview],
    processed_reviews: list[ProcessedReview],
    report_materials: list[dict[str, Any]] | None = None,
    pipeline_run_id: str,
) -> dict[str, Any]:
    """Build and return a purchase decision report payload."""
    metadata_payload = metadata.to_dict()
    analysis_payload = analysis.to_dict()
    processed_payload = [review.to_dict() for review in processed_reviews]
    included_count = sum(1 for review in processed_payload if review.get("included_in_analysis"))

    consensus_payload = _build_consensus_payload(
        appid=appid,
        metadata=metadata_payload,
        analysis=analysis_payload,
        processed_reviews=processed_payload,
        report_materials=report_materials or [],
        included_count=included_count,
    )

    structured_report = _build_structured_report_bundle(
        consensus_payload=consensus_payload,
        enable_llm_sections=True,
        enable_llm_evidence_compression=True,
    )

    payload = {
        "report_version": "v4-planned-sections",
        "appid": appid,
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_review_count": len(raw_reviews),
        "included_review_count": included_count,
        "min_report_review_count": MIN_REPORT_REVIEW_COUNT,
        "report_state": _report_state_for_review_count(len(raw_reviews)),
        "review_trend": build_review_trend_payload(processed_payload),
        "game": build_game_context_payload(appid, metadata_payload),
        **structured_report,
        "disclaimer": "여러 유저 리뷰를 바탕으로 정리했어요. 플레이 경험은 사람마다 다를 수 있어요.",
    }
    return _attach_legacy_flat_fields(payload)


def build_consumer_report_from_snapshot(
    *,
    appid: int,
    metadata: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    processed_reviews: list[dict[str, Any]] | None = None,
    report_materials: list[dict[str, Any]] | None = None,
    pipeline_run_id: str | None = None,
    source_review_count: int | None = None,
) -> dict[str, Any]:
    """Build deterministic report for read-only fallback serving."""
    metadata_payload = metadata or {}
    analysis_payload = analysis or {}
    processed_payload = processed_reviews or []
    included_count = sum(1 for review in processed_payload if review.get("included_in_analysis"))

    consensus_payload = _build_consensus_payload(
        appid=appid,
        metadata=metadata_payload,
        analysis=analysis_payload,
        processed_reviews=processed_payload,
        report_materials=report_materials or [],
        included_count=included_count,
    )
    structured_report = _build_structured_report_bundle(
        consensus_payload=consensus_payload,
        enable_llm_sections=False,
        enable_llm_evidence_compression=False,
    )

    payload = {
        "report_version": "v4-planned-sections",
        "appid": appid,
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_review_count": source_review_count,
        "included_review_count": included_count,
        "min_report_review_count": MIN_REPORT_REVIEW_COUNT,
        "report_state": _report_state_for_review_count(source_review_count),
        "review_trend": build_review_trend_payload(processed_payload),
        "game": build_game_context_payload(appid, metadata_payload),
        **structured_report,
        "disclaimer": "여러 유저 리뷰를 바탕으로 정리했어요. 플레이 경험은 사람마다 다를 수 있어요.",
    }
    return _attach_legacy_flat_fields(payload)


def _should_use_llm_report_writer() -> bool:
    return os.getenv("USE_LLM_REPORT_WRITER", "true").strip().lower() in {"1", "true", "yes", "on"}


def _should_use_llm_material_rewrite() -> bool:
    return os.getenv("USE_LLM_MATERIAL_REWRITE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _should_use_llm_evidence_judge() -> bool:
    return os.getenv("USE_LLM_EVIDENCE_JUDGE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _should_use_title_why_similarity_ranking() -> bool:
    return os.getenv("USE_TITLE_WHY_SIMILARITY_RANKING", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_structured_report_bundle(
    *,
    consensus_payload: dict[str, Any],
    enable_llm_sections: bool,
    enable_llm_evidence_compression: bool,
) -> dict[str, Any]:
    """Run multi-stage report generation:
    1) report_plan
    2) section-wise report_display
    3) evidence grouping + snippet compression
    """
    seed_display = _build_report_deterministic(consensus_payload)
    seed_plan = _build_report_plan_deterministic(consensus_payload, seed_display)
    seed_evidence_sections = _build_evidence_sections_from_blocks(
        list(seed_display.get("evidence_reviews", []) or [])
    )

    report_plan = seed_plan
    report_display = {k: v for k, v in seed_display.items() if k != "evidence_reviews"}
    writer = OpenAIReportWriter()

    if enable_llm_sections and _should_use_llm_report_writer() and writer.available:
        logger.info(
            "report_llm_writer enabled plan_model=%s display_model=%s",
            writer.plan_model,
            writer.display_model,
        )
        llm_plan = writer.generate_report_plan(
            consensus_payload=consensus_payload,
            seed_plan=seed_plan,
        )
        if isinstance(llm_plan, dict):
            report_plan = llm_plan

        llm_display = writer.generate_report_display(
            consensus_payload=consensus_payload,
            report_plan=report_plan,
            seed_display=report_display,
        )
        if isinstance(llm_display, dict):
            report_display = llm_display

    evidence_sections = _compress_evidence_sections(
        seed_evidence_sections,
        use_llm=enable_llm_evidence_compression,
    )
    evidence_sections = _truncate_evidence_sections_by_plan(evidence_sections, report_plan)

    payload = {
        "report_plan": report_plan,
        "report_display": report_display,
        "evidence_sections": evidence_sections,
    }
    if validate_structured_report_payload(payload):
        finalized = _apply_price_aware_recommendation_to_payload(
            payload=payload,
            consensus_payload=consensus_payload,
        )
        finalized = _apply_final_language_polish(
            payload=finalized,
            allow_llm=bool(enable_llm_sections),
            is_free_game=_is_free_game(consensus_payload),
            seed_display=seed_display,
            genres=list((consensus_payload.get("game_context", {}) or {}).get("genres", []) or []),
        )
        if validate_structured_report_payload(finalized):
            return finalized

    # Hard fallback to deterministic multi-stage result.
    fallback = {
        "report_plan": seed_plan,
        "report_display": {k: v for k, v in seed_display.items() if k != "evidence_reviews"},
        "evidence_sections": _truncate_evidence_sections_by_plan(
            _compress_evidence_sections(seed_evidence_sections, use_llm=False),
            seed_plan,
        ),
    }
    fallback = _apply_price_aware_recommendation_to_payload(
        payload=fallback,
        consensus_payload=consensus_payload,
    )
    fallback = _apply_final_language_polish(
        payload=fallback,
        allow_llm=False,
        is_free_game=_is_free_game(consensus_payload),
        seed_display=seed_display,
        genres=list((consensus_payload.get("game_context", {}) or {}).get("genres", []) or []),
    )
    return fallback


def _build_report_plan_deterministic(
    consensus_payload: dict[str, Any],
    seed_display: dict[str, Any],
) -> dict[str, Any]:
    aspects = list(consensus_payload.get("consensus_aspects", []) or [])
    strengths = [item for item in aspects if _block_stance(item) == "positive"][:3]
    risks = [item for item in aspects if _block_stance(item) == "negative"][:3]
    recommendation = str(seed_display.get("buy_recommendation", "buy_on_sale"))

    strength_reasons = [
        {
            "reason_id": f"str_{index + 1}",
            "aspect": str(item.get("aspect", "")),
            "theme": _pick_block_theme(item, "positive")
            or str(item.get("aspect_label", "핵심 강점")),
        }
        for index, item in enumerate(strengths)
    ]
    risk_reasons = [
        {
            "reason_id": f"risk_{index + 1}",
            "aspect": str(item.get("aspect", "")),
            "theme": _pick_block_theme(item, "negative")
            or str(item.get("aspect_label", "핵심 리스크")),
        }
        for index, item in enumerate(risks)
    ]
    primary_reason_ids = [item["reason_id"] for item in (risk_reasons + strength_reasons)[:2]]

    return {
        "decision_anchor": {
            "buy_recommendation": recommendation,
            "primary_reason_ids": primary_reason_ids,
            "rationale_short": str(seed_display.get("buy_timing_summary", "")),
        },
        "section_blueprint": {
            "strength_block_count": 3,
            "risk_block_count": 3,
            "evidence_per_block": 3,
        },
        "theme_priorities": {
            "strengths": strength_reasons,
            "risks": risk_reasons,
        },
    }


def _is_llm_proofread_enabled() -> bool:
    primary = os.getenv("USE_LLM_PROOFREAD")
    if primary is not None:
        return primary.strip().lower() in {"1", "true", "yes", "on"}
    # Backward compatibility for previous env key.
    legacy = os.getenv("USE_LLM_REPORT_PROOFREAD", "true")
    return legacy.strip().lower() in {"1", "true", "yes", "on"}


def _is_free_game(consensus_payload: dict[str, Any]) -> bool:
    game_context = consensus_payload.get("game_context", {}) if isinstance(consensus_payload, dict) else {}
    if bool(game_context.get("is_free")):
        return True
    return str(game_context.get("price_model", "")) == "free_to_play"


def _to_price_aware_recommendation(value: str, *, is_free_game: bool) -> str:
    recommendation = str(value or "").strip()
    if not recommendation:
        recommendation = "buy_on_sale"
    if recommendation not in ALL_RECOMMENDATIONS:
        recommendation = "buy_on_sale"

    if not is_free_game:
        if recommendation in FREE_RECOMMENDATIONS - {"wait", "not_recommended"}:
            return "buy_now"
        return recommendation if recommendation in PAID_RECOMMENDATIONS else "buy_on_sale"

    free_mapping = {
        "buy_now": "free_play_recommended",
        "buy_on_sale": "try_lightly",
        "free_play_recommended": "free_play_recommended",
        "play_now": "play_now",
        "try_lightly": "try_lightly",
        "wait": "wait",
        "not_recommended": "not_recommended",
    }
    return free_mapping.get(recommendation, "try_lightly")


def _apply_price_aware_recommendation_to_payload(
    *,
    payload: dict[str, Any],
    consensus_payload: dict[str, Any],
) -> dict[str, Any]:
    is_free_game = _is_free_game(consensus_payload)
    report_plan = dict(payload.get("report_plan", {}) or {})
    report_display = dict(payload.get("report_display", {}) or {})

    decision_anchor = dict(report_plan.get("decision_anchor", {}) or {})
    plan_rec = _to_price_aware_recommendation(
        str(decision_anchor.get("buy_recommendation", report_display.get("buy_recommendation", "buy_on_sale"))),
        is_free_game=is_free_game,
    )
    decision_anchor["buy_recommendation"] = plan_rec
    report_plan["decision_anchor"] = decision_anchor

    display_rec = _to_price_aware_recommendation(
        str(report_display.get("buy_recommendation", plan_rec)),
        is_free_game=is_free_game,
    )
    report_display["buy_recommendation"] = display_rec

    if is_free_game:
        report_display["headline"] = _rewrite_free_game_text(str(report_display.get("headline", "")))
        report_display["buy_timing_summary"] = _rewrite_free_game_text(
            str(report_display.get("buy_timing_summary", ""))
        )

    merged = dict(payload)
    merged["report_plan"] = report_plan
    merged["report_display"] = report_display
    return merged


def _rewrite_free_game_text(text: str) -> str:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return normalized

    replacements = (
        ("할인 구매", "무료 플레이"),
        ("할인 시점", "시작 시점"),
        ("할인", "무료"),
        ("지금 구매", "지금 플레이"),
        ("구매", "플레이"),
        ("사는 것이", "시작하는 것이"),
        ("사도", "플레이해도"),
        ("사는 편이", "시작하는 편이"),
    )
    result = normalized
    for before, after in replacements:
        result = result.replace(before, after)
    return result


_PLAYER_FIT_BAD_FRAGMENTS = (
    "상황의 플레이어",
    "상황의 유저",
    "플레이할 수 있는 상황",
    "즐길 수 있는 상황",
)


def _normalize_player_fit_phrase(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    value = value.rstrip(".!?。！？ ")
    replacements = (
        ("플레이어이다", "플레이어"),
        ("플레이어입니다", "플레이어"),
        ("플레이어예요", "플레이어"),
        ("플레이어에요", "플레이어"),
        ("플레이어는", "플레이어"),
        ("플레이어은", "플레이어"),
        ("유저이다", "유저"),
        ("유저입니다", "유저"),
        ("유저예요", "유저"),
        ("유저에요", "유저"),
        ("유저는", "유저"),
        ("분입니다", "분"),
        ("분이에요", "분"),
        ("분이에용", "분"),
        ("분은", "분"),
    )
    for before, after in replacements:
        if value.endswith(before):
            value = value[: -len(before)] + after
            break
    value = re.sub(r"(플레이어|유저|분)(?:[는은이가]|이다|입니다|이에요|예요)$", r"\1", value)
    return value.strip(" ,")


def _normalize_card_title(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    value = value.rstrip(".!?。！？ ")
    if len(value) >= 10 and value.endswith(("이다", "입니다", "예요", "이에요")):
        value = re.sub(r"(이다|입니다|예요|이에요)$", "", value).strip()
    if len(value) >= 10 and value.endswith(("는", "은")):
        value = value[:-1].strip()
    return value


def _looks_generic_player_fit_phrase(text: str) -> bool:
    value = str(text or "")
    if not value:
        return True
    if any(fragment in value for fragment in _PLAYER_FIT_BAD_FRAGMENTS):
        return True
    if len(value) >= 44:
        return True
    return False


def _stabilize_player_fit_list(values: list[Any], seed_values: list[Any]) -> list[str]:
    stabilized: list[str] = []
    max_items = max(len(values), len(seed_values))
    for index in range(max_items):
        candidate = _normalize_player_fit_phrase(values[index]) if index < len(values) else ""
        seed = _normalize_player_fit_phrase(seed_values[index]) if index < len(seed_values) else ""
        final = candidate
        if not final:
            final = seed
        elif _looks_generic_player_fit_phrase(final) and seed:
            final = seed
        if final and final not in stabilized:
            stabilized.append(final)
    return stabilized


def _apply_final_language_polish(
    *,
    payload: dict[str, Any],
    allow_llm: bool,
    is_free_game: bool,
    seed_display: dict[str, Any] | None = None,
    genres: list[str] | None = None,
) -> dict[str, Any]:
    report_plan = dict(payload.get("report_plan", {}) or {})
    report_display = dict(payload.get("report_display", {}) or {})
    evidence_sections = payload.get("evidence_sections", {}) or {}
    seed_display = dict(seed_display or {})
    context_text = _context_text(payload.get("game", {}) or {})

    # Apply forbidden-label replacement first (title/theme only),
    # then run proofreading on the final wording.
    report_display = _apply_forbidden_label_replacements_to_display(report_display)
    evidence_sections = _apply_forbidden_label_replacements_to_sections(evidence_sections)

    proofreader = KoreanReportProofreader()
    llm_enabled = bool(allow_llm and _is_llm_proofread_enabled() and proofreader.available)
    logger.info(
        "report_llm_proofreader enabled=%s model=%s",
        llm_enabled,
        proofreader.model,
    )

    def _fix(text: str, *, allow_llm_override: bool | None = None) -> str:
        source = _rewrite_free_game_text(text) if is_free_game else str(text or "")
        use_llm = llm_enabled if allow_llm_override is None else bool(allow_llm_override)
        return proofreader.proofread_text(source, allow_llm=use_llm)

    decision_anchor = dict(report_plan.get("decision_anchor", {}) or {})
    if isinstance(decision_anchor.get("rationale_short"), str):
        decision_anchor["rationale_short"] = _fix(str(decision_anchor.get("rationale_short", "")))
    report_plan["decision_anchor"] = decision_anchor

    if isinstance(report_display.get("headline"), str):
        report_display["headline"] = _rewrite_headline_for_context(
            _fix(str(report_display.get("headline", ""))),
            genres=genres or [],
            fallback=str(seed_display.get("headline", "")),
            context_text=context_text,
        )
    if isinstance(report_display.get("buy_timing_summary"), str):
        report_display["buy_timing_summary"] = _fix(str(report_display.get("buy_timing_summary", "")))

    good_for = []
    for item in list(report_display.get("good_for", []) or []):
        good_for.append(_fix(str(item), allow_llm_override=False))
    report_display["good_for"] = _guard_player_fit_list_by_genre(
        _stabilize_player_fit_list(
            good_for,
            list(seed_display.get("good_for", []) or []),
        ),
        list(seed_display.get("good_for", []) or []),
        genres or [],
        context_text=context_text,
    )

    not_good_for = []
    for item in list(report_display.get("not_good_for", []) or []):
        not_good_for.append(_fix(str(item), allow_llm_override=False))
    report_display["not_good_for"] = _guard_player_fit_list_by_genre(
        _stabilize_player_fit_list(
            not_good_for,
            list(seed_display.get("not_good_for", []) or []),
        ),
        list(seed_display.get("not_good_for", []) or []),
        genres or [],
        context_text=context_text,
    )

    top_strengths = []
    seed_strengths = list(seed_display.get("top_strengths", []) or [])
    seen_strength_titles: set[str] = set()
    for index, item in enumerate(list(report_display.get("top_strengths", []) or [])):
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        seed_item = seed_strengths[index] if index < len(seed_strengths) and isinstance(seed_strengths[index], dict) else {}
        if isinstance(next_item.get("title"), str):
            next_item["title"] = _guard_copy_text_by_genre(
                _normalize_card_title(_fix(str(next_item.get("title", "")))),
                genres or [],
                fallback=_normalize_card_title(str(seed_item.get("title", ""))),
                context_text=context_text,
            )
        if isinstance(next_item.get("summary"), str):
            next_item["summary"] = _guard_copy_text_by_genre(
                _fix(str(next_item.get("summary", ""))),
                genres or [],
                fallback=str(seed_item.get("summary", "")),
                context_text=context_text,
            )
        next_item["title"], next_item["summary"] = _rewrite_generic_strength_for_context(
            title=str(next_item.get("title", "") or ""),
            summary=str(next_item.get("summary", "") or ""),
            genres=genres or [],
            context_text=context_text,
        )
        title_key = " ".join(str(next_item.get("title", "") or "").split()).strip()
        if title_key:
            if title_key in seen_strength_titles:
                continue
            seen_strength_titles.add(title_key)
        top_strengths.append(next_item)
    report_display["top_strengths"] = top_strengths

    top_risks = []
    seed_risks = list(seed_display.get("top_risks", []) or [])
    for index, item in enumerate(list(report_display.get("top_risks", []) or [])):
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        seed_item = seed_risks[index] if index < len(seed_risks) and isinstance(seed_risks[index], dict) else {}
        if isinstance(next_item.get("title"), str):
            next_item["title"] = _guard_copy_text_by_genre(
                _normalize_card_title(_fix(str(next_item.get("title", "")))),
                genres or [],
                fallback=_normalize_card_title(str(seed_item.get("title", ""))),
                context_text=context_text,
            )
        if isinstance(next_item.get("summary"), str):
            next_item["summary"] = _guard_copy_text_by_genre(
                _fix(str(next_item.get("summary", ""))),
                genres or [],
                fallback=str(seed_item.get("summary", "")),
                context_text=context_text,
            )
        next_item["title"], next_item["summary"] = _rewrite_generic_strength_for_context(
            title=str(next_item.get("title", "") or ""),
            summary=str(next_item.get("summary", "") or ""),
            genres=genres or [],
            context_text=context_text,
        )
        top_risks.append(next_item)
    report_display["top_risks"] = top_risks

    fit_blob = " ".join(str(item or "") for item in list(report_display.get("good_for", []) or []))
    looter_fit = any(token in fit_blob for token in ("장비", "파밍", "빌드", "성장 루프"))
    coop_fit = any(token in fit_blob for token in ("분대", "협동", "임무", "역할"))
    narrative_fit = any(token in fit_blob for token in ("사건", "인물", "서사", "여운"))

    if _is_looter_shooter_context(genres or [], context_text) or looter_fit:
        headline = " ".join(str(report_display.get("headline", "") or "").split()).strip()
        if headline and not any(token in headline for token in ("장비", "파밍", "성장", "빌드")):
            report_display["headline"] = "장비 파밍과 성장 루프의 장점이 보여 무료로 가볍게 시작해보고 맞는지 판단하기 좋습니다."
        if report_display["top_strengths"]:
            first_strength = report_display["top_strengths"][0]
            title = " ".join(str(first_strength.get("title", "") or "").split()).strip()
            if title and not any(token in title for token in ("장비", "파밍", "성장", "빌드")):
                first_strength["title"] = "장비와 빌드를 오래 다듬는 성장 루프"
                first_strength["summary"] = "장비를 파밍하고 세팅을 맞춰 가며 강해지는 과정이 반복 임무의 동력으로 잘 이어집니다."

    if _is_coop_live_service_shooter_context(genres or [], context_text) or coop_fit:
        headline = " ".join(str(report_display.get("headline", "") or "").split()).strip()
        if headline and not any(token in headline for token in ("분대", "협동", "임무")):
            report_display["headline"] = "분대 협동과 임무 수행의 재미는 분명하지만 밸런스와 안정성 변수는 함께 감수해야 합니다."
        if report_display["top_strengths"]:
            first_strength = report_display["top_strengths"][0]
            title = " ".join(str(first_strength.get("title", "") or "").split()).strip()
            if title and not any(token in title for token in ("분대", "협동", "임무")):
                first_strength["title"] = "분대 합이 살아나는 협동 임무"
                first_strength["summary"] = "역할을 나눠 임무를 밀어붙일수록 분대 플레이의 손발이 맞는 재미가 살아납니다."

    if _is_narrative_openworld_context(genres or [], context_text) or narrative_fit:
        headline = " ".join(str(report_display.get("headline", "") or "").split()).strip()
        if headline and (
            not any(token in headline for token in ("사건", "인물", "서사", "여운"))
            or "체감" in headline
        ):
            report_display["headline"] = "사건과 인물의 여운이 오래 남는 경험은 분명한 강점이지만 긴 호흡의 진행 템포는 취향을 탈 수 있습니다."
        if report_display["top_strengths"]:
            first_strength = report_display["top_strengths"][0]
            title = " ".join(str(first_strength.get("title", "") or "").split()).strip()
            if title and not any(token in title for token in ("사건", "인물", "서사", "여운")):
                first_strength["title"] = "사건과 인물이 오래 남는 서사 경험"
                first_strength["summary"] = "사건과 인물의 여운이 길게 남아 세계를 천천히 체험하는 몰입감이 또렷합니다."
        for next_item in report_display["top_risks"]:
            title = " ".join(str(next_item.get("title", "") or "").split()).strip()
            summary = " ".join(str(next_item.get("summary", "") or "").split()).strip()
            blob = f"{title} {summary}"
            if title == "몰입을 끊는 기술 이슈" or any(token in blob for token in ("매칭", "서버 상태", "멀티플레이")):
                next_item["title"] = "몰입을 끊는 기술 이슈"
                next_item["summary"] = "기술적인 끊김이나 거슬림이 길게 이어지면 서사와 장면의 몰입이 쉽게 흐트러질 수 있습니다."

    if _is_soulslike_context(genres or [], context_text):
        headline = " ".join(str(report_display.get("headline", "") or "").split()).strip()
        if headline and (
            any(token in headline for token in ("핵심 플레이", "가격 대비", "팀 플레이"))
            or not any(token in headline for token in ("보스", "패턴", "도전", "돌파", "성취"))
        ):
            report_display["headline"] = "보스 패턴을 익히며 돌파하는 성취감은 분명하지만 초반 진입 장벽과 반복 트라이 피로는 감수해야 합니다."
        if report_display["top_strengths"]:
            first_strength = report_display["top_strengths"][0]
            title = " ".join(str(first_strength.get("title", "") or "").split()).strip()
            if title and not any(token in title for token in ("보스", "패턴", "도전", "돌파", "성취")):
                first_strength["title"] = "보스 패턴을 익히며 돌파하는 성취감"
                first_strength["summary"] = "실패를 거듭하며 패턴을 읽고 결국 돌파하는 과정이 강한 긴장감과 성취감으로 이어집니다."
        for next_item in report_display["top_risks"]:
            title = " ".join(str(next_item.get("title", "") or "").split()).strip()
            summary = " ".join(str(next_item.get("summary", "") or "").split()).strip()
            blob = f"{title} {summary}"
            if any(token in blob for token in ("가격", "과금")):
                next_item["title"] = "진입 장벽이 높은 초반"
                next_item["summary"] = "초반에 길 찾기와 전투 리듬을 익히기까지 시간이 걸려 첫인상이 꽤 거칠게 느껴질 수 있습니다."
            elif any(token in blob for token in ("팀 플레이", "팀 호흡")):
                next_item["title"] = "반복 트라이에서 오는 피로"
                next_item["summary"] = "막히는 구간을 여러 번 다시 시도해야 해서 긴장감이 큰 만큼 피로도 빠르게 쌓일 수 있습니다."

    if _is_openworld_crime_sandbox_context(genres or [], context_text):
        headline = " ".join(str(report_display.get("headline", "") or "").split()).strip()
        if headline and any(token in headline for token in ("그래픽과 스토리", "업데이트 후가 좋습니다")):
            report_display["headline"] = "세 주인공 서사와 오픈월드 자유도는 분명한 강점이지만 온라인 안정성과 핵 문제는 함께 감수해야 합니다."
        if report_display["top_strengths"]:
            first_strength = report_display["top_strengths"][0]
            title = " ".join(str(first_strength.get("title", "") or "").split()).strip()
            if title and not any(token in title for token in ("서사", "자유도", "오픈월드", "범죄")):
                first_strength["title"] = "세 주인공이 끌고 가는 범죄 서사"
                first_strength["summary"] = "세 주인공의 시선이 엮이며 범죄극의 리듬이 살아나서 스토리 몰입감이 오래 이어집니다."

    recent_state = dict(report_display.get("recent_state", {}) or {})
    if isinstance(recent_state.get("summary"), str):
        recent_state["summary"] = _fix(str(recent_state.get("summary", "")))
    report_display["recent_state"] = recent_state

    def _fix_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fixed: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            next_block = dict(block)
            if isinstance(next_block.get("title"), str):
                next_block["title"] = _guard_copy_text_by_genre(
                    _soften_evidence_title_tone(_fix(str(next_block.get("title", "")))),
                    genres or [],
                    fallback=str(next_block.get("theme", "")),
                    context_text=context_text,
                )
            if isinstance(next_block.get("why_it_matters"), str):
                next_block["why_it_matters"] = _guard_copy_text_by_genre(
                    _fix(str(next_block.get("why_it_matters", ""))),
                    genres or [],
                    fallback=str(next_block.get("explanation", "")),
                    context_text=context_text,
                )
            if isinstance(next_block.get("explanation"), str):
                next_block["explanation"] = _guard_copy_text_by_genre(
                    _fix(str(next_block.get("explanation", ""))),
                    genres or [],
                    fallback=str(next_block.get("explanation", "")),
                    context_text=context_text,
                )
            snippets: list[str] = []
            for snippet in list(next_block.get("evidence_snippets", []) or []):
                # Evidence snippet is kept as rule-only polish to preserve original user wording.
                snippets.append(_fix(str(snippet), allow_llm_override=False))
            next_block["evidence_snippets"] = snippets
            fixed.append(next_block)
        return fixed

    next_sections = {
        "strengths": _fix_blocks(list(evidence_sections.get("strengths", []) or [])),
        "risks": _fix_blocks(list(evidence_sections.get("risks", []) or [])),
    }

    merged = dict(payload)
    merged["report_plan"] = report_plan
    merged["report_display"] = report_display
    merged["evidence_sections"] = next_sections
    return merged


def _guard_player_fit_list_by_genre(
    values: list[str],
    seed_values: list[Any],
    genres: list[str],
    *,
    context_text: str = "",
) -> list[str]:
    guarded: list[str] = []
    for index, value in enumerate(values):
        seed = _normalize_player_fit_phrase(seed_values[index]) if index < len(seed_values) else ""
        final = _guard_copy_text_by_genre(value, genres, fallback=seed, context_text=context_text)
        final = _soften_generic_player_fit_phrase(final)
        if final and final not in guarded:
            guarded.append(final)
    return guarded


def _rewrite_generic_strength_for_context(
    *,
    title: str,
    summary: str,
    genres: list[str],
    context_text: str = "",
) -> tuple[str, str]:
    title_value = " ".join(str(title or "").split()).strip()
    summary_value = " ".join(str(summary or "").split()).strip()
    blob = f"{title_value} {summary_value}".strip()

    if not blob:
        return title_value, summary_value

    if any(token in blob for token in ("핵심 플레이 감각", "손에 익을수록", "플레이 흐름의 안정감")):
        if _is_looter_shooter_context(genres, context_text):
            return (
                "장비와 빌드를 오래 다듬는 성장 루프",
                "장비를 파밍하고 세팅을 맞춰 가며 강해지는 과정이 반복 임무의 동력으로 잘 이어집니다.",
            )
        if _is_coop_live_service_shooter_context(genres, context_text):
            return (
                "분대 합이 살아나는 협동 임무",
                "역할을 나눠 임무를 밀어붙일수록 분대 플레이의 손발이 맞는 재미가 살아납니다.",
            )
        if _is_narrative_openworld_context(genres, context_text):
            return (
                "사건과 인물이 오래 남는 서사 경험",
                "사건과 인물의 여운이 길게 남아 세계를 천천히 체험하는 몰입감이 또렷합니다.",
            )
        if _is_soulslike_context(genres, context_text):
            return (
                "보스 패턴을 익히며 돌파하는 성취감",
                "실패를 거듭하며 패턴을 읽고 결국 돌파하는 과정이 강한 긴장감과 성취감으로 이어집니다.",
            )
        if _is_openworld_crime_sandbox_context(genres, context_text):
            return (
                "세 주인공이 끌고 가는 범죄 서사",
                "세 주인공의 시선이 엮이며 범죄극의 리듬이 살아나서 스토리 몰입감이 오래 이어집니다.",
            )
        if _is_life_sim_context(genres, context_text):
            return (
                "생활 루프와 꾸미기의 자유도",
                "일상과 공간을 내 취향대로 다듬어 가는 과정이 차분하게 이어지는 재미를 만듭니다.",
            )
        if _is_visual_novel_context(genres, context_text):
            return (
                "감정선이 오래 남는 서사 경험",
                "장면 전환과 감정선의 여운이 커서 이야기에 몰입할수록 장점이 더 또렷하게 남습니다.",
            )
        if _is_city_builder_context(genres, context_text):
            return (
                "도시 흐름을 다듬는 운영의 재미",
                "배치와 확장을 조정할수록 도시 전체 흐름이 안정적으로 맞물리는 재미가 살아 있습니다.",
            )
        if _is_automation_context(genres, context_text):
            return (
                "자동화 흐름을 다듬는 재미",
                "생산 라인과 병목을 정리할수록 효율이 또렷하게 올라가는 재미가 살아 있습니다.",
            )
        if _is_deckbuilder_context(genres, context_text):
            return (
                "덱이 손에 맞아가는 한 판 설계",
                "카드와 유물을 맞춰 가며 한 판의 방향을 세우는 과정이 점점 더 선명한 재미로 이어집니다.",
            )
        if _is_turn_based_tactics_context(genres, context_text):
            return (
                "턴마다 쌓이는 전술 긴장감",
                "한 번의 선택이 다음 턴 결과에 크게 이어져 전술 판단의 무게가 분명하게 살아 있습니다.",
            )

    if _is_coop_live_service_shooter_context(genres, context_text) and any(
        token in blob for token in ("장비와 빌드를 오래 다듬는 성장 루프", "장비를 모으는 재미", "장비와 빌드")
    ):
        return (
            "분대 합이 살아나는 협동 임무",
            "역할을 나눠 임무를 밀어붙일수록 분대 플레이의 손발이 맞는 재미가 살아납니다.",
        )

    if _is_turn_based_tactics_context(genres, context_text) and "전투/이동 흐름" in blob:
        return (
            "턴 흐름이 끊기는 구간",
            "프레임과 반응성이 흔들리면 턴 단위 판단이 답답하게 느껴질 수 있습니다.",
        )

    if _is_narrative_openworld_context(genres, context_text) and any(token in blob for token in ("매칭", "서버 상태")):
        return (
            "몰입을 끊는 기술 이슈",
            "기술적인 끊김이나 거슬림이 길게 이어지면 서사와 장면의 몰입이 쉽게 흐트러질 수 있습니다.",
        )

    return title_value, summary_value


def _soften_generic_player_fit_phrase(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    replacements = {
        "가격 대비 만족을 매우 엄격하게 따지는 플레이어": "비용 대비 만족을 꼼꼼하게 따지는 플레이어",
        "가격 대비 만족을 아주 엄격하게 따지는 플레이어": "비용 대비 만족을 꼼꼼하게 따지는 플레이어",
    }
    return replacements.get(value, value)


def _soften_evidence_title_tone(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    for ending in ("반응이다.", "반응이다", "반응입니다.", "반응입니다"):
        if value.endswith(ending):
            return value[: -len(ending)] + "반응"
    return value


def _rewrite_headline_for_context(
    headline: str,
    *,
    genres: list[str],
    fallback: str = "",
    context_text: str = "",
) -> str:
    value = " ".join(str(headline or "").split()).strip()
    if not value:
        return fallback.strip()

    if _is_looter_shooter_context(genres, context_text) and any(
        token in value for token in ("탐험과 세계 해석", "세계관과 맥락", "플레이 흐름의 안정감", "플레이 흐름")
    ):
        return "장비 파밍과 성장 루프의 장점이 보여 무료로 가볍게 시작해보고 맞는지 판단하기 좋습니다."

    if _is_coop_live_service_shooter_context(genres, context_text) and any(
        token in value for token in ("플레이 흐름의 안정감", "플레이 흐름", "장비와 빌드")
    ):
        return "분대 협동과 임무 수행의 재미는 분명하지만 밸런스와 안정성 변수는 함께 감수해야 합니다."

    if _is_narrative_openworld_context(genres, context_text) and any(
        token in value for token in ("플레이 흐름의 안정감", "매칭", "서버 상태", "짧고 강한 교전 템포")
    ):
        return "사건과 인물의 여운이 오래 남는 경험은 분명한 강점이지만 긴 호흡의 진행 템포는 취향을 탈 수 있습니다."

    if _is_soulslike_context(genres, context_text) and any(
        token in value for token in ("핵심 플레이", "가격 대비", "팀 플레이", "플레이 흐름")
    ):
        return "보스 패턴을 익히며 돌파하는 성취감은 분명하지만 초반 진입 장벽과 반복 트라이 피로는 감수해야 합니다."

    return value


def _guard_copy_text_by_genre(
    text: str,
    genres: list[str],
    *,
    fallback: str = "",
    context_text: str = "",
) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return fallback.strip()

    lowered = value.lower()
    genre_text = _genre_signal_blob(genres, context_text)

    def _has_any(*fragments: str) -> bool:
        return any(fragment in lowered for fragment in fragments)

    if _is_visual_novel_context(genres, context_text):
        if _has_any("전투", "교전", "손맛", "매칭", "서버", "핵심 플레이", "성장 루프", "보스"):
            return fallback.strip() or value

    if _is_looter_shooter_context(genres, context_text):
        if _has_any(
            "탐험과 세계 해석",
            "세계관과 맥락을 스스로 읽어가는",
            "맵을 돌아다니며 발견",
            "패턴을 익히며 반복 도전",
            "플레이 흐름이 점점 또렷해지는 재미",
            "배경과 연출이 만드는 분위기",
        ):
            return fallback.strip() or "장비와 빌드를 오래 다듬는 플레이어"

    if _is_coop_live_service_shooter_context(genres, context_text):
        if _has_any(
            "탐험과 세계 해석",
            "세계관과 맥락을 스스로 읽어가는",
            "패턴을 익히며 반복 도전",
            "플레이 흐름이 점점 또렷해지는 재미",
            "서사와 분위기에 오래 몰입",
            "배경과 연출이 만드는 분위기",
        ):
            return fallback.strip() or "분대 호흡을 맞추며 임무를 푸는 플레이어"

    if _is_narrative_openworld_context(genres, context_text):
        if _has_any("매칭", "서버 상태", "팀플레이", "짧고 강한 교전 템포", "패턴을 익히며 반복 도전", "플레이 흐름이 점점 또렷해지는 재미", "핵심 플레이를 반복하며", "핵심 플레이 감각"):
            return fallback.strip() or value

    if _is_soulslike_context(genres, context_text):
        if _has_any("가격 대비 만족", "팀 플레이", "핵심 플레이", "플레이 흐름", "한 판이 금방 지나", "매칭", "서버"):
            return fallback.strip() or value

    if _is_life_sim_context(genres, context_text):
        if _has_any("핵심 플레이 감각", "핵심 플레이를 반복하며", "빌드", "탐험과 세계 해석", "패턴을 익히며 반복 도전", "짧고 강한 교전 템포", "전투 손맛"):
            return fallback.strip() or value

    if _is_city_builder_context(genres, context_text):
        if _has_any("전투", "교전", "보스", "패턴", "이동 흐름", "핵심 플레이를 반복하며", "핵심 플레이 감각"):
            return fallback.strip() or value

    if _is_automation_context(genres, context_text):
        if _has_any("매칭", "서버", "보스", "보스전", "교전 손맛", "핵심 플레이를 반복하며", "핵심 플레이 감각", "손에 익을수록"):
            return fallback.strip() or value

    if _is_deckbuilder_context(genres, context_text):
        if _has_any("오픈월드", "탐험", "교전 손맛", "서사와 분위기", "핵심 플레이 감각", "손에 익을수록"):
            return fallback.strip() or value

    if _is_turn_based_tactics_context(genres, context_text):
        if _has_any("오픈월드", "탐험", "실시간", "손맛", "서사와 분위기", "핵심 플레이 감각", "전투/이동 흐름") and "턴" not in lowered:
            return fallback.strip() or value

    return value


def _replace_forbidden_labels(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return ""
    replaced = normalized
    for before, after in FORBIDDEN_LABEL_REPLACEMENTS.items():
        replaced = replaced.replace(before, after)
    return replaced


def _apply_forbidden_label_replacements_to_display(
    report_display: dict[str, Any],
) -> dict[str, Any]:
    next_display = dict(report_display)

    strengths: list[dict[str, Any]] = []
    for item in list(next_display.get("top_strengths", []) or []):
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        if isinstance(next_item.get("title"), str):
            next_item["title"] = _replace_forbidden_labels(str(next_item.get("title", "")))
        strengths.append(next_item)
    next_display["top_strengths"] = strengths

    risks: list[dict[str, Any]] = []
    for item in list(next_display.get("top_risks", []) or []):
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        if isinstance(next_item.get("title"), str):
            next_item["title"] = _replace_forbidden_labels(str(next_item.get("title", "")))
        risks.append(next_item)
    next_display["top_risks"] = risks

    return next_display


def _apply_forbidden_label_replacements_to_sections(
    evidence_sections: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    def _replace_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        replaced_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            next_block = dict(block)
            if isinstance(next_block.get("title"), str):
                next_block["title"] = _replace_forbidden_labels(str(next_block.get("title", "")))
            if isinstance(next_block.get("theme"), str):
                next_block["theme"] = _replace_forbidden_labels(str(next_block.get("theme", "")))
            replaced_blocks.append(next_block)
        return replaced_blocks

    return {
        "strengths": _replace_blocks(list(evidence_sections.get("strengths", []) or [])),
        "risks": _replace_blocks(list(evidence_sections.get("risks", []) or [])),
    }


def _build_evidence_sections_from_blocks(blocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    strengths: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    strength_index = 1
    risk_index = 1

    for block in blocks:
        if not isinstance(block, dict):
            continue
        stance = str(block.get("stance", ""))
        snippets = [str(item) for item in list(block.get("evidence_snippets", []) or []) if str(item)]
        candidate_snippets = [
            str(item)
            for item in list(block.get("evidence_candidate_snippets", []) or [])
            if str(item)
        ]
        if len(snippets) < 2:
            continue
        if stance == "positive":
            strengths.append(
                {
                    "block_id": f"str_{strength_index}",
                    "title": str(block.get("title", "")),
                    "theme": str(block.get("theme", "")),
                    "why_it_matters": str(block.get("why_it_matters") or block.get("explanation", "")),
                    "explanation": str(block.get("explanation", "")),
                    "aspect_keys": list(block.get("aspect_keys", []) or []),
                    "stance": "positive",
                    "consensus_level": str(block.get("consensus_level", "high")),
                    "mention_count": int(block.get("mention_count", 0)),
                    "evidence_quality_level": str(block.get("evidence_quality_level", "strict")),
                    "evidence_candidate_snippets": candidate_snippets[:8],
                    "evidence_snippets": snippets[:3],
                }
            )
            strength_index += 1
        elif stance == "negative":
            risks.append(
                {
                    "block_id": f"risk_{risk_index}",
                    "title": str(block.get("title", "")),
                    "theme": str(block.get("theme", "")),
                    "why_it_matters": str(block.get("why_it_matters") or block.get("explanation", "")),
                    "explanation": str(block.get("explanation", "")),
                    "aspect_keys": list(block.get("aspect_keys", []) or []),
                    "stance": "negative",
                    "consensus_level": str(block.get("consensus_level", "high")),
                    "mention_count": int(block.get("mention_count", 0)),
                    "evidence_quality_level": str(block.get("evidence_quality_level", "strict")),
                    "evidence_candidate_snippets": candidate_snippets[:8],
                    "evidence_snippets": snippets[:3],
                }
            )
            risk_index += 1

    return {
        "strengths": strengths[:3],
        "risks": risks[:3],
    }


def _truncate_evidence_sections_by_plan(
    evidence_sections: dict[str, list[dict[str, Any]]],
    report_plan: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    blueprint = report_plan.get("section_blueprint", {}) if isinstance(report_plan, dict) else {}
    strength_count = int(blueprint.get("strength_block_count", 3))
    risk_count = int(blueprint.get("risk_block_count", 3))
    evidence_per_block = int(blueprint.get("evidence_per_block", 3))
    if evidence_per_block < 2:
        evidence_per_block = 2
    if evidence_per_block > 3:
        evidence_per_block = 3

    clipped_strengths = []
    for block in list(evidence_sections.get("strengths", []) or [])[: max(strength_count, 0)]:
        next_block = dict(block)
        next_block["evidence_snippets"] = list(block.get("evidence_snippets", []) or [])[: max(
            evidence_per_block, 0
        )]
        clipped_strengths.append(next_block)

    clipped_risks = []
    for block in list(evidence_sections.get("risks", []) or [])[: max(risk_count, 0)]:
        next_block = dict(block)
        next_block["evidence_snippets"] = list(block.get("evidence_snippets", []) or [])[: max(
            evidence_per_block, 0
        )]
        clipped_risks.append(next_block)

    return {
        "strengths": clipped_strengths,
        "risks": clipped_risks,
    }


def _attach_legacy_flat_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep backward-compatible top-level fields for existing UI routes."""
    report_display = payload.get("report_display", {}) if isinstance(payload, dict) else {}
    evidence_sections = payload.get("evidence_sections", {}) if isinstance(payload, dict) else {}

    evidence_reviews: list[dict[str, Any]] = []
    for block in list(evidence_sections.get("strengths", []) or []):
        merged = dict(block)
        merged["stance"] = "positive"
        evidence_reviews.append(merged)
    for block in list(evidence_sections.get("risks", []) or []):
        merged = dict(block)
        merged["stance"] = "negative"
        evidence_reviews.append(merged)

    merged_payload = dict(payload)
    merged_payload.update(
        {
            "headline": report_display.get("headline"),
            "buy_recommendation": report_display.get("buy_recommendation"),
            "buy_timing_summary": report_display.get("buy_timing_summary"),
            "good_for": report_display.get("good_for"),
            "not_good_for": report_display.get("not_good_for"),
            "top_strengths": report_display.get("top_strengths"),
            "top_risks": report_display.get("top_risks"),
            "recent_state": report_display.get("recent_state"),
            "evidence_reviews": evidence_reviews,
        }
    )
    return merged_payload


def _build_consensus_payload(
    *,
    appid: int,
    metadata: dict[str, Any],
    analysis: dict[str, Any],
    processed_reviews: list[dict[str, Any]],
    report_materials: list[dict[str, Any]],
    included_count: int,
) -> dict[str, Any]:
    issue_signals = analysis.get("issue_signals", {}) or {}
    high_min = max(12, int(round(included_count * 0.06)))
    medium_min = max(6, int(round(included_count * 0.03)))
    refined_material_map = _build_refined_material_map(report_materials)

    consensus_aspects: list[dict[str, Any]] = []
    for aspect, signal in issue_signals.items():
        mention_count = int(signal.get("mention_count", 0))
        if mention_count < medium_min:
            continue

        consensus_level = "high" if mention_count >= high_min else "medium"
        negative_ratio = round(float(signal.get("negative_ratio", 0.0)), 4)
        themes = list(signal.get("themes", []) or [])
        evidence_group = _collect_grouped_evidence(
            processed_reviews=processed_reviews,
            aspect=aspect,
            refined_material_map=refined_material_map,
            fallback_snippets=list(signal.get("sample_reviews", []) or []),
        )

        consensus_aspects.append(
            {
                "aspect": aspect,
                "aspect_label": CATEGORY_DISPLAY.get(aspect, aspect),
                "mention_count": mention_count,
                "consensus_level": consensus_level,
                "negative_ratio": negative_ratio,
                "recent_trend": str(signal.get("recent_trend", "flat")),
                "themes": themes,
                "tone": _infer_aspect_tone(negative_ratio, themes),
                "evidence_group": evidence_group,
            }
        )

    consensus_aspects.sort(
        key=lambda item: (-_consensus_rank(item["consensus_level"]), -int(item["mention_count"]))
    )
    return {
        "game_context": {
            "appid": appid,
            **build_game_context_payload(appid, metadata),
            "analysis_window": "latest_snapshot",
            "included_review_count": included_count,
        },
        "consensus_thresholds": {
            "high_min_mentions": high_min,
            "medium_min_mentions": medium_min,
        },
        "report_materials": list(report_materials or [])[:50],
        "consensus_aspects": consensus_aspects,
    }


def _consensus_rank(level: str) -> int:
    if level == "high":
        return 2
    if level == "medium":
        return 1
    return 0


def _infer_aspect_tone(negative_ratio: float, themes: list[str]) -> str:
    # 데이터가 명확한 구간은 즉시 확정 (테마 라벨보다 실제 추천율 우선)
    if negative_ratio <= 0.10:
        return "positive"
    if negative_ratio >= 0.55:
        return "negative"

    # 애매한 구간(10~55%)에서만 테마 힌트로 보조 판정
    score = 0
    for theme in themes:
        text = str(theme)
        if any(token in text for token in NEGATIVE_THEME_HINTS):
            score -= 1
        if any(token in text for token in POSITIVE_THEME_HINTS):
            score += 1

    if score <= -1:
        return "negative"
    if score >= 1:
        return "positive"
    if negative_ratio >= 0.40:
        return "negative"
    if negative_ratio <= 0.25:
        return "positive"
    return "mixed"


def _collect_grouped_evidence(
    *,
    processed_reviews: list[dict[str, Any]],
    aspect: str,
    refined_material_map: dict[str, dict[str, Any]],
    fallback_snippets: list[str],
) -> dict[str, list[dict[str, Any]]]:
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    seen: set[str] = set()

    for review in processed_reviews:
        if not review.get("included_in_analysis"):
            continue
        tags = list(review.get("category_tags", []) or [])
        if aspect not in tags:
            continue

        review_id = str(review.get("review_id", ""))
        material = refined_material_map.get(review_id, {})
        snippet_source = str(material.get("evidence_text", ""))
        if not snippet_source:
            snippet_source = str(review.get("review_text", ""))
        snippet = _prepare_evidence_source_text(clean_markup_text(snippet_source), limit=1200)
        if not snippet or snippet in seen:
            continue
        if _is_noisy_evidence_text(snippet):
            continue
        seen.add(snippet)

        item = {"review_id": review_id, "snippet": snippet}
        material_stance = str(material.get("stance", "")).strip().lower()
        if material_stance in {"positive", "negative"}:
            stance = material_stance
        else:
            stance = _classify_snippet_stance(snippet, voted_up=bool(review.get("voted_up", False)))
        if stance == "positive":
            positive.append(item)
        elif stance == "negative":
            negative.append(item)
        else:
            continue

        if len(positive) >= 4 and len(negative) >= 4:
            break

    if not positive and not negative:
        for index, snippet in enumerate(fallback_snippets[:3]):
            normalized = _prepare_evidence_source_text(clean_markup_text(str(snippet)), limit=1200)
            if normalized and not _is_noisy_evidence_text(normalized):
                negative.append(
                    {
                        "review_id": f"fallback-{aspect}-{index + 1}",
                        "snippet": normalized,
                    }
                )

    return {"positive": positive[:4], "negative": negative[:4]}


def _build_refined_material_map(report_materials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    use_rewrite = _should_use_llm_material_rewrite()
    for material in list(report_materials or []):
        if not isinstance(material, dict):
            continue
        review_id = str(material.get("review_id", "")).strip()
        source_text = str(material.get("source_text", "")).strip()
        refined_text = str(material.get("refined_text", "")).strip()
        evidence_text = refined_text if use_rewrite and refined_text else source_text
        if not review_id or not evidence_text:
            continue
        result[review_id] = {
            "evidence_text": evidence_text,
            "stance": str(material.get("stance", "")).strip().lower(),
        }
    return result


def _build_report_deterministic(consensus_payload: dict[str, Any]) -> dict[str, Any]:
    aspects = list(consensus_payload.get("consensus_aspects", []) or [])
    game_context = consensus_payload.get("game_context", {}) or {}
    genres = list(game_context.get("genres", []) or [])
    context_text = _context_text(game_context)
    high = [item for item in aspects if item.get("consensus_level") == "high"]
    medium = [item for item in aspects if item.get("consensus_level") == "medium"]

    selected_strengths = _select_strengths(high, medium)
    selected_risks = _select_risks(high, medium)
    recent_state = _derive_recent_state(selected_risks, high, medium)
    paid_recommendation = _derive_recommendation(selected_risks, recent_state["status"])
    recommendation = _to_price_aware_recommendation(
        paid_recommendation,
        is_free_game=_is_free_game(consensus_payload),
    )
    headline = _build_headline(
        recommendation,
        selected_strengths,
        selected_risks,
        genres=genres,
        context_text=context_text,
    )
    if recommendation == "buy_on_sale":
        strength_theme = (
            _experience_theme(selected_strengths[0], positive=True, genres=genres, context_text=context_text)
            if selected_strengths
            else "핵심 플레이 경험"
        )
        risk_theme = (
            _experience_theme(selected_risks[0], positive=False, genres=genres, context_text=context_text)
            if selected_risks
            else "기술 안정성 이슈"
        )
        headline = (
            f"{strength_theme} 경험은 분명한 강점입니다. "
            f"다만 {risk_theme} 때문에 할인 시점에 시작하는 편이 더 안전합니다."
        )
    buy_timing_summary = _build_timing_summary(
        recommendation,
        recent_state,
        selected_risks,
        genres=genres,
        context_text=context_text,
    )
    evidence_blocks = _build_evidence_blocks(consensus_payload)

    good_for = _build_good_for(selected_strengths, genres=genres, context_text=context_text)
    not_good_for = _build_not_good_for(selected_risks, genres=genres, context_text=context_text)
    good_fit_signals = [
        _build_player_fit_signal(item, genres=genres, negative=False)
        for item in selected_strengths[:4]
    ]
    not_good_fit_signals = [
        _build_player_fit_signal(item, genres=genres, negative=True)
        for item in selected_risks[:4]
    ]
    if not good_fit_signals:
        fallback_good_signal = _build_player_fit_signal(
            _default_positive_fit_source(genres, context_text=context_text),
            genres=genres,
            negative=False,
        )
        if fallback_good_signal:
            good_fit_signals.append(fallback_good_signal)
    if not not_good_fit_signals:
        fallback_not_good_signal = _build_player_fit_signal(
            _default_negative_fit_source(genres, context_text=context_text),
            genres=genres,
            negative=True,
        )
        if fallback_not_good_signal:
            not_good_fit_signals.append(fallback_not_good_signal)
    player_fit_signals = {
        "good_for": good_fit_signals,
        "not_good_for": not_good_fit_signals,
    }

    return {
        "headline": headline,
        "buy_recommendation": recommendation,
        "buy_timing_summary": buy_timing_summary,
        "good_for": good_for[:4],
        "not_good_for": not_good_for[:4],
        "player_fit_signals": player_fit_signals,
        "top_strengths": [_to_strength_item(item, genres=genres, context_text=context_text) for item in selected_strengths[:3]],
        "top_risks": [_to_risk_item(item, genres=genres, context_text=context_text) for item in selected_risks[:3]],
        "recent_state": recent_state,
        "evidence_reviews": evidence_blocks,
    }


def _select_strengths(high: list[dict[str, Any]], medium: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pool = high + medium
    candidates = [
        item
        for item in pool
        if item.get("tone") != "negative"
        and float(item.get("negative_ratio", 0.0)) <= 0.56
    ]
    ranked = sorted(
        candidates,
        key=lambda item: (
            -_consensus_rank(item.get("consensus_level", "low")),
            0 if item.get("tone") == "positive" else 1,
            float(item.get("negative_ratio", 0.0)),
            -int(item.get("mention_count", 0)),
        ),
    )
    return ranked[:3]


def _select_risks(high: list[dict[str, Any]], medium: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pool = high + medium
    candidates = [
        item
        for item in pool
        if item.get("tone") == "negative" or float(item.get("negative_ratio", 0.0)) >= 0.50
    ]
    # 후보가 없으면 negative_ratio가 가장 높은 항목을 차선 리스크로 선정
    if not candidates and pool:
        fallback = [
            item for item in pool
            if float(item.get("negative_ratio", 0.0)) > 0.0
        ]
        fallback.sort(key=lambda item: -float(item.get("negative_ratio", 0.0)))
        candidates = fallback[:2]
    ranked = sorted(
        candidates,
        key=lambda item: (
            -_consensus_rank(item.get("consensus_level", "low")),
            0 if item.get("tone") == "negative" else 1,
            -float(item.get("negative_ratio", 0.0)),
            -int(item.get("mention_count", 0)),
        ),
    )
    return ranked[:3]


def _derive_recent_state(
    selected_risks: list[dict[str, Any]],
    high: list[dict[str, Any]],
    medium: list[dict[str, Any]],
) -> dict[str, str]:
    if not high and not medium:
        return {"status": "insufficient_data", "summary": "최근 후기만으로는 분위기 변화를 단정하기 어렵습니다."}

    up = sum(1 for item in selected_risks if item.get("recent_trend") == "up")
    down = sum(1 for item in selected_risks if item.get("recent_trend") == "down")

    if selected_risks and up >= down + 1:
        return {"status": "declining", "summary": "최근에는 불편을 말하는 후기가 늘어 분위기가 다소 내려가는 편입니다."}
    if selected_risks and down >= up + 1:
        return {"status": "improving", "summary": "불편이 줄었다는 후기가 늘어 전반적인 분위기가 나아지는 편입니다."}
    if selected_risks:
        return {"status": "mixed", "summary": "좋았다는 반응과 아쉽다는 반응이 함께 보여 평가가 갈리는 편입니다."}
    return {"status": "stable", "summary": "최근 후기 분위기는 큰 흔들림 없이 비슷한 편입니다."}


def _derive_recommendation(selected_risks: list[dict[str, Any]], recent_status: str) -> str:
    severe = sum(1 for item in selected_risks if float(item.get("negative_ratio", 0.0)) >= 0.65)
    medium = sum(1 for item in selected_risks if float(item.get("negative_ratio", 0.0)) >= 0.52)

    if severe >= 2:
        return "not_recommended"
    if recent_status == "declining" and (severe >= 1 or medium >= 2):
        return "wait"
    if severe == 0 and medium <= 1 and recent_status in {"stable", "improving"}:
        return "buy_now"
    return "buy_on_sale"


def _build_headline(
    recommendation: str,
    strengths: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    *,
    genres: list[str],
    context_text: str = "",
) -> str:
    strength_theme = (
        _experience_theme(strengths[0], positive=True, genres=genres, context_text=context_text)
        if strengths
        else _fallback_positive_headline_theme(genres, context_text)
    )
    risk_theme = (
        _experience_theme(risks[0], positive=False, genres=genres, context_text=context_text)
        if risks
        else _fallback_negative_headline_theme(genres, context_text)
    )

    if recommendation in {"free_play_recommended", "play_now"}:
        return f"{strength_theme} 체감이 좋아 무료로 지금 시작해보기 좋은 상태입니다."
    if recommendation == "try_lightly":
        return f"{strength_theme} 장점이 보여 무료로 가볍게 시작해보고 맞는지 판단하기 좋습니다."
    if recommendation == "buy_now":
        return f"{strength_theme} 체감이 좋아 지금 바로 시작해도 만족도가 높은 편입니다."
    if recommendation == "buy_on_sale":
        return f"{strength_theme} 장점은 분명하지만 {risk_theme}이 거슬릴 수 있어 할인 시점이 더 안전합니다."
    if recommendation == "wait":
        return f"{strength_theme}은 매력적이지만 {risk_theme} 불편이 남아 있어 업데이트를 본 뒤 결정하는 편이 좋습니다."
    return f"{risk_theme} 불편이 플레이 경험을 크게 흔들 수 있어 현재 시점 구매는 보수적으로 보는 편이 좋습니다."


def _build_timing_summary(
    recommendation: str,
    recent_state: dict[str, str],
    risks: list[dict[str, Any]],
    *,
    genres: list[str],
    context_text: str = "",
) -> str:
    risk_theme = (
        _experience_theme(risks[0], positive=False, genres=genres, context_text=context_text)
        if risks
        else _fallback_negative_headline_theme(genres, context_text)
    )
    status = recent_state.get("status", "mixed")

    if recommendation in {"free_play_recommended", "play_now"}:
        return "무료 게임 기준으로 보면 지금 바로 플레이를 시작해도 체감 부담이 낮은 편입니다."
    if recommendation == "try_lightly":
        return "무료이므로 큰 진입 비용 없이 먼저 짧게 플레이해 취향 적합성을 확인하기 좋습니다."
    if recommendation == "buy_now":
        return "최근 후기 흐름에서 체감 불편이 크게 늘지 않아 지금 시작해도 부담이 낮은 편입니다."
    if recommendation == "buy_on_sale":
        return f"{risk_theme} 불편을 감수해야 할 수 있어 가격 메리트가 있는 시점이 더 낫습니다."
    if recommendation == "wait":
        if status == "declining":
            return f"{risk_theme} 관련 불편을 호소하는 후기가 늘어 업데이트 방향을 확인한 뒤 결정하는 편이 안전합니다."
        return f"{risk_theme} 불편이 여전히 자주 보이는 편이라 한두 번 더 패치 흐름을 보고 사는 것이 좋습니다."
    return f"{risk_theme} 문제가 플레이 몰입을 크게 깰 수 있어, 당장은 관망이 더 안전합니다."


def _build_good_for(
    selected_strengths: list[dict[str, Any]],
    *,
    genres: list[str],
    context_text: str = "",
) -> list[str]:
    result: list[str] = []
    for item in selected_strengths:
        theme = _select_positive_theme_for_context(item, genres=genres, context_text=context_text)
        phrase = build_player_fit_phrase(
            aspect=str(item.get("aspect", "")),
            theme=theme,
            genres=genres,
            negative=False,
        )
        if phrase and phrase not in result:
            result.append(phrase)
    if not result:
        fallback_source = _default_positive_fit_source(genres, context_text=context_text)
        fallback_theme = _choose_positive_theme(list(fallback_source.get("themes", []) or []))
        result.append(
            build_player_fit_phrase(
                aspect=str(fallback_source.get("aspect", "")),
                theme=fallback_theme,
                genres=genres,
                negative=False,
            )
        )
    return _contextualize_player_fit_result(
        result,
        genres=genres,
        context_text=context_text,
        negative=False,
    )


def _build_not_good_for(
    selected_risks: list[dict[str, Any]],
    *,
    genres: list[str],
    context_text: str = "",
) -> list[str]:
    result: list[str] = []
    for item in selected_risks:
        theme = _select_negative_theme_for_context(item, genres=genres, context_text=context_text)
        phrase = build_player_fit_phrase(
            aspect=str(item.get("aspect", "")),
            theme=theme,
            genres=genres,
            negative=True,
        )
        if phrase and phrase not in result:
            result.append(phrase)
    if not result:
        fallback_source = _default_negative_fit_source(genres, context_text=context_text)
        fallback_theme = _choose_negative_theme(list(fallback_source.get("themes", []) or []))
        result.append(
            build_player_fit_phrase(
                aspect=str(fallback_source.get("aspect", "")),
                theme=fallback_theme,
                genres=genres,
                negative=True,
            )
        )
    return _contextualize_player_fit_result(
        result,
        genres=genres,
        context_text=context_text,
        negative=True,
    )


def _build_player_fit_signal(
    item: dict[str, Any],
    *,
    genres: list[str],
    negative: bool,
) -> dict[str, Any]:
    themes = list(item.get("themes", []) or [])
    theme = _choose_negative_theme(themes) if negative else _choose_positive_theme(themes)
    return build_fit_signal(
        aspect=str(item.get("aspect", "")),
        theme=theme,
        genres=genres,
        negative=negative,
    )


def _contextualize_player_fit_result(
    values: list[str],
    *,
    genres: list[str],
    context_text: str = "",
    negative: bool,
) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = _normalize_player_fit_phrase(value)
        if not normalized:
            continue
        if _is_looter_shooter_context(genres, context_text):
            if negative and any(token in normalized for token in ("탐험", "세계 해석", "패턴", "반복 도전", "서사와 분위기")):
                normalized = "반복 임무와 파밍 피로를 크게 느끼는 플레이어"
            elif (not negative) and any(
                token in normalized
                for token in ("탐험", "세계와 단서", "세계관과 맥락", "패턴", "반복 도전", "플레이 흐름", "배경과 연출")
            ):
                normalized = "장비와 빌드를 오래 다듬는 플레이어"
        if _is_coop_live_service_shooter_context(genres, context_text):
            if negative and any(token in normalized for token in ("탐험", "세계 해석", "패턴", "서사와 분위기")):
                normalized = "분대 합이 안 맞을 때 커지는 피로에 민감한 플레이어"
            elif (not negative) and any(
                token in normalized
                for token in ("탐험", "세계와 단서", "세계관과 맥락", "패턴", "플레이 흐름", "서사와 분위기", "배경과 연출")
            ):
                normalized = "분대 호흡을 맞추며 임무를 푸는 플레이어"
        if _is_narrative_openworld_context(genres, context_text):
            if negative and any(token in normalized for token in ("매칭", "서버", "팀플레이", "짧고 강한 교전")):
                normalized = "긴 호흡의 진행 템포에 쉽게 지치는 플레이어"
            elif (not negative) and any(
                token in normalized for token in ("맵을 돌아다니며", "탐험", "세계와 단서", "플레이 흐름", "핵심 플레이", "손에 익혀")
            ):
                normalized = "사건과 인물의 여운을 오래 가져가는 플레이어"
        if _is_life_sim_context(genres, context_text):
            if negative and any(token in normalized for token in ("전투", "빌드", "탐험", "핵심 플레이")):
                normalized = "반복적인 일상 루프에 쉽게 피로를 느끼는 플레이어"
            elif (not negative) and any(token in normalized for token in ("전투", "빌드", "탐험", "핵심 플레이", "패턴")):
                normalized = "생활 루프를 천천히 쌓아가는 플레이어"
        if _is_visual_novel_context(genres, context_text):
            if negative and any(token in normalized for token in ("매칭", "서버", "팀플레이", "교전", "핵심 플레이")):
                normalized = "텍스트와 번역 품질에 민감한 플레이어"
            elif (not negative) and any(
                token in normalized for token in ("핵심 플레이", "손에 익혀", "성장 루프", "탐험", "세계와 단서")
            ):
                normalized = "서사와 감정선에 깊게 몰입하는 플레이어"
        if _is_city_builder_context(genres, context_text):
            if (not negative) and any(token in normalized for token in ("핵심 플레이", "손에 익혀", "전술과 운영 판단")):
                normalized = "도시를 키우며 흐름을 다듬는 운영형 플레이어"
        if _is_automation_context(genres, context_text):
            if negative and any(token in normalized for token in ("매칭", "서버", "팀플레이", "핵심 플레이")):
                normalized = "복잡한 동선과 관리 피로에 민감한 플레이어"
            elif (not negative) and any(token in normalized for token in ("핵심 플레이", "손에 익혀", "서사", "분위기")):
                normalized = "자동화 라인을 다듬으며 효율을 올리는 플레이어"
        if _is_deckbuilder_context(genres, context_text):
            if negative and any(token in normalized for token in ("매칭", "서버", "팀플레이")):
                normalized = "반복 구간과 운 의존에 쉽게 피로를 느끼는 플레이어"
            elif (not negative) and any(token in normalized for token in ("서사", "분위기", "핵심 플레이", "손에 익혀")):
                normalized = "한 판마다 덱 조합과 경로 선택을 즐기는 플레이어"
        if _is_turn_based_tactics_context(genres, context_text):
            if (not negative) and any(token in normalized for token in ("탐험", "세계와 단서", "핵심 플레이", "손에 익혀", "서사", "분위기")):
                normalized = "한 턴의 판단 무게를 즐기는 전술형 플레이어"
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _choose_positive_theme(themes: list[str]) -> str | None:
    for theme in themes:
        text = str(theme)
        if any(token in text for token in NEGATIVE_THEME_HINTS):
            continue
        return text
    return themes[0] if themes else None


def _choose_negative_theme(themes: list[str]) -> str | None:
    for theme in themes:
        text = str(theme)
        if any(token in text for token in NEGATIVE_THEME_HINTS):
            return text
    return themes[0] if themes else None


def _normalized_genre_text(genres: list[str]) -> str:
    return " ".join(str(item or "").lower() for item in genres)


def _context_text(game_context: dict[str, Any] | None) -> str:
    context = dict(game_context or {})
    parts = [
        str(context.get("name", "") or ""),
        str(context.get("short_description", "") or ""),
        " ".join(str(item or "") for item in list(context.get("genres", []) or [])),
    ]
    return " ".join(part.strip().lower() for part in parts if part and str(part).strip())


def _genre_signal_blob(genres: list[str], context_text: str = "") -> str:
    blob = " ".join(part for part in (_normalized_genre_text(genres), str(context_text or "").lower()) if part)
    return " ".join(blob.split())


def _is_visual_novel_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "visual novel",
            "비주얼 노벨",
            "literature club",
            "write the way into their heart",
            "not suitable for children",
            "easily disturbed",
        )
    )


def _is_city_builder_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "city builder",
            "city-building",
            "도시 건설",
            "city simulation",
            "city building experience",
            "cities: skylines",
        )
    )


def _is_automation_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(token in blob for token in ("automation", "factory", "factorio", "공장", "자동화"))


def _is_looter_shooter_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "looter shooter",
            "loot shooter",
            "destiny 2",
            "데스티니 가디언즈",
            "action mmo",
            "온라인 액션",
            "warframe",
            "무기고",
            "워프레임",
        )
    )


def _is_coop_live_service_shooter_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "helldivers 2",
            "helldivers™ 2",
            "헬다이버",
            "co-op shooter",
            "cooperative shooter",
            "live service shooter",
            "3인칭 슈팅",
        )
    )


def _is_narrative_openworld_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "the witcher 3",
            "witcher 3",
            "red dead redemption 2",
            "story rich open world",
            "open world rpg",
        )
    )


def _is_soulslike_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "elden ring",
            "dark souls",
            "sekiro",
            "lies of p",
            "soulslike",
            "souls-like",
            "소울",
        )
    )


def _is_openworld_crime_sandbox_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "grand theft auto v",
            "gta v",
            "gta online",
            "crime sandbox",
            "open world crime",
            "rockstar games",
        )
    )


def _is_life_sim_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(
        token in blob
        for token in (
            "life sim",
            "social sim",
            "the sims",
            "sims 4",
            "inzoi",
            "daily life",
        )
    )


def _is_deckbuilder_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(token in blob for token in ("deckbuilding", "deck builder", "card", "deck", "카드", "덱"))


def _is_turn_based_tactics_context(genres: list[str], context_text: str = "") -> bool:
    blob = _genre_signal_blob(genres, context_text)
    return any(token in blob for token in ("turn-based", "turn based", "턴제", "xcom", "tactical combat"))


def _select_positive_theme_for_context(
    item: dict[str, Any],
    *,
    genres: list[str],
    context_text: str = "",
) -> str | None:
    aspect = str(item.get("aspect", ""))
    if _is_visual_novel_context(genres, context_text):
        if aspect in {
            "story",
            "gameplay",
            "content_depth",
            "graphics",
            "sound",
            "customization",
            "controls",
            "multiplayer",
            "matchmaking",
        }:
            return "감정선"
    if _is_city_builder_context(genres, context_text):
        if aspect in {"gameplay", "building_ux", "content_depth"}:
            return "도시 운영"
        if aspect in {"graphics", "performance"}:
            return "도시 풍경"
    if _is_looter_shooter_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "customization", "story"}:
            return "장비 성장"
        if aspect in {"multiplayer", "matchmaking"}:
            return "반복 임무"
    if _is_coop_live_service_shooter_context(genres, context_text):
        if aspect in {"gameplay", "multiplayer", "content_depth", "customization"}:
            return "분대 임무"
    if _is_narrative_openworld_context(genres, context_text):
        if aspect in {"story", "gameplay", "content_depth", "graphics", "sound"}:
            return "사건과 인물"
    if _is_life_sim_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "customization", "story", "building_ux"}:
            return "생활 루프"
    if _is_automation_context(genres, context_text):
        if aspect in {"gameplay", "building_ux", "content_depth", "story", "multiplayer", "matchmaking"}:
            return "자동화 라인"
    if _is_deckbuilder_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "customization", "story"}:
            return "덱 구성"
    if _is_turn_based_tactics_context(genres, context_text):
        if aspect in {"gameplay", "difficulty", "content_depth", "story"}:
            return "한 턴의 판단"
    return _choose_positive_theme(list(item.get("themes", []) or []))


def _select_negative_theme_for_context(
    item: dict[str, Any],
    *,
    genres: list[str],
    context_text: str = "",
) -> str | None:
    aspect = str(item.get("aspect", ""))
    if _is_visual_novel_context(genres, context_text):
        if aspect in {"localization", "story"}:
            return "텍스트 흐름"
        if aspect in {"performance", "bugs", "matchmaking", "multiplayer", "gameplay", "content_depth", "controls"}:
            return "몰입 끊김"
    if _is_city_builder_context(genres, context_text):
        if aspect in {"building_ux", "gameplay"}:
            return "배치 피로"
        if aspect == "performance":
            return "도시 규모가 커질수록 무거워지는 흐름"
    if _is_looter_shooter_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "story", "customization"}:
            return "반복 파밍 피로"
        if aspect in {"multiplayer", "matchmaking"}:
            return "연결과 매칭 변수"
        if aspect in {"bugs", "performance"}:
            return "활동 안정성 흔들림"
    if _is_coop_live_service_shooter_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "multiplayer", "matchmaking"}:
            return "분대 합이 안 맞을 때 커지는 피로"
        if aspect in {"bugs", "performance"}:
            return "진행 안정성을 해치는 오류와 끊김"
    if _is_narrative_openworld_context(genres, context_text):
        if aspect in {"story", "gameplay", "content_depth"}:
            return "진행 템포가 느리게 느껴지는 구간"
        if aspect in {"multiplayer", "matchmaking", "bugs", "performance"}:
            return "몰입을 끊는 기술 이슈"
    if _is_life_sim_context(genres, context_text):
        if aspect in {"gameplay", "content_depth", "story"}:
            return "일상 루프 반복 피로"
        if aspect in {"building_ux", "customization", "controls"}:
            return "꾸미기와 동선 피로"
        if aspect in {"bugs", "performance"}:
            return "로딩과 오류가 흐름을 끊는 구간"
    if _is_automation_context(genres, context_text):
        if aspect in {"building_ux", "gameplay", "controls", "story", "multiplayer", "matchmaking"}:
            return "복잡한 동선"
        if aspect == "performance":
            return "규모가 커질수록 무거워지는 공장 흐름"
    if _is_deckbuilder_context(genres, context_text):
        if aspect in {"content_depth", "balance", "gameplay", "story", "multiplayer", "matchmaking"}:
            return "운 의존"
    if _is_turn_based_tactics_context(genres, context_text):
        if aspect in {"difficulty", "gameplay", "controls", "story"}:
            return "한 턴 실수 부담"
    return _choose_negative_theme(list(item.get("themes", []) or []))


def _fallback_positive_headline_theme(genres: list[str], context_text: str = "") -> str:
    if _is_visual_novel_context(genres, context_text):
        return "서사 몰입"
    if _is_city_builder_context(genres, context_text):
        return "도시 운영"
    if _is_looter_shooter_context(genres, context_text):
        return "장비 파밍과 성장"
    if _is_coop_live_service_shooter_context(genres, context_text):
        return "분대 협동과 임무 수행"
    if _is_narrative_openworld_context(genres, context_text):
        return "사건과 인물의 여운"
    if _is_life_sim_context(genres, context_text):
        return "생활 루프와 꾸미기"
    if _is_automation_context(genres, context_text):
        return "자동화와 최적화"
    if _is_deckbuilder_context(genres, context_text):
        return "덱 구성의 재미"
    if _is_turn_based_tactics_context(genres, context_text):
        return "전술 판단의 재미"
    return "핵심 플레이 감각"


def _fallback_negative_headline_theme(genres: list[str], context_text: str = "") -> str:
    if _is_visual_novel_context(genres, context_text):
        return "텍스트 전달"
    if _is_city_builder_context(genres, context_text):
        return "도시 관리 부담"
    if _is_looter_shooter_context(genres, context_text):
        return "반복 파밍 피로"
    if _is_coop_live_service_shooter_context(genres, context_text):
        return "분대 합 피로"
    if _is_narrative_openworld_context(genres, context_text):
        return "긴 진행 템포"
    if _is_life_sim_context(genres, context_text):
        return "일상 루프 반복 피로"
    if _is_automation_context(genres, context_text):
        return "공장 관리 부담"
    if _is_deckbuilder_context(genres, context_text):
        return "운 의존성"
    if _is_turn_based_tactics_context(genres, context_text):
        return "턴 단위 실수 부담"
    return "기술 안정성"


def _default_positive_fit_source(genres: list[str], *, context_text: str = "") -> dict[str, Any]:
    genre_text = _genre_signal_blob(genres, context_text)
    if _is_visual_novel_context(genres, context_text):
        return {"aspect": "story", "themes": ["감정선", "서사 몰입"]}
    if _is_city_builder_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["도시 운영", "교통 흐름"]}
    if _is_looter_shooter_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["장비 성장", "반복 임무"]}
    if _is_coop_live_service_shooter_context(genres, context_text):
        return {"aspect": "multiplayer", "themes": ["분대 임무", "역할 분담"]}
    if _is_narrative_openworld_context(genres, context_text):
        return {"aspect": "story", "themes": ["사건과 인물", "서사 여운"]}
    if _is_life_sim_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["생활 루프", "꾸미기와 관계"]}
    if _is_automation_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["자동화 라인", "병목 해소"]}
    if _is_deckbuilder_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["덱 구성", "카드 선택"]}
    if _is_turn_based_tactics_context(genres, context_text):
        return {"aspect": "gameplay", "themes": ["한 턴의 판단", "병력 손실 압박"]}
    if any(token in genre_text for token in ("management", "sports", "sport", "strategy", "전략", "경영")):
        return {"aspect": "content_depth", "themes": []}
    if any(token in genre_text for token in ("farming", "cozy", "life sim", "농장", "힐링", "생활")):
        return {"aspect": "gameplay", "themes": ["하루 루틴", "농장 성장"]}
    if any(token in genre_text for token in ("survival", "생존", "raid", "loot", "craft", "crafting")):
        return {"aspect": "gameplay", "themes": ["파밍과 생존", "거점 운영"]}
    if any(token in genre_text for token in ("co-op", "coop", "cooperative", "협동", "파티", "team")):
        return {"aspect": "multiplayer", "themes": ["협동 임무", "팀 호흡"]}
    return {"aspect": "gameplay", "themes": []}


def _default_negative_fit_source(genres: list[str], *, context_text: str = "") -> dict[str, Any]:
    genre_text = _genre_signal_blob(genres, context_text)
    if _is_visual_novel_context(genres, context_text):
        return {"aspect": "localization", "themes": ["텍스트 흐름", "감정선 전달"]}
    if _is_city_builder_context(genres, context_text):
        return {"aspect": "building_ux", "themes": ["배치 피로", "도시 관리 부담"]}
    if _is_looter_shooter_context(genres, context_text):
        return {"aspect": "content_depth", "themes": ["반복 파밍 피로", "연결과 매칭 변수"]}
    if _is_coop_live_service_shooter_context(genres, context_text):
        return {"aspect": "multiplayer", "themes": ["분대 합 피로", "임무 반복 피로"]}
    if _is_narrative_openworld_context(genres, context_text):
        return {"aspect": "story", "themes": ["긴 진행 템포", "몰입을 끊는 기술 이슈"]}
    if _is_life_sim_context(genres, context_text):
        return {"aspect": "content_depth", "themes": ["일상 루프 반복 피로", "꾸미기와 동선 피로"]}
    if _is_automation_context(genres, context_text):
        return {"aspect": "building_ux", "themes": ["복잡한 동선", "병목 관리"]}
    if _is_deckbuilder_context(genres, context_text):
        return {"aspect": "content_depth", "themes": ["반복 전개", "운 의존"]}
    if _is_turn_based_tactics_context(genres, context_text):
        return {"aspect": "difficulty", "themes": ["한 턴 실수 부담", "초반 적응"]}
    if any(
        token in genre_text
        for token in ("multiplayer", "대규모 멀티플레이어", "battle royale", "battlegrounds", "shooter", "fps", "tps")
    ):
        return {"aspect": "multiplayer", "themes": []}
    return {"aspect": "performance", "themes": []}


def _to_strength_item(item: dict[str, Any], *, genres: list[str], context_text: str = "") -> dict[str, str]:
    aspect = _display_aspect_for_context(str(item.get("aspect", "")), genres=genres, context_text=context_text)
    label = CATEGORY_DISPLAY.get(aspect, aspect)
    selected_theme = _select_positive_theme_for_context(item, genres=genres, context_text=context_text)
    if selected_theme:
        return {
            "title": build_display_theme(
                aspect=aspect,
                theme=selected_theme,
                genres=genres,
                negative=False,
            ),
            "summary": _strength_experience_summary(
                aspect=aspect,
                theme=selected_theme,
                genres=genres,
            ),
        }
    return {
        "title": build_display_theme(
            aspect=aspect,
            theme=label,
            genres=genres,
            negative=False,
        ),
        "summary": _strength_experience_summary(
            aspect=aspect,
            theme=label,
            genres=genres,
        ),
    }


def _to_risk_item(item: dict[str, Any], *, genres: list[str], context_text: str = "") -> dict[str, str]:
    aspect = _display_aspect_for_context(str(item.get("aspect", "")), genres=genres, context_text=context_text)
    label = CATEGORY_DISPLAY.get(aspect, aspect)
    selected_theme = _select_negative_theme_for_context(item, genres=genres, context_text=context_text)
    if selected_theme:
        return {
            "title": build_display_theme(
                aspect=aspect,
                theme=selected_theme,
                genres=genres,
                negative=True,
            ),
            "summary": _risk_experience_summary(
                aspect=aspect,
                theme=selected_theme,
                genres=genres,
            ),
        }
    return {
        "title": build_display_theme(
            aspect=aspect,
            theme=label,
            genres=genres,
            negative=True,
        ),
        "summary": _risk_experience_summary(
            aspect=aspect,
            theme=label,
            genres=genres,
        ),
    }


def _experience_theme(item: dict[str, Any], *, positive: bool, genres: list[str], context_text: str = "") -> str:
    selected = (
        _select_positive_theme_for_context(item, genres=genres, context_text=context_text)
        if positive
        else _select_negative_theme_for_context(item, genres=genres, context_text=context_text)
    )
    fallback = CATEGORY_DISPLAY.get(str(item.get("aspect", "")), "핵심 경험")
    return build_headline_theme(
        aspect=_display_aspect_for_context(str(item.get("aspect", "")), genres=genres, context_text=context_text),
        theme=selected or fallback,
        genres=genres,
        negative=not positive,
    )


def _display_aspect_for_context(aspect: str, *, genres: list[str], context_text: str = "") -> str:
    if _is_visual_novel_context(genres, context_text) and aspect in {
        "gameplay",
        "content_depth",
        "graphics",
        "sound",
        "customization",
        "controls",
        "multiplayer",
        "matchmaking",
    }:
        return "story"
    if _is_narrative_openworld_context(genres, context_text) and aspect in {"gameplay", "graphics", "sound"}:
        return "story"
    if _is_life_sim_context(genres, context_text) and aspect in {"gameplay", "story", "customization", "building_ux"}:
        return "content_depth"
    if _is_city_builder_context(genres, context_text) and aspect == "gameplay":
        return "building_ux"
    if _is_looter_shooter_context(genres, context_text) and aspect in {"story", "customization"}:
        return "content_depth"
    if _is_coop_live_service_shooter_context(genres, context_text) and aspect in {"gameplay", "story"}:
        return "multiplayer"
    if _is_automation_context(genres, context_text) and aspect in {"gameplay", "story", "multiplayer", "matchmaking"}:
        return "building_ux"
    if _is_deckbuilder_context(genres, context_text) and aspect in {"gameplay", "story", "customization"}:
        return "content_depth"
    if _is_turn_based_tactics_context(genres, context_text) and aspect in {"gameplay", "story"}:
        return "difficulty"
    return aspect


def _strength_experience_summary(*, aspect: str, theme: str, genres: list[str]) -> str:
    return build_experience_summary(
        aspect=aspect,
        theme=theme,
        genres=genres,
        negative=False,
    )


def _risk_experience_summary(*, aspect: str, theme: str, genres: list[str]) -> str:
    return build_experience_summary(
        aspect=aspect,
        theme=theme,
        genres=genres,
        negative=True,
    )


def _build_evidence_blocks(consensus_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build insight+evidence blocks from high-consensus repeated opinions."""
    aspects = list(consensus_payload.get("consensus_aspects", []) or [])
    game_context = consensus_payload.get("game_context", {}) or {}
    genres = list(game_context.get("genres", []) or [])
    high_min = int(
        (consensus_payload.get("consensus_thresholds", {}) or {}).get("high_min_mentions", 12)
    )
    high_items = [item for item in aspects if item.get("consensus_level") == "high"]
    if not high_items:
        return []

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in high_items:
        stance = _block_stance(item)
        if stance not in {"positive", "negative"}:
            continue

        theme = _pick_block_theme(item, stance) or str(item.get("aspect_label", "핵심 의견"))
        key = (stance, theme)
        bucket = grouped.setdefault(
            key,
            {
                "stance": stance,
                "theme": theme,
                "mention_count": 0,
                "aspects": [],
                "aspect_labels": [],
                "snippets": [],
            },
        )

        bucket["mention_count"] += int(item.get("mention_count", 0))
        aspect = str(item.get("aspect", ""))
        if aspect and aspect not in bucket["aspects"]:
            bucket["aspects"].append(aspect)
        aspect_label = str(item.get("aspect_label", ""))
        if aspect_label and aspect_label not in bucket["aspect_labels"]:
            bucket["aspect_labels"].append(aspect_label)

        evidence_group = item.get("evidence_group", {}) or {}
        stance_snippets = list(evidence_group.get(stance, []) or [])
        match_tokens = _build_theme_match_tokens(bucket["theme"], bucket["aspects"])
        for snippet in stance_snippets:
            text = _prepare_evidence_source_text(str(snippet.get("snippet", "")), limit=1200)
            if not text or text in bucket["snippets"]:
                continue
            if not _snippet_matches_stance(text, stance):
                continue
            if match_tokens and not _snippet_matches_theme(text, match_tokens):
                continue
            bucket["snippets"].append(text)
            if len(bucket["snippets"]) >= 4:
                break

    blocks: list[dict[str, Any]] = []
    for bucket in sorted(grouped.values(), key=lambda b: (-int(b["mention_count"]), b["theme"])):
        if int(bucket["mention_count"]) < high_min:
            continue
        if len(bucket["snippets"]) < 2:
            continue

        title = _build_block_title(
            bucket["theme"],
            bucket["stance"],
            aspect_keys=list(bucket["aspects"]),
            genres=genres,
        )
        why_it_matters = _build_block_why_it_matters(
            stance=bucket["stance"],
            theme=bucket["theme"],
            aspect_labels=bucket["aspect_labels"],
            aspect_keys=list(bucket["aspects"]),
            genres=genres,
        )
        blocks.append(
            {
                "title": title,
                "theme": bucket["theme"],
                "why_it_matters": why_it_matters,
                "explanation": why_it_matters,
                "aspect_keys": list(bucket["aspects"]),
                "stance": bucket["stance"],
                "consensus_level": "high",
                "mention_count": int(bucket["mention_count"]),
                "evidence_snippets": bucket["snippets"][:3],
            }
        )
        if len(blocks) >= 4:
            break

    # negative 블록이 없으면 전체 aspects에서 negative_ratio 상위 항목으로 폴백
    has_negative = any(b["stance"] == "negative" for b in blocks)
    if not has_negative:
        fallback_candidates = sorted(
            [item for item in aspects if float(item.get("negative_ratio", 0.0)) > 0.0],
            key=lambda item: -float(item.get("negative_ratio", 0.0)),
        )
        for item in fallback_candidates[:2]:
            theme = _pick_block_theme(item, "negative") or str(item.get("aspect_label", "핵심 의견"))
            evidence_group = item.get("evidence_group", {}) or {}
            neg_snippets = list(evidence_group.get("negative", []) or [])
            match_tokens = _build_theme_match_tokens(theme, [str(item.get("aspect", ""))])
            snippets: list[str] = []
            for snippet in neg_snippets:
                text = _prepare_evidence_source_text(str(snippet.get("snippet", "")), limit=1200)
                if not text or text in snippets:
                    continue
                if match_tokens and not _snippet_matches_theme(text, match_tokens):
                    continue
                snippets.append(text)
                if len(snippets) >= 3:
                    break
            if len(snippets) < 2:
                continue
            blocks.append(
                {
                    "title": _build_block_title(
                        theme,
                        "negative",
                        aspect_keys=[str(item.get("aspect", ""))],
                        genres=genres,
                    ),
                    "theme": theme,
                    "why_it_matters": _build_block_why_it_matters(
                        stance="negative", theme=theme,
                        aspect_labels=[str(item.get("aspect_label", ""))],
                        aspect_keys=[str(item.get("aspect", ""))],
                        genres=genres,
                    ),
                    "explanation": _build_block_why_it_matters(
                        stance="negative", theme=theme,
                        aspect_labels=[str(item.get("aspect_label", ""))],
                        aspect_keys=[str(item.get("aspect", ""))],
                        genres=genres,
                    ),
                    "aspect_keys": [str(item.get("aspect", ""))],
                    "stance": "negative",
                    "consensus_level": str(item.get("consensus_level", "medium")),
                    "mention_count": int(item.get("mention_count", 0)),
                    "evidence_snippets": snippets[:3],
                }
            )

    return blocks


def _build_evidence_blocks_v2(consensus_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build insight+evidence blocks with 3-stage gates.

    Stage 1: strict (stance + theme match, high consensus first)
    Stage 2: relaxed (stance match + aspect-aligned material)
    Stage 3: guaranteed_fill (global stance pools to avoid empty evidence)
    """
    aspects = list(consensus_payload.get("consensus_aspects", []) or [])
    game_context = consensus_payload.get("game_context", {}) or {}
    genres = list(game_context.get("genres", []) or [])
    context_text = _context_text(game_context)
    high_min = int(
        (consensus_payload.get("consensus_thresholds", {}) or {}).get("high_min_mentions", 12)
    )
    high_items = [item for item in aspects if item.get("consensus_level") == "high"]
    medium_items = [item for item in aspects if item.get("consensus_level") == "medium"]
    base_items = high_items if high_items else medium_items
    if not base_items:
        return []

    pool_items = high_items + medium_items
    global_stance_snippets = _collect_global_stance_snippets_v2(pool_items)
    global_material_snippets = _collect_global_material_snippets_v2(consensus_payload)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in base_items:
        stance = _block_stance(item)
        if stance not in {"positive", "negative"}:
            continue

        theme = _pick_block_theme(item, stance, genres=genres, context_text=context_text) or str(item.get("aspect_label", "?듭떖 ?섍껄"))
        key = (stance, theme)
        bucket = grouped.setdefault(
            key,
            {
                "stance": stance,
                "theme": theme,
                "mention_count": 0,
                "aspects": [],
                "aspect_labels": [],
                "consensus_level": str(item.get("consensus_level", "high")),
                "strict_candidates": [],
                "relaxed_candidates": [],
            },
        )

        bucket["mention_count"] += int(item.get("mention_count", 0))
        aspect = str(item.get("aspect", ""))
        if aspect and aspect not in bucket["aspects"]:
            bucket["aspects"].append(aspect)
        aspect_label = str(item.get("aspect_label", ""))
        if aspect_label and aspect_label not in bucket["aspect_labels"]:
            bucket["aspect_labels"].append(aspect_label)

        evidence_group = item.get("evidence_group", {}) or {}
        stance_snippets = list(evidence_group.get(stance, []) or [])
        match_tokens = _build_theme_match_tokens(bucket["theme"], bucket["aspects"])
        for index, snippet in enumerate(stance_snippets):
            evidence_item = _build_evidence_item(
                review_id=str((snippet or {}).get("review_id", "")),
                text=str((snippet or {}).get("snippet", "")),
                synthetic_prefix=f"group-{aspect}-{index + 1}",
            )
            if evidence_item is None:
                continue
            text = str(evidence_item["text"])
            if not _snippet_matches_stance(text, stance):
                continue
            if match_tokens and _snippet_matches_theme(text, match_tokens):
                bucket["strict_candidates"] = _append_unique_snippets_v2(
                    list(bucket["strict_candidates"]),
                    [evidence_item],
                    limit=32,
                )
            bucket["relaxed_candidates"] = _append_unique_snippets_v2(
                list(bucket["relaxed_candidates"]),
                [evidence_item],
                limit=32,
            )

    blocks: list[dict[str, Any]] = []
    for bucket in sorted(grouped.values(), key=lambda b: (-int(b["mention_count"]), b["theme"])):
        if bucket.get("consensus_level") == "high" and int(bucket["mention_count"]) < high_min:
            continue

        stage = "strict"
        snippets: list[dict[str, str]] = []
        snippets = _append_unique_snippets_v2(
            snippets,
            list(bucket.get("strict_candidates", [])),
            limit=8,
        )

        if len(snippets) < 2:
            stage = "relaxed"
            snippets = _append_unique_snippets_v2(
                snippets,
                list(bucket.get("relaxed_candidates", [])),
                limit=8,
            )
            snippets = _append_unique_snippets_v2(
                snippets,
                _collect_aspect_material_snippets_v2(
                    consensus_payload=consensus_payload,
                    stance=str(bucket.get("stance", "")),
                    aspects=list(bucket.get("aspects", [])),
                ),
                limit=8,
            )

        if len(snippets) < 2:
            stage = "guaranteed_fill"
            stance_key = str(bucket.get("stance", ""))
            snippets = _append_unique_snippets_v2(
                snippets,
                list(global_stance_snippets.get(stance_key, [])),
                limit=8,
            )
            snippets = _append_unique_snippets_v2(
                snippets,
                list(global_material_snippets.get(stance_key, [])),
                limit=8,
            )

        if len(snippets) < 2:
            continue

        title = _build_block_title(
            str(bucket["theme"]),
            str(bucket["stance"]),
            aspect_keys=_evidence_aspect_keys_for_context(
                list(bucket["aspects"]),
                genres=genres,
                context_text=context_text,
            ),
            genres=genres,
        )
        why_it_matters = _build_block_why_it_matters(
            stance=str(bucket["stance"]),
            theme=str(bucket["theme"]),
            aspect_labels=list(bucket["aspect_labels"]),
            aspect_keys=_evidence_aspect_keys_for_context(
                list(bucket["aspects"]),
                genres=genres,
                context_text=context_text,
            ),
            genres=genres,
        )
        blocks.append(
            {
                "title": title,
                "theme": str(bucket["theme"]),
                "why_it_matters": why_it_matters,
                "explanation": why_it_matters,
                "aspect_keys": list(bucket["aspects"]),
                "stance": str(bucket["stance"]),
                "consensus_level": str(bucket.get("consensus_level", "high")),
                "mention_count": int(bucket["mention_count"]),
                "evidence_quality_level": stage,
                "evidence_candidate_items": snippets[:8],
                "evidence_candidate_snippets": [str(item["text"]) for item in snippets[:8]],
                "evidence_snippets": [str(item["text"]) for item in snippets[:3]],
            }
        )
        if len(blocks) >= 4:
            break

    blocks = _ensure_min_stance_blocks_v2(
        blocks=blocks,
        source_items=pool_items,
        global_stance_snippets=global_stance_snippets,
        global_material_snippets=global_material_snippets,
        genres=genres,
        context_text=context_text,
    )
    return blocks


def _build_evidence_item(
    *,
    review_id: str,
    text: str,
    synthetic_prefix: str,
) -> dict[str, str] | None:
    normalized = _prepare_evidence_source_text(clean_markup_text(str(text or "")), limit=1200)
    if not normalized:
        return None
    if _is_noisy_evidence_text(normalized):
        return None
    resolved_review_id = str(review_id or "").strip()
    if not resolved_review_id:
        # Keep deterministic synthetic id for snippets that lost source ids in fallback paths.
        resolved_review_id = f"{synthetic_prefix}-{abs(hash(normalized))}"
    return {"review_id": resolved_review_id, "text": normalized}


def _coerce_evidence_items(raw_values: list[Any], *, synthetic_prefix: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for index, raw in enumerate(raw_values):
        if isinstance(raw, dict):
            review_id = str(raw.get("review_id", ""))
            text = str(raw.get("text", raw.get("snippet", "")))
        else:
            review_id = ""
            text = str(raw)
        evidence_item = _build_evidence_item(
            review_id=review_id,
            text=text,
            synthetic_prefix=f"{synthetic_prefix}-{index + 1}",
        )
        if evidence_item is not None:
            result.append(evidence_item)
    return result


def _append_unique_snippets_v2(
    base: list[dict[str, str]],
    incoming: list[dict[str, str]],
    *,
    limit: int,
    used_review_ids: set[str] | None = None,
    used_texts: set[str] | None = None,
) -> list[dict[str, str]]:
    result = list(base)
    seen_review_ids = {str(item.get("review_id", "")).strip() for item in result}
    seen_texts = {str(item.get("text", "")).strip() for item in result}
    blocked_review_ids = used_review_ids if used_review_ids is not None else set()
    blocked_texts = used_texts if used_texts is not None else set()

    for item in incoming:
        review_id = str(item.get("review_id", "")).strip()
        text = str(item.get("text", "")).strip()
        if not review_id or not text:
            continue
        if review_id in blocked_review_ids or review_id in seen_review_ids:
            continue
        if text in blocked_texts or text in seen_texts:
            continue
        seen_review_ids.add(review_id)
        seen_texts.add(text)
        result.append({"review_id": review_id, "text": text})
        if len(result) >= limit:
            break
    return result


def _collect_global_stance_snippets_v2(items: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    collected: dict[str, list[dict[str, str]]] = {"positive": [], "negative": []}
    for item in items:
        for stance in ("positive", "negative"):
            evidence_group = item.get("evidence_group", {}) or {}
            for index, snippet in enumerate(list(evidence_group.get(stance, []) or [])):
                evidence_item = _build_evidence_item(
                    review_id=str((snippet or {}).get("review_id", "")),
                    text=str((snippet or {}).get("snippet", "")),
                    synthetic_prefix=f"global-{stance}-{index + 1}",
                )
                if evidence_item is None:
                    continue
                text = str(evidence_item["text"])
                if not _snippet_matches_stance(text, stance):
                    continue
                collected[stance] = _append_unique_snippets_v2(
                    list(collected[stance]),
                    [evidence_item],
                    limit=128,
                )
    return collected


def _collect_global_material_snippets_v2(
    consensus_payload: dict[str, Any]
) -> dict[str, list[dict[str, str]]]:
    collected: dict[str, list[dict[str, str]]] = {"positive": [], "negative": []}
    use_rewrite = _should_use_llm_material_rewrite()
    for index, material in enumerate(list(consensus_payload.get("report_materials", []) or [])):
        if not isinstance(material, dict):
            continue
        stance = str(material.get("stance", "")).strip().lower()
        if stance not in {"positive", "negative"}:
            continue
        review_id = str(material.get("review_id", "")).strip()
        source_text = str(material.get("source_text", ""))
        refined_text = str(material.get("refined_text", ""))
        raw_text = refined_text if use_rewrite and refined_text else source_text
        evidence_item = _build_evidence_item(
            review_id=review_id,
            text=raw_text,
            synthetic_prefix=f"material-{stance}-{index + 1}",
        )
        if evidence_item is None:
            continue
        collected[stance] = _append_unique_snippets_v2(
            list(collected[stance]),
            [evidence_item],
            limit=128,
        )
    return collected


def _collect_aspect_material_snippets_v2(
    *,
    consensus_payload: dict[str, Any],
    stance: str,
    aspects: list[str],
) -> list[dict[str, str]]:
    aspect_set = {str(aspect).strip().lower() for aspect in aspects if str(aspect).strip()}
    if not aspect_set:
        return []

    result: list[dict[str, str]] = []
    use_rewrite = _should_use_llm_material_rewrite()
    for index, material in enumerate(list(consensus_payload.get("report_materials", []) or [])):
        if not isinstance(material, dict):
            continue
        material_stance = str(material.get("stance", "")).strip().lower()
        if material_stance != stance:
            continue
        review_id = str(material.get("review_id", "")).strip()
        material_tags = {
            str(tag).strip().lower()
            for tag in list(material.get("category_tags", []) or [])
            if str(tag).strip()
        }
        if material_tags and aspect_set.isdisjoint(material_tags):
            continue
        source_text = str(material.get("source_text", ""))
        refined_text = str(material.get("refined_text", ""))
        raw_text = refined_text if use_rewrite and refined_text else source_text
        evidence_item = _build_evidence_item(
            review_id=review_id,
            text=raw_text,
            synthetic_prefix=f"aspect-{stance}-{index + 1}",
        )
        if evidence_item is not None:
            result = _append_unique_snippets_v2(result, [evidence_item], limit=128)
    return result


def _ensure_min_stance_blocks_v2(
    *,
    blocks: list[dict[str, Any]],
    source_items: list[dict[str, Any]],
    global_stance_snippets: dict[str, list[dict[str, str]]],
    global_material_snippets: dict[str, list[dict[str, str]]],
    genres: list[str],
    context_text: str = "",
) -> list[dict[str, Any]]:
    result = list(blocks)
    existing = {str(block.get("stance", "")) for block in result}
    for stance in ("positive", "negative"):
        if stance in existing:
            continue
        candidate = _pick_best_item_for_stance_v2(source_items, stance)
        if not candidate:
            continue
        snippets: list[dict[str, str]] = []
        snippets = _append_unique_snippets_v2(snippets, list(global_stance_snippets.get(stance, [])), limit=8)
        snippets = _append_unique_snippets_v2(snippets, list(global_material_snippets.get(stance, [])), limit=8)
        if len(snippets) < 2:
            continue

        theme = _pick_block_theme(candidate, stance, genres=genres, context_text=context_text) or str(candidate.get("aspect_label", "?듭떖 ?섍껄"))
        aspect_label = str(candidate.get("aspect_label", ""))
        aspect_keys = _evidence_aspect_keys_for_context(
            [str(candidate.get("aspect", ""))],
            genres=genres,
            context_text=context_text,
        )
        why = _build_block_why_it_matters(
            stance=stance,
            theme=theme,
            aspect_labels=[aspect_label] if aspect_label else [],
            aspect_keys=aspect_keys,
            genres=genres,
        )
        result.append(
            {
                "title": _build_block_title(
                    theme,
                    stance,
                    aspect_keys=aspect_keys,
                    genres=genres,
                ),
                "theme": theme,
                "why_it_matters": why,
                "explanation": why,
                "aspect_keys": [str(candidate.get("aspect", ""))],
                "stance": stance,
                "consensus_level": str(candidate.get("consensus_level", "medium")),
                "mention_count": int(candidate.get("mention_count", 0)),
                "evidence_quality_level": "guaranteed_fill",
                "evidence_candidate_items": snippets[:8],
                "evidence_candidate_snippets": [str(item["text"]) for item in snippets[:8]],
                "evidence_snippets": [str(item["text"]) for item in snippets[:3]],
            }
        )
    return result


def _pick_best_item_for_stance_v2(items: list[dict[str, Any]], stance: str) -> dict[str, Any] | None:
    candidates = [item for item in items if _block_stance(item) == stance]
    if not candidates and stance == "negative":
        fallback = [
            item for item in items
            if float(item.get("negative_ratio", 0.0)) > 0.0
        ]
        if fallback:
            candidates = fallback
    if not candidates and stance == "positive":
        fallback = [
            item for item in items
            if float(item.get("negative_ratio", 0.0)) < 1.0
        ]
        if fallback:
            candidates = fallback
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            -_consensus_rank(str(item.get("consensus_level", "low"))),
            -float(item.get("negative_ratio", 0.0)) if stance == "negative" else float(item.get("negative_ratio", 0.0)),
            -int(item.get("mention_count", 0)),
        ),
    )[0]


# Use v2 generator as the active evidence strategy.
_build_evidence_blocks = _build_evidence_blocks_v2


def _block_stance(item: dict[str, Any]) -> str:
    tone = str(item.get("tone", "mixed"))
    negative_ratio = float(item.get("negative_ratio", 0.0))
    if tone == "negative" or negative_ratio >= 0.55:
        return "negative"
    if tone == "positive" or negative_ratio <= 0.40:
        return "positive"
    return "mixed"


def _pick_block_theme(
    item: dict[str, Any],
    stance: str,
    *,
    genres: list[str] | None = None,
    context_text: str = "",
) -> str | None:
    themes = [str(theme) for theme in list(item.get("themes", []) or []) if str(theme).strip()]
    if not themes:
        return None
    aspect = str(item.get("aspect", ""))
    genres = list(genres or [])
    if stance == "negative":
        contextual = _select_negative_theme_for_context(
            {"aspect": aspect, "themes": themes},
            genres=genres,
            context_text=context_text,
        )
        if contextual:
            return contextual
    contextual = _select_positive_theme_for_context(
        {"aspect": aspect, "themes": themes},
        genres=genres,
        context_text=context_text,
    )
    if contextual:
        return contextual
    if stance == "negative":
        return _choose_negative_theme(themes)
    return _choose_positive_theme(themes)


def _evidence_aspect_keys_for_context(
    aspect_keys: list[str],
    *,
    genres: list[str],
    context_text: str = "",
) -> list[str]:
    normalized = [str(item or "").strip() for item in aspect_keys if str(item or "").strip()]
    if _is_visual_novel_context(genres, context_text):
        return ["story"]
    if _is_narrative_openworld_context(genres, context_text):
        return ["story"]
    if _is_life_sim_context(genres, context_text):
        if any(key in {"gameplay", "story", "content_depth", "building_ux", "customization"} for key in normalized):
            return ["content_depth"]
    if _is_city_builder_context(genres, context_text):
        if any(key in {"gameplay", "building_ux", "content_depth"} for key in normalized):
            return ["building_ux"]
    if _is_looter_shooter_context(genres, context_text):
        if any(key in {"gameplay", "story", "content_depth", "customization"} for key in normalized):
            return ["content_depth"]
        if any(key in {"multiplayer", "matchmaking"} for key in normalized):
            return ["multiplayer"]
    if _is_coop_live_service_shooter_context(genres, context_text):
        if any(key in {"gameplay", "story", "multiplayer", "content_depth"} for key in normalized):
            return ["multiplayer"]
    if _is_automation_context(genres, context_text):
        if any(key in {"gameplay", "building_ux", "content_depth"} for key in normalized):
            return ["building_ux"]
    return normalized


def _build_block_title(
    theme: str,
    stance: str,
    *,
    aspect_keys: list[str],
    genres: list[str],
) -> str:
    return build_evidence_title(
        theme=theme,
        stance=stance,
        aspect_keys=aspect_keys,
        genres=genres,
    )


def _build_block_why_it_matters(
    *,
    stance: str,
    theme: str,
    aspect_labels: list[str],
    aspect_keys: list[str],
    genres: list[str],
) -> str:
    del aspect_labels  # kept for compatibility with older call sites
    return build_evidence_why_it_matters(
        stance=stance,
        theme=theme,
        aspect_keys=aspect_keys,
        genres=genres,
    )


def _theme_tokens(theme: str) -> list[str]:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", str(theme)).lower()
    tokens = [token.strip() for token in cleaned.split() if len(token.strip()) >= 2]
    return list(dict.fromkeys(tokens))


def _aspect_hint_tokens(aspects: list[str]) -> list[str]:
    tokens: list[str] = []
    for aspect in aspects:
        key = str(aspect or "").strip().lower()
        if not key:
            continue
        for token in ASPECT_EVIDENCE_HINTS.get(key, ()):
            token_text = str(token).strip().lower()
            if len(token_text) >= 2:
                tokens.append(token_text)
    return list(dict.fromkeys(tokens))


def _build_theme_match_tokens(theme: str, aspects: list[str]) -> list[str]:
    merged = _theme_tokens(theme) + _aspect_hint_tokens(aspects)
    return list(dict.fromkeys(merged))


def _snippet_matches_theme(text: str, theme_tokens: list[str]) -> bool:
    if not theme_tokens:
        return True
    normalized = str(text).lower().replace(" ", "")
    return any(token.replace(" ", "") in normalized for token in theme_tokens)


def _snippet_matches_stance(text: str, stance: str) -> bool:
    pos_hits, neg_hits = _snippet_stance_hits(text)
    if stance == "positive":
        if pos_hits == 0 and neg_hits == 0:
            return True
        return pos_hits > neg_hits
    if stance == "negative":
        if pos_hits == 0 and neg_hits == 0:
            return True
        return neg_hits > pos_hits
    return True


def _snippet_stance_hits(text: str) -> tuple[int, int]:
    normalized = str(text).lower()
    pos_hits = sum(1 for token in EVIDENCE_POSITIVE_HINTS if token in normalized)
    neg_hits = sum(1 for token in EVIDENCE_NEGATIVE_HINTS if token in normalized)
    return pos_hits, neg_hits


def _snippet_detected_stance(text: str) -> str | None:
    pos_hits, neg_hits = _snippet_stance_hits(text)
    if pos_hits >= neg_hits + 1:
        return "positive"
    if neg_hits >= pos_hits + 1:
        return "negative"
    return None


def _classify_snippet_stance(text: str, *, voted_up: bool) -> str:
    pos_hits, neg_hits = _snippet_stance_hits(text)
    if pos_hits >= neg_hits + 1:
        return "positive"
    if neg_hits >= pos_hits + 1:
        return "negative"
    return "positive" if voted_up else "negative"


def _compress_evidence_sections(
    evidence_sections: dict[str, list[dict[str, Any]]],
    *,
    use_llm: bool,
) -> dict[str, list[dict[str, Any]]]:
    """Select grouped evidence snippets with judge-only replacement."""
    strengths = list(evidence_sections.get("strengths", []) or [])
    risks = list(evidence_sections.get("risks", []) or [])
    if not strengths and not risks:
        return {"strengths": [], "risks": []}

    judge = (
        OpenAIEvidenceJudge()
        if use_llm and _should_use_llm_evidence_judge()
        else None
    )
    llm_judge_enabled = bool(judge and judge.available)

    def _compress_block_list(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compressed_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            snippets = block.get("evidence_snippets")
            if not isinstance(snippets, list):
                continue
            candidate_snippets = block.get("evidence_candidate_snippets")
            source_snippets = (
                list(candidate_snippets)
                if isinstance(candidate_snippets, list) and candidate_snippets
                else list(snippets)
            )
            if not source_snippets:
                continue
            stance = str(block.get("stance", "mixed"))
            match_tokens = _build_theme_match_tokens(
                str(block.get("theme", "")),
                [str(item) for item in list(block.get("aspect_keys", []) or [])],
            )

            rewritten: list[str] = []
            seen: set[str] = set()
            for raw in source_snippets[:8]:
                raw_text = str(raw or "").strip()
                if not raw_text:
                    continue

                normalized = _prepare_evidence_source_text(raw_text, limit=1200)
                if not normalized:
                    continue
                if _is_noisy_evidence_text(normalized):
                    continue
                # 압축 후 stance/theme 필터 탈락 시 원본 스니펫으로 재시도
                passes_filters = (
                    _snippet_matches_stance(normalized, stance)
                    and (not match_tokens or _snippet_matches_theme(normalized, match_tokens))
                )
                if not passes_filters:
                    fallback_text = _prepare_evidence_source_text(raw_text, limit=1200)
                    if (
                        fallback_text
                        and not _is_noisy_evidence_text(fallback_text)
                        and _snippet_matches_stance(fallback_text, stance)
                        and (not match_tokens or _snippet_matches_theme(fallback_text, match_tokens))
                    ):
                        normalized = fallback_text
                    else:
                        continue

                if normalized not in seen:
                    seen.add(normalized)
                    rewritten.append(normalized)
                if len(rewritten) >= 8:
                    break

            if len(rewritten) < 2:
                fallback_rewritten: list[str] = []
                fallback_seen: set[str] = set()
                for raw in source_snippets[:8]:
                    raw_text = str(raw or "").strip()
                    if not raw_text:
                        continue
                    normalized = _prepare_evidence_source_text(raw_text, limit=1200)
                    if not normalized:
                        continue
                    if normalized in fallback_seen:
                        continue
                    if not _snippet_matches_stance(normalized, stance):
                        continue
                    fallback_seen.add(normalized)
                    fallback_rewritten.append(normalized)
                    if len(fallback_rewritten) >= 8:
                        break
                if len(fallback_rewritten) >= 2:
                    rewritten = fallback_rewritten[:8]
            if len(rewritten) < 2:
                continue

            finalized = _select_evidence_snippets_for_block(
                block=block,
                candidates=rewritten[:8],
                judge=(judge if llm_judge_enabled else None),
            )
            if len(finalized) < 2:
                finalized = _rank_evidence_candidates(
                    candidates=rewritten[:8],
                    stance=stance,
                    match_tokens=match_tokens,
                )[:3]
            if len(finalized) < 2:
                continue
            next_block = dict(block)
            next_block["evidence_candidate_snippets"] = rewritten[:8]
            next_block["evidence_snippets"] = finalized[:3]
            compressed_blocks.append(next_block)
        return compressed_blocks

    compressed_strengths = _compress_block_list(strengths)[:3]
    compressed_risks = _compress_block_list(risks)[:3]

    compressed_strengths = _guarantee_min_stance_blocks(
        compressed_blocks=compressed_strengths,
        source_blocks=strengths,
        stance="positive",
    )[:3]
    compressed_risks = _guarantee_min_stance_blocks(
        compressed_blocks=compressed_risks,
        source_blocks=risks,
        stance="negative",
    )[:3]

    return {
        "strengths": compressed_strengths,
        "risks": compressed_risks,
    }


def _guarantee_min_stance_blocks(
    *,
    compressed_blocks: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]],
    stance: str,
) -> list[dict[str, Any]]:
    if compressed_blocks:
        return compressed_blocks
    fallback = _build_guaranteed_fill_block(source_blocks=source_blocks, stance=stance)
    if fallback is None:
        return []
    return [fallback]


def _build_guaranteed_fill_block(
    *,
    source_blocks: list[dict[str, Any]],
    stance: str,
) -> dict[str, Any] | None:
    for block in source_blocks:
        if not isinstance(block, dict):
            continue
        if str(block.get("stance", "")).strip().lower() != stance:
            continue

        merged_candidates: list[str] = []
        for raw in list(block.get("evidence_candidate_snippets", []) or []):
            merged_candidates.append(str(raw))
        for raw in list(block.get("evidence_snippets", []) or []):
            merged_candidates.append(str(raw))
        if not merged_candidates:
            continue

        snippets: list[str] = []
        signal_matched: list[str] = []
        signal_seen: set[str] = set()
        seen: set[str] = set()
        for raw in merged_candidates[:12]:
            normalized = _prepare_evidence_source_text(str(raw), limit=1200)
            if not normalized or normalized in seen:
                continue
            if _is_noisy_evidence_text(normalized):
                continue
            if not _snippet_matches_stance(normalized, stance):
                continue
            seen.add(normalized)
            snippets.append(normalized)
            if _snippet_detected_stance(normalized) == stance and normalized not in signal_seen:
                signal_seen.add(normalized)
                signal_matched.append(normalized)
            if len(snippets) >= 3:
                break

        if len(signal_matched) >= 2:
            snippets = signal_matched[:3]
        if len(snippets) < 2:
            # stance가 어긋나는 증거로 억지 채움을 하지 않는다.
            continue

        next_block = dict(block)
        next_block["evidence_quality_level"] = "guaranteed_fill"
        next_block["evidence_candidate_snippets"] = merged_candidates[:8]
        next_block["evidence_snippets"] = snippets[:3]
        return next_block

    return None


def _select_evidence_snippets_for_block(
    *,
    block: dict[str, Any],
    candidates: list[str],
    judge: OpenAIEvidenceJudge | None,
) -> list[str]:
    stance = str(block.get("stance", "mixed"))
    block_title = str(block.get("title", "핵심 근거"))
    block_why = str(block.get("why_it_matters", ""))
    match_tokens = _build_theme_match_tokens(
        str(block.get("theme", "")),
        [str(item) for item in list(block.get("aspect_keys", []) or [])],
    )
    # 1) stance/theme 하드 필터를 먼저 적용한다.
    hard_theme_filtered = [
        text
        for text in candidates
        if _snippet_matches_stance(text, stance)
        and (not match_tokens or _snippet_matches_theme(text, match_tokens))
    ]
    hard_stance_filtered = [
        text
        for text in candidates
        if _snippet_matches_stance(text, stance)
    ]
    ranked_source = hard_theme_filtered if len(hard_theme_filtered) >= 2 else hard_stance_filtered
    ranked = _rank_evidence_candidates(
        candidates=ranked_source,
        stance=stance,
        match_tokens=match_tokens,
        block_title=block_title,
        block_why_it_matters=block_why,
    )
    if len(ranked) < 2:
        return ranked

    preferred: list[str] = []
    if judge is not None and len(ranked) >= 2:
        selected_indices = judge.judge(
            title=str(block.get("title", "핵심 근거")),
            theme=str(block.get("theme", "")),
            why_it_matters=str(block.get("why_it_matters", "")),
            stance=stance,
            candidates=ranked[:8],
            timeout_seconds=20,
            retry_limit=1,
        )
        if selected_indices:
            for index in selected_indices:
                zero_based = index - 1
                if 0 <= zero_based < len(ranked):
                    preferred.append(ranked[zero_based])

    ordered: list[str] = []
    seen: set[str] = set()
    for text in preferred + ranked:
        if text in seen:
            continue
        seen.add(text)
        ordered.append(text)

    strict: list[str] = []
    strict_known: list[str] = []
    for text in ordered:
        if not _snippet_matches_stance(text, stance):
            continue
        if match_tokens and not _snippet_matches_theme(text, match_tokens):
            continue
        strict.append(text)
        if _snippet_detected_stance(text) == stance:
            strict_known.append(text)
        if len(strict) >= 6 and len(strict_known) >= 3:
            break
    if len(strict_known) >= 2:
        return strict_known[:3]
    if len(strict) >= 2:
        return strict[:3]

    relaxed = list(strict)
    relaxed_known = list(strict_known)
    for text in ordered:
        if text in relaxed:
            continue
        if not _snippet_matches_stance(text, stance):
            continue
        relaxed.append(text)
        if _snippet_detected_stance(text) == stance:
            relaxed_known.append(text)
        if len(relaxed) >= 6 and len(relaxed_known) >= 3:
            break
    if len(relaxed_known) >= 2:
        return relaxed_known[:3]
    if len(relaxed) >= 2:
        return relaxed[:3]

    return []


def _rank_evidence_candidates(
    *,
    candidates: list[str],
    stance: str,
    match_tokens: list[str],
    block_title: str = "",
    block_why_it_matters: str = "",
) -> list[str]:
    query_text = f"{block_title} {block_why_it_matters}".strip()
    use_similarity = _should_use_title_why_similarity_ranking()
    scored: list[tuple[float, int, str]] = []
    for index, text in enumerate(candidates):
        normalized = str(text).strip()
        if not normalized:
            continue
        score = 0.0
        if _snippet_matches_stance(normalized, stance):
            score += 4.0
        detected_stance = _snippet_detected_stance(normalized)
        if detected_stance == stance:
            score += 1.5
        elif detected_stance is None:
            score -= 1.2
        else:
            score -= 2.0
        if match_tokens and _snippet_matches_theme(normalized, match_tokens):
            score += 2.0
        if use_similarity and query_text:
            score += 3.0 * _title_query_similarity(query_text, normalized)
        if 20 <= len(normalized) <= 320:
            score += 1.0
        elif len(normalized) > 550:
            score -= 1.5
        scored.append((score, index, normalized))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def _items_to_texts(items: list[dict[str, str]], *, limit: int = 3) -> list[str]:
    return [str(item.get("text", "")) for item in items[:limit] if str(item.get("text", "")).strip()]


def _rank_evidence_candidates_v3(
    *,
    candidates: list[dict[str, str]],
    stance: str,
    match_tokens: list[str],
    block_title: str = "",
    block_why_it_matters: str = "",
) -> list[dict[str, str]]:
    query_text = f"{block_title} {block_why_it_matters}".strip()
    use_similarity = _should_use_title_why_similarity_ranking()
    scored: list[tuple[float, int, dict[str, str]]] = []
    for index, item in enumerate(candidates):
        normalized = str(item.get("text", "")).strip()
        if not normalized:
            continue
        score = 0.0
        if _snippet_matches_stance(normalized, stance):
            score += 4.0
        detected_stance = _snippet_detected_stance(normalized)
        if detected_stance == stance:
            score += 1.5
        elif detected_stance is None:
            score -= 1.2
        else:
            score -= 2.0
        if match_tokens and _snippet_matches_theme(normalized, match_tokens):
            score += 2.0
        if use_similarity and query_text:
            score += 3.0 * _title_query_similarity(query_text, normalized)
        if 20 <= len(normalized) <= 320:
            score += 1.0
        elif len(normalized) > 550:
            score -= 1.5
        scored.append((score, index, {"review_id": str(item.get("review_id", "")).strip(), "text": normalized}))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def _select_evidence_snippets_for_block_v3(
    *,
    block: dict[str, Any],
    candidates: list[dict[str, str]],
    judge: OpenAIEvidenceJudge | None,
) -> list[dict[str, str]]:
    stance = str(block.get("stance", "mixed"))
    block_title = str(block.get("title", "evidence"))
    block_why = str(block.get("why_it_matters", ""))
    match_tokens = _build_theme_match_tokens(
        str(block.get("theme", "")),
        [str(item) for item in list(block.get("aspect_keys", []) or [])],
    )

    hard_theme_filtered = [
        item
        for item in candidates
        if _snippet_matches_stance(str(item.get("text", "")), stance)
        and (
            not match_tokens
            or _snippet_matches_theme(str(item.get("text", "")), match_tokens)
        )
    ]
    hard_stance_filtered = [
        item
        for item in candidates
        if _snippet_matches_stance(str(item.get("text", "")), stance)
    ]
    ranked_source = hard_theme_filtered if len(hard_theme_filtered) >= 2 else hard_stance_filtered
    ranked = _rank_evidence_candidates_v3(
        candidates=ranked_source,
        stance=stance,
        match_tokens=match_tokens,
        block_title=block_title,
        block_why_it_matters=block_why,
    )
    if len(ranked) < 2:
        return ranked

    preferred: list[dict[str, str]] = []
    if judge is not None and len(ranked) >= 2:
        selected_indices = judge.judge(
            title=block_title,
            theme=str(block.get("theme", "")),
            why_it_matters=block_why,
            stance=stance,
            candidates=[str(item.get("text", "")) for item in ranked[:8]],
            timeout_seconds=20,
            retry_limit=1,
        )
        if selected_indices:
            for index in selected_indices:
                zero_based = index - 1
                if 0 <= zero_based < len(ranked):
                    preferred.append(ranked[zero_based])

    ordered: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in preferred + ranked:
        key = f"{str(item.get('review_id', '')).strip()}::{str(item.get('text', '')).strip()}"
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)

    strict: list[dict[str, str]] = []
    strict_known: list[dict[str, str]] = []
    for item in ordered:
        text = str(item.get("text", ""))
        if not _snippet_matches_stance(text, stance):
            continue
        if match_tokens and not _snippet_matches_theme(text, match_tokens):
            continue
        strict.append(item)
        if _snippet_detected_stance(text) == stance:
            strict_known.append(item)
        if len(strict) >= 6 and len(strict_known) >= 3:
            break
    if len(strict_known) >= 2:
        return strict_known[:3]
    if len(strict) >= 2:
        return strict[:3]

    relaxed = list(strict)
    relaxed_known = list(strict_known)
    for item in ordered:
        if item in relaxed:
            continue
        text = str(item.get("text", ""))
        if not _snippet_matches_stance(text, stance):
            continue
        relaxed.append(item)
        if _snippet_detected_stance(text) == stance:
            relaxed_known.append(item)
        if len(relaxed) >= 6 and len(relaxed_known) >= 3:
            break
    if len(relaxed_known) >= 2:
        return relaxed_known[:3]
    if len(relaxed) >= 2:
        return relaxed[:3]
    return []


def _build_guaranteed_fill_block_v3(
    *,
    source_blocks: list[dict[str, Any]],
    stance: str,
    used_review_ids: set[str],
    used_texts: set[str],
) -> dict[str, Any] | None:
    for block_index, block in enumerate(source_blocks):
        if not isinstance(block, dict):
            continue
        if str(block.get("stance", "")).strip().lower() != stance:
            continue

        merged_candidates: list[Any] = []
        merged_candidates.extend(list(block.get("evidence_candidate_items", []) or []))
        merged_candidates.extend(list(block.get("evidence_candidate_snippets", []) or []))
        merged_candidates.extend(list(block.get("evidence_snippets", []) or []))
        candidate_items = _coerce_evidence_items(
            merged_candidates[:12],
            synthetic_prefix=f"guaranteed-v3-{stance}-{block_index + 1}",
        )
        if not candidate_items:
            continue

        snippets: list[dict[str, str]] = []
        signal_matched: list[dict[str, str]] = []
        signal_seen: set[str] = set()
        seen: set[str] = set()
        for item in candidate_items:
            review_id = str(item.get("review_id", "")).strip()
            normalized = _prepare_evidence_source_text(
                clean_markup_text(str(item.get("text", ""))),
                limit=1200,
            )
            if not review_id or not normalized or normalized in seen:
                continue
            if review_id in used_review_ids or normalized in used_texts:
                continue
            if _is_noisy_evidence_text(normalized):
                continue
            if not _snippet_matches_stance(normalized, stance):
                continue
            seen.add(normalized)
            evidence_item = {"review_id": review_id, "text": normalized}
            snippets.append(evidence_item)
            if _snippet_detected_stance(normalized) == stance and normalized not in signal_seen:
                signal_seen.add(normalized)
                signal_matched.append(evidence_item)
            if len(snippets) >= 3:
                break

        if len(signal_matched) >= 2:
            snippets = signal_matched[:3]
        if len(snippets) < 2:
            continue

        for item in snippets:
            used_review_ids.add(str(item.get("review_id", "")).strip())
            used_texts.add(str(item.get("text", "")).strip())

        next_block = dict(block)
        next_block["evidence_quality_level"] = "guaranteed_fill"
        next_block["evidence_candidate_items"] = snippets[:8]
        next_block["evidence_candidate_snippets"] = _items_to_texts(snippets, limit=8)
        next_block["evidence_snippets"] = _items_to_texts(snippets, limit=3)
        return next_block
    return None


def _guarantee_min_stance_blocks_v3(
    *,
    compressed_blocks: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]],
    stance: str,
    used_review_ids: set[str],
    used_texts: set[str],
) -> list[dict[str, Any]]:
    if compressed_blocks:
        return compressed_blocks
    fallback = _build_guaranteed_fill_block_v3(
        source_blocks=source_blocks,
        stance=stance,
        used_review_ids=used_review_ids,
        used_texts=used_texts,
    )
    if fallback is None:
        return []
    return [fallback]


def _compress_evidence_sections_v3(
    evidence_sections: dict[str, list[dict[str, Any]]],
    *,
    use_llm: bool,
) -> dict[str, list[dict[str, Any]]]:
    strengths = list(evidence_sections.get("strengths", []) or [])
    risks = list(evidence_sections.get("risks", []) or [])
    if not strengths and not risks:
        return {"strengths": [], "risks": []}

    judge = (
        OpenAIEvidenceJudge()
        if use_llm and _should_use_llm_evidence_judge()
        else None
    )
    llm_judge_enabled = bool(judge and judge.available)
    logger.info(
        "report_llm_evidence_judge enabled=%s model=%s",
        llm_judge_enabled,
        judge.model if judge is not None else None,
    )
    used_review_ids: set[str] = set()
    used_texts: set[str] = set()

    def _compress_block_list(blocks: list[dict[str, Any]], *, stance: str) -> list[dict[str, Any]]:
        compressed_blocks: list[dict[str, Any]] = []
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            source_values = (
                list(block.get("evidence_candidate_items", []) or [])
                or list(block.get("evidence_candidate_snippets", []) or [])
                or list(block.get("evidence_snippets", []) or [])
            )
            source_items = _coerce_evidence_items(
                source_values[:12],
                synthetic_prefix=f"compress-v3-{stance}-{block_index + 1}",
            )
            if not source_items:
                continue

            block_stance = str(block.get("stance", "mixed"))
            match_tokens = _build_theme_match_tokens(
                str(block.get("theme", "")),
                [str(item) for item in list(block.get("aspect_keys", []) or [])],
            )

            rewritten = _append_unique_snippets_v2(
                [],
                [
                    item
                    for item in source_items
                    if _snippet_matches_stance(str(item.get("text", "")), block_stance)
                    and (
                        not match_tokens
                        or _snippet_matches_theme(str(item.get("text", "")), match_tokens)
                    )
                ],
                limit=8,
                used_review_ids=used_review_ids,
                used_texts=used_texts,
            )
            if len(rewritten) < 2:
                rewritten = _append_unique_snippets_v2(
                    [],
                    [
                        item
                        for item in source_items
                        if _snippet_matches_stance(str(item.get("text", "")), block_stance)
                    ],
                    limit=8,
                    used_review_ids=used_review_ids,
                    used_texts=used_texts,
                )
            if len(rewritten) < 2:
                continue

            finalized = _select_evidence_snippets_for_block_v3(
                block=block,
                candidates=rewritten[:8],
                judge=(judge if llm_judge_enabled else None),
            )
            if len(finalized) < 2:
                finalized = _rank_evidence_candidates_v3(
                    candidates=rewritten[:8],
                    stance=block_stance,
                    match_tokens=match_tokens,
                )[:3]
            finalized = _append_unique_snippets_v2(
                [],
                finalized,
                limit=3,
                used_review_ids=used_review_ids,
                used_texts=used_texts,
            )
            if len(finalized) < 2:
                continue

            for item in finalized:
                used_review_ids.add(str(item.get("review_id", "")).strip())
                used_texts.add(str(item.get("text", "")).strip())

            next_block = dict(block)
            next_block["evidence_candidate_items"] = rewritten[:8]
            next_block["evidence_candidate_snippets"] = _items_to_texts(rewritten, limit=8)
            next_block["evidence_snippets"] = _items_to_texts(finalized, limit=3)
            compressed_blocks.append(next_block)
        return compressed_blocks

    compressed_strengths = _compress_block_list(strengths, stance="positive")[:3]
    compressed_risks = _compress_block_list(risks, stance="negative")[:3]

    compressed_strengths = _guarantee_min_stance_blocks_v3(
        compressed_blocks=compressed_strengths,
        source_blocks=strengths,
        stance="positive",
        used_review_ids=used_review_ids,
        used_texts=used_texts,
    )[:3]
    compressed_risks = _guarantee_min_stance_blocks_v3(
        compressed_blocks=compressed_risks,
        source_blocks=risks,
        stance="negative",
        used_review_ids=used_review_ids,
        used_texts=used_texts,
    )[:3]

    return {"strengths": compressed_strengths, "risks": compressed_risks}


# Activate v3 compressor: global dedup by review_id/text + markup clean enforcement.
_compress_evidence_sections = _compress_evidence_sections_v3


def _title_query_similarity(query_text: str, candidate_text: str) -> float:
    query = _normalize_similarity_text(query_text)
    candidate = _normalize_similarity_text(candidate_text)
    if not query or not candidate:
        return 0.0

    query_tokens = _similarity_tokens(query)
    candidate_tokens = _similarity_tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0

    common = query_tokens & candidate_tokens
    jaccard = len(common) / max(len(query_tokens | candidate_tokens), 1)
    recall = len(common) / max(len(query_tokens), 1)
    sequence = SequenceMatcher(None, query, candidate).ratio()
    return round((0.45 * recall) + (0.35 * jaccard) + (0.20 * sequence), 6)


def _normalize_similarity_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _similarity_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", text)
        if token
    }


def _compress_evidence_reviews(
    report_payload: dict[str, Any],
    *,
    use_llm: bool,
) -> dict[str, Any]:
    """Backward-compat wrapper for old flat payload shape."""
    evidence_blocks = report_payload.get("evidence_reviews")
    if not isinstance(evidence_blocks, list):
        return report_payload
    sections = _build_evidence_sections_from_blocks(evidence_blocks)
    compressed = _compress_evidence_sections(sections, use_llm=use_llm)
    merged_blocks = list(compressed.get("strengths", [])) + list(compressed.get("risks", []))
    next_payload = dict(report_payload)
    next_payload["evidence_reviews"] = merged_blocks
    return next_payload


def _attach_evidence_sections(report_payload: dict[str, Any]) -> dict[str, Any]:
    """Backward-compat helper; maps old flat evidence into new section map."""
    blocks = report_payload.get("evidence_reviews")
    if not isinstance(blocks, list):
        next_payload = dict(report_payload)
        next_payload["evidence_sections"] = {"strengths": [], "risks": []}
        return next_payload

    next_payload = dict(report_payload)
    next_payload["evidence_sections"] = _build_evidence_sections_from_blocks(blocks)
    return next_payload


def _prepare_evidence_source_text(text: str, limit: int = 1200) -> str:
    """Keep source text readable, preserve line breaks, and avoid mid-sentence truncation."""
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized

    tokens: list[str] = []
    for part in re.split(r"(\n+)", normalized):
        if not part:
            continue
        if "\n" in part:
            tokens.append("\n\n" if len(part) >= 2 else "\n")
            continue
        sentences = _split_sentences(part)
        if sentences:
            tokens.extend(sentences)
            continue
        chunk = part.strip()
        if chunk:
            tokens.append(chunk)

    if not tokens:
        return normalized[:limit].rstrip()

    selected: list[str] = []
    total = 0
    last_was_text = False
    for token in tokens:
        if token in {"\n", "\n\n"}:
            if total == 0:
                continue
            if selected and selected[-1] in {"\n", "\n\n"}:
                if selected[-1] == "\n\n" or token == "\n":
                    continue
                selected[-1] = "\n\n"
                continue
            if total + len(token) > limit:
                break
            selected.append(token)
            total += len(token)
            last_was_text = False
            continue

        chunk = token.strip()
        if not chunk:
            continue
        prefix = " " if last_was_text else ""
        extra = len(prefix) + len(chunk)
        if total + extra > limit:
            break
        if prefix:
            selected.append(prefix)
        selected.append(chunk)
        total += extra
        last_was_text = True

    if selected:
        return "".join(selected).strip()
    return normalized[:limit].rstrip()


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _is_noisy_evidence_text(text: str) -> bool:
    target = " ".join((text or "").split()).strip()
    if not target:
        return True
    if len(target) < 18:
        return True
    compact = target.replace(" ", "")
    if not compact:
        return True
    if re.search(r"(.)\1{6,}", compact):
        return True
    jamo_count = len(re.findall(r"[ㄱ-ㅎㅏ-ㅣ]", compact))
    if jamo_count >= 8:
        return True
    readable = len(re.findall(r"[0-9A-Za-z가-힣]", compact))
    if readable / max(len(compact), 1) < 0.55:
        return True
    return False


def _is_evidence_block_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("title"), str):
            return False
        if not isinstance(item.get("why_it_matters"), str):
            return False
        if not isinstance(item.get("explanation"), str):
            return False
        if item.get("stance") not in {"positive", "negative"}:
            return False
        if item.get("consensus_level") not in {"high", "medium"}:
            return False
        if not isinstance(item.get("mention_count"), int):
            return False
        snippets = item.get("evidence_snippets")
        if not isinstance(snippets, list):
            return False
        if len(snippets) < 2 or len(snippets) > 3:
            return False
        if any(not isinstance(snippet, str) for snippet in snippets):
            return False
    return True


def _is_evidence_sections_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    strengths = value.get("strengths")
    risks = value.get("risks")
    if not _is_evidence_block_list(strengths):
        return False
    if not _is_evidence_block_list(risks):
        return False
    if any(item.get("stance") != "positive" for item in strengths):
        return False
    if any(item.get("stance") != "negative" for item in risks):
        return False
    return True

