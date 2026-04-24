"""Pydantic DTO models for report.v1 API responses."""

from __future__ import annotations

from pydantic import BaseModel


class DataQualityDTO(BaseModel):
    review_count_total: int
    review_count_eligible: int
    confidence: float
    flags: list[str]


class SnapshotDriverDTO(BaseModel):
    type: str
    category: str
    strength: float


class SnapshotSectionDTO(BaseModel):
    decision_label: str
    decision_score: float
    decision_confidence: float
    key_drivers: list[SnapshotDriverDTO]


class CategoryDistributionItemDTO(BaseModel):
    category: str
    share: float
    mentions: int


class SentimentCategoryItemDTO(BaseModel):
    category: str
    positive: float
    negative: float
    net: float
    impact_rank: int


class TopThemeItemDTO(BaseModel):
    theme_code: str
    label: str
    category: str
    polarity: str
    coverage: float
    impact: float


class EvidenceReviewMetaDTO(BaseModel):
    created_at: str | None = None
    playtime_minutes: int
    votes_up: int


class EvidenceBlockDTO(BaseModel):
    id: str
    category: str
    theme_code: str | None = None
    polarity: str
    quote: str
    review_meta: EvidenceReviewMetaDTO
    evidence_score: float


class TrendSummaryDTO(BaseModel):
    direction: str
    up_categories: int = 0
    down_categories: int = 0
    flat_categories: int = 0
    limited_categories: int = 0


class TrendSpikeDTO(BaseModel):
    day: str | None = None
    type: str | None = None
    category: str | None = None
    zscore_negative: float | None = None


class TrendSectionDTO(BaseModel):
    summary: TrendSummaryDTO
    spikes: list[TrendSpikeDTO]


class ReviewerSegmentDTO(BaseModel):
    segment: str
    segment_label: str
    sample: int
    net_sentiment: float
    top_risk: str | None = None


class FinalRecommendationInputsDTO(BaseModel):
    risk_index: float
    confidence: float
    trend_direction: str


class FinalRecommendationSectionDTO(BaseModel):
    label: str
    reason_summary: str
    conditions_to_buy: list[str]
    watch_items: list[str]
    inputs: FinalRecommendationInputsDTO


class ReportV1DTO(BaseModel):
    schema_version: str
    app_id: int
    snapshot_at: str
    window_days: int
    data_quality: DataQualityDTO
    snapshot: SnapshotSectionDTO
    category_distribution: list[CategoryDistributionItemDTO]
    sentiment_x_category: list[SentimentCategoryItemDTO]
    top_themes: list[TopThemeItemDTO]
    evidence_blocks: list[EvidenceBlockDTO]
    trend: TrendSectionDTO
    reviewer_segment: list[ReviewerSegmentDTO]
    final_recommendation: FinalRecommendationSectionDTO

