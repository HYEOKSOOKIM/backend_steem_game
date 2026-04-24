"""Core schemas for review ingestion, preprocessing, and analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass()
class RawReview:
    """Raw review record normalized from the external Steam payload."""

    review_id: str
    appid: int
    review_text: str
    voted_up: bool
    timestamp_created: int
    timestamp_updated: int | None = None
    playtime_forever: float | None = None
    playtime_at_review_hours: float | None = None
    num_reviews: int | None = None
    author_steamid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass()
class GameMetadata:
    """Minimal game metadata for report context."""

    appid: int
    name: str | None = None
    genres: list[str] = field(default_factory=list)
    price_model: str = "unknown"
    release_stage: str = "unknown"
    release_date_text: str | None = None
    header_image: str | None = None
    capsule_image: str | None = None
    capsule_imagev5: str | None = None
    short_description: str | None = None
    steam_store_url: str | None = None
    steam_recommendation_count: int | None = None
    steam_review_score_desc: str | None = None
    steam_total_positive: int | None = None
    steam_total_negative: int | None = None
    steam_total_reviews: int | None = None
    is_free: bool | None = None
    coming_soon: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass()
class ProcessedReview:
    """Processed review record after deterministic preprocessing."""

    review_id: str
    appid: int
    review_text: str
    normalized_text: str
    voted_up: bool
    timestamp_created: int
    timestamp_updated: int | None
    playtime_forever: float | None
    playtime_at_review_hours: float | None
    num_reviews: int | None
    author_steamid: str | None
    hangul_ratio: float
    is_low_quality: bool
    is_profanity_only: bool
    ambiguity_flags: list[str] = field(default_factory=list)
    included_in_analysis: bool = False
    rule_decision: str = ""
    rule_confidence: float = 0.0
    llm_invoked: bool = False
    llm_decision: str | None = None
    llm_confidence: float | None = None
    final_decision_source: str = "rule"
    final_decision: str = "unknown"
    category_tags: list[str] = field(default_factory=list)
    canonical_theme: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass()
class IssueSignal:
    """Explainable signal set for a single issue category."""

    mention_count: int
    negative_ratio: float
    recent_trend: str
    experienced_player_share: float
    themes: list[str] = field(default_factory=list)
    sample_reviews: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass()
class AnalysisResult:
    """Top-level analysis response for one game."""

    appid: int
    sample_size_tier: str
    trend_status: str
    trend_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    issue_signals: dict[str, IssueSignal] = field(default_factory=dict)
    summary: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issue_signals"] = {
            key: signal.to_dict() for key, signal in self.issue_signals.items()
        }
        return data


@dataclass()
class IngestRequest:
    """Request payload for a future ingestion endpoint."""

    appids: list[int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
