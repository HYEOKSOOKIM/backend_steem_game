"""Pydantic DTO models for report job APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

MAX_NUMERIC_REVIEW_PAGES = 200


class ReportJobCreateRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appid: int = Field(..., gt=0)
    review_pages: int | Literal["all"] = "all"
    use_llm_fallback: bool = False
    max_llm_reviews: int = Field(default=50, ge=1, le=200)
    llm_timeout_seconds: int = Field(default=20, ge=1, le=120)
    llm_retry_limit: int = Field(default=2, ge=0, le=5)
    llm_min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    game_name: str | None = Field(default=None, max_length=200)

    @field_validator("review_pages", mode="before")
    @classmethod
    def validate_review_pages(cls, value):
        if value is None:
            return "all"
        if isinstance(value, bool):
            raise ValueError(
                f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
            )
        if isinstance(value, int):
            if 1 <= value <= MAX_NUMERIC_REVIEW_PAGES:
                return value
            raise ValueError(
                f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
            )
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "all":
                return "all"
            if normalized.isdigit():
                parsed = int(normalized)
                if 1 <= parsed <= MAX_NUMERIC_REVIEW_PAGES:
                    return parsed
            raise ValueError(
                f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
            )
        raise ValueError(
            f"review_pages must be 'all' or an integer between 1 and {MAX_NUMERIC_REVIEW_PAGES}."
        )

    @field_validator("game_name", mode="before")
    @classmethod
    def normalize_game_name(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("game_name must be a string.")
        normalized = value.strip()
        return normalized or None


class ReportJobParamsDTO(BaseModel):
    appid: int
    review_pages: int | str
    use_llm_fallback: bool
    max_llm_reviews: int
    llm_timeout_seconds: int
    llm_retry_limit: int
    llm_min_confidence: float
    game_name: str | None = None
    data_root: str


class ReportJobResultDTO(BaseModel):
    app_id: int
    pipeline_run_id: str | None = None
    snapshot_schema: str
    snapshot_path: str | None = None
    finished_at: str
    raw_review_count: int
    processed_review_count: int
    included_review_count: int


class ReportJobDTO(BaseModel):
    job_id: str
    status: str
    progress: int
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    params: ReportJobParamsDTO
    result: ReportJobResultDTO | None = None
    is_existing: bool | None = None
