"""Helpers for normalizing Steam review and app metadata payloads."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from report.models.schemas import GameMetadata, RawReview

STEAM_REVIEW_ENDPOINT = "https://store.steampowered.com/appreviews/{appid}"
STEAM_APP_DETAILS_ENDPOINT = "https://store.steampowered.com/api/appdetails"
ALL_MODE_PAGE_CAP = 200


def normalize_steam_review(appid: int, payload: dict[str, Any]) -> RawReview:
    """Normalize one Steam review payload into the internal raw schema."""
    author = payload.get("author", {})

    return RawReview(
        review_id=str(payload.get("recommendationid", "")),
        appid=appid,
        review_text=payload.get("review", ""),
        voted_up=bool(payload.get("voted_up", False)),
        timestamp_created=int(payload.get("timestamp_created", 0)),
        timestamp_updated=(
            int(payload["timestamp_updated"])
            if payload.get("timestamp_updated") is not None
            else None
        ),
        playtime_forever=_minutes_to_hours(author.get("playtime_forever")),
        playtime_at_review_hours=_minutes_to_hours(author.get("playtime_at_review")),
        num_reviews=_safe_int(author.get("num_reviews")),
        author_steamid=str(author.get("steamid")) if author.get("steamid") else None,
    )


def normalize_steam_reviews(appid: int, payload: dict[str, Any]) -> list[RawReview]:
    """Normalize a Steam API response into internal raw review records."""
    reviews = payload.get("reviews", [])
    return [normalize_steam_review(appid, review) for review in reviews]


def normalize_steam_review_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Steam appreviews query summary for game-level display."""
    summary = payload.get("query_summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}

    return {
        "steam_review_score_desc": _clean_optional_string(summary.get("review_score_desc")),
        "steam_total_positive": _safe_int(summary.get("total_positive")),
        "steam_total_negative": _safe_int(summary.get("total_negative")),
        "steam_total_reviews": _safe_int(summary.get("total_reviews")),
    }


def normalize_steam_game_metadata(appid: int, payload: dict[str, Any]) -> GameMetadata:
    """Normalize Steam appdetails payload into report-context metadata."""
    app_data = _extract_appdetails_data(appid, payload)
    genres = [
        str(entry.get("description", "")).strip()
        for entry in app_data.get("genres", [])
        if str(entry.get("description", "")).strip()
    ]

    is_free = app_data.get("is_free")
    categories = [
        str(entry.get("description", "")).strip()
        for entry in app_data.get("categories", [])
        if str(entry.get("description", "")).strip()
    ]
    release_date = app_data.get("release_date") or {}
    coming_soon = bool(release_date.get("coming_soon", False))
    recommendations = app_data.get("recommendations") or {}

    return GameMetadata(
        appid=appid,
        name=str(app_data.get("name")) if app_data.get("name") else None,
        genres=genres,
        price_model=_derive_price_model(is_free=is_free, app_data=app_data),
        release_stage=_derive_release_stage(
            coming_soon=coming_soon,
            categories=categories,
            genres=genres,
        ),
        release_date_text=(
            str(release_date.get("date"))
            if release_date.get("date")
            else None
        ),
        header_image=_clean_optional_string(app_data.get("header_image")),
        capsule_image=_clean_optional_string(app_data.get("capsule_image")),
        capsule_imagev5=_clean_optional_string(app_data.get("capsule_imagev5")),
        short_description=_clean_optional_string(app_data.get("short_description")),
        steam_store_url=f"https://store.steampowered.com/app/{appid}",
        steam_recommendation_count=_safe_int(recommendations.get("total")),
        **_normalize_price_overview(app_data.get("price_overview")),
        is_free=bool(is_free) if is_free is not None else None,
        coming_soon=coming_soon,
    )


def _clean_optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def fetch_steam_reviews(
    appid: int,
    *,
    language: str = "koreana",
    filter_type: str = "recent",
    review_type: str = "all",
    purchase_type: str = "all",
    num_per_page: int = 100,
    cursor: str = "*",
    max_pages: int | None = None,
    timeout: int = 20,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Fetch Steam reviews with cursor pagination.

    ``max_pages=None`` means "all mode", capped by ``ALL_MODE_PAGE_CAP``.
    """
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be >= 1")
    effective_max_pages = max_pages if max_pages is not None else ALL_MODE_PAGE_CAP

    pages: list[dict[str, Any]] = []
    current_cursor = cursor
    seen_cursors: set[str] = set()
    seen_review_ids: set[str] = set()

    page_count = 0
    while True:
        if page_count >= effective_max_pages:
            break

        payload = fetch_steam_reviews_page(
            appid,
            language=language,
            filter_type=filter_type,
            review_type=review_type,
            purchase_type=purchase_type,
            num_per_page=num_per_page,
            cursor=current_cursor,
            timeout=timeout,
        )
        pages.append(payload)
        page_count += 1

        next_cursor = payload.get("cursor")
        reviews = payload.get("reviews", []) or []
        new_unique_reviews = 0
        for review in reviews:
            review_id = str(review.get("recommendationid", ""))
            if not review_id:
                continue
            if review_id in seen_review_ids:
                continue
            seen_review_ids.add(review_id)
            new_unique_reviews += 1

        if progress_callback is not None:
            progress_callback(
                {
                    "appid": appid,
                    "page": page_count,
                    "max_pages": effective_max_pages,
                    "all_mode": max_pages is None,
                    "page_review_count": len(reviews),
                    "page_new_unique_reviews": new_unique_reviews,
                    "cumulative_unique_reviews": len(seen_review_ids),
                }
            )

        if not next_cursor or not reviews or str(next_cursor) in seen_cursors:
            break

        seen_cursors.add(str(next_cursor))
        current_cursor = str(next_cursor)

    merged = _merge_review_pages(pages)
    all_mode_cap_reached = max_pages is None and page_count >= ALL_MODE_PAGE_CAP
    merged["_fetch_stats"] = {
        "pages_fetched": page_count,
        "deduped_review_count": len(merged.get("reviews", [])),
        "request_timeout_seconds": timeout,
        "filter_type": filter_type,
        "language": language,
        "all_mode_page_cap": ALL_MODE_PAGE_CAP if max_pages is None else None,
        "all_mode_cap_reached": all_mode_cap_reached,
    }
    return merged


def fetch_steam_reviews_page(
    appid: int,
    *,
    language: str = "koreana",
    filter_type: str = "recent",
    review_type: str = "all",
    purchase_type: str = "all",
    num_per_page: int = 100,
    cursor: str = "*",
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch one page of Steam reviews from the public store endpoint."""
    params = urlencode(
        {
            "json": 1,
            "language": language,
            "filter": filter_type,
            "review_type": review_type,
            "purchase_type": purchase_type,
            "num_per_page": num_per_page,
            "cursor": cursor,
        }
    )
    url = f"{STEAM_REVIEW_ENDPOINT.format(appid=appid)}?{params}"
    payload = _fetch_json(url, "Steam review", timeout=timeout)

    if payload.get("success") not in {1, None}:
        raise RuntimeError("Steam review response did not report success")

    return payload


def fetch_steam_game_metadata(
    appid: int,
    *,
    language: str = "koreana",
    country_code: str = "KR",
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch minimal app metadata from Steam appdetails."""
    params = urlencode(
        {
            "appids": appid,
            "l": language,
            "cc": country_code,
        }
    )
    url = f"{STEAM_APP_DETAILS_ENDPOINT}?{params}"
    payload = _fetch_json(url, "Steam appdetails", timeout=timeout)

    app_entry = payload.get(str(appid))
    if not isinstance(app_entry, dict) or not app_entry.get("success"):
        raise RuntimeError("Steam appdetails response did not report success")

    return payload


def _fetch_json(url: str, label: str, *, timeout: int = 20) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # pragma: no cover - network is mocked in tests.
        raise RuntimeError(f"{label} request failed with status {exc.code}") from exc
    except URLError as exc:  # pragma: no cover - network is mocked in tests.
        raise RuntimeError(f"{label} request failed due to a network error") from exc


def _merge_review_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge paginated Steam responses into one payload with deduplicated reviews."""
    if not pages:
        return {"success": 1, "reviews": [], "cursor": "*"}

    merged = dict(pages[0])
    merged_reviews: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for page in pages:
        for review in page.get("reviews", []) or []:
            review_id = str(review.get("recommendationid", ""))
            if review_id and review_id in seen_ids:
                continue
            if review_id:
                seen_ids.add(review_id)
            merged_reviews.append(review)

    merged["reviews"] = merged_reviews
    merged["cursor"] = pages[-1].get("cursor", merged.get("cursor", "*"))
    return merged


def _extract_appdetails_data(appid: int, payload: dict[str, Any]) -> dict[str, Any]:
    app_entry = payload.get(str(appid))
    if isinstance(app_entry, dict):
        if app_entry.get("success") and isinstance(app_entry.get("data"), dict):
            return app_entry["data"]
        if isinstance(app_entry.get("data"), dict):
            return app_entry["data"]

    if isinstance(payload.get("data"), dict):
        return payload["data"]

    if payload.get("appid") == appid:
        return payload

    return payload


def _derive_price_model(*, is_free: Any, app_data: dict[str, Any]) -> str:
    if is_free is True:
        return "free_to_play"
    if app_data.get("price_overview"):
        return "paid"
    return "unknown"


def _normalize_price_overview(price_overview: Any) -> dict[str, Any]:
    if not isinstance(price_overview, dict):
        return {
            "price_currency": None,
            "price_current": None,
            "price_original": None,
            "price_current_formatted": None,
            "price_original_formatted": None,
            "price_discount_percent": None,
        }

    current = _safe_int_or_none(price_overview.get("final"))
    original = _safe_int_or_none(price_overview.get("initial"))
    if original is None:
        original = current

    return {
        "price_currency": _clean_optional_string(price_overview.get("currency")),
        "price_current": current,
        "price_original": original,
        "price_current_formatted": _clean_optional_string(price_overview.get("final_formatted")),
        "price_original_formatted": _clean_optional_string(price_overview.get("initial_formatted")),
        "price_discount_percent": _safe_int_or_none(price_overview.get("discount_percent")),
    }


def _derive_release_stage(
    *,
    coming_soon: bool,
    categories: list[str],
    genres: list[str],
) -> str:
    if coming_soon:
        return "coming_soon"

    combined = " ".join([*categories, *genres]).lower()
    if "early access" in combined or "앞서 해보기" in combined:
        return "early_access"

    return "released"


def _minutes_to_hours(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 60.0, 2)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _safe_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

