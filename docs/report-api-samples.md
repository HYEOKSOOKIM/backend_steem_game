# Report API Samples (report.v1)

## 1. Purpose

This document fixes the response contract for report APIs so frontend can attach without guessing.

Base path: `/api`


## 2. Common Error Payload

All error responses follow this shape:

```json
{
  "error_code": "string_code",
  "detail": "human readable message",
  "hint": "what to do next"
}
```

Examples:
- `request_validation_error` (422)
- `invalid_section` (400)
- `job_not_found` (404)
- `analysis_not_ready` (404)
- `snapshot_required_missing` (job failure code)


## 3. GET /api/v1/reports/{appid}/latest

Returns full `report.v1`.

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "window_days": 90,
  "data_quality": {
    "review_count_total": 1200,
    "review_count_eligible": 980,
    "confidence": 0.82,
    "flags": ["sample_ok"]
  },
  "snapshot": {
    "decision_label": "buy_with_caution",
    "decision_score": 0.41,
    "decision_confidence": 0.78,
    "key_drivers": [
      {
        "type": "risk",
        "category": "performance",
        "strength": 0.73
      },
      {
        "type": "strength",
        "category": "gameplay",
        "strength": 0.62
      }
    ]
  },
  "category_distribution": [
    {
      "category": "gameplay",
      "share": 0.33,
      "mentions": 323
    },
    {
      "category": "performance",
      "share": 0.22,
      "mentions": 216
    }
  ],
  "sentiment_x_category": [
    {
      "category": "gameplay",
      "positive": 0.74,
      "negative": 0.26,
      "net": 0.48,
      "impact_rank": 1
    },
    {
      "category": "performance",
      "positive": 0.31,
      "negative": 0.69,
      "net": -0.38,
      "impact_rank": 2
    }
  ],
  "top_themes": [
    {
      "theme_code": "combat_feel",
      "label": "Combat feel",
      "category": "gameplay",
      "polarity": "positive",
      "coverage": 0.28,
      "impact": 0.69
    },
    {
      "theme_code": "frame_drop",
      "label": "Frame drops",
      "category": "performance",
      "polarity": "negative",
      "coverage": 0.21,
      "impact": 0.72
    }
  ],
  "evidence_blocks": [
    {
      "id": "ev_001",
      "category": "performance",
      "theme_code": "frame_drop",
      "polarity": "negative",
      "quote": "Frame drops got worse after the last update.",
      "review_meta": {
        "created_at": "2026-04-20T12:00:00Z",
        "playtime_minutes": 1820,
        "votes_up": 54
      },
      "evidence_score": 0.88
    }
  ],
  "trend": {
    "summary": {
      "direction": "down",
      "up_categories": 1,
      "down_categories": 3,
      "flat_categories": 2,
      "limited_categories": 0
    },
    "spikes": [
      {
        "day": "2026-04-18",
        "type": "negative_spike",
        "category": "performance",
        "zscore_negative": 2.9
      }
    ]
  },
  "reviewer_segment": [
    {
      "segment": "new_low_playtime",
      "segment_label": "New players (low playtime)",
      "sample": 240,
      "net_sentiment": 0.14,
      "top_risk": "onboarding"
    },
    {
      "segment": "experienced_high_playtime",
      "segment_label": "Experienced players",
      "sample": 310,
      "net_sentiment": -0.07,
      "top_risk": "performance"
    }
  ],
  "final_recommendation": {
    "label": "buy_with_caution",
    "reason_summary": "Core gameplay is strong, but current performance risk remains meaningful.",
    "conditions_to_buy": [
      "You value gameplay more than technical polish.",
      "You can tolerate occasional stutter."
    ],
    "watch_items": [
      "Patch notes for optimization updates.",
      "Recent trend direction for performance sentiment."
    ],
    "inputs": {
      "risk_index": 0.58,
      "confidence": 0.78,
      "trend_direction": "down"
    }
  }
}
```


## 4. GET /api/v1/reports/{appid}/sections/{section}

Returns one section only.

Allowed `section` values:
- `snapshot`
- `category_distribution`
- `sentiment_x_category`
- `top_themes`
- `evidence_blocks`
- `trend`
- `reviewer_segment`
- `final_recommendation`

Common wrapper:

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "snapshot",
  "data": {}
}
```

### 4.1 section=snapshot

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "snapshot",
  "data": {
    "decision_label": "buy_with_caution",
    "decision_score": 0.41,
    "decision_confidence": 0.78,
    "key_drivers": [
      { "type": "risk", "category": "performance", "strength": 0.73 },
      { "type": "strength", "category": "gameplay", "strength": 0.62 }
    ]
  }
}
```

### 4.2 section=category_distribution

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "category_distribution",
  "data": [
    { "category": "gameplay", "share": 0.33, "mentions": 323 },
    { "category": "performance", "share": 0.22, "mentions": 216 }
  ]
}
```

### 4.3 section=sentiment_x_category

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "sentiment_x_category",
  "data": [
    {
      "category": "gameplay",
      "positive": 0.74,
      "negative": 0.26,
      "net": 0.48,
      "impact_rank": 1
    }
  ]
}
```

### 4.4 section=top_themes

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "top_themes",
  "data": [
    {
      "theme_code": "frame_drop",
      "label": "Frame drops",
      "category": "performance",
      "polarity": "negative",
      "coverage": 0.21,
      "impact": 0.72
    }
  ]
}
```

### 4.5 section=evidence_blocks

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "evidence_blocks",
  "data": [
    {
      "id": "ev_001",
      "category": "performance",
      "theme_code": "frame_drop",
      "polarity": "negative",
      "quote": "Frame drops got worse after the last update.",
      "review_meta": {
        "created_at": "2026-04-20T12:00:00Z",
        "playtime_minutes": 1820,
        "votes_up": 54
      },
      "evidence_score": 0.88
    }
  ]
}
```

Evidence generation notes:
- Max 3 categories are selected by evidence priority.
- For each selected category, negative evidence is attempted first, then positive.
- Empty/blank review text is skipped.
- Quote is truncated to 220 chars.
- Missing review metadata falls back to safe defaults (`created_at=null`, `playtime_minutes=0`, `votes_up=0`).

### 4.6 section=trend

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "trend",
  "data": {
    "summary": {
      "direction": "down",
      "up_categories": 1,
      "down_categories": 3,
      "flat_categories": 2,
      "limited_categories": 0
    },
    "spikes": [
      {
        "day": "2026-04-18",
        "type": "negative_spike",
        "category": "performance",
        "zscore_negative": 2.9
      }
    ]
  }
}
```

Trend direction rule:
- If any category has `recent_trend=limited`, overall `direction` is `limited`.
- Otherwise:
  - `up_categories > down_categories` -> `worsening`
  - `down_categories > up_categories` -> `improving`
  - equal -> `stable`

### 4.7 section=reviewer_segment

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "reviewer_segment",
  "data": [
    {
      "segment": "experienced_high_playtime",
      "segment_label": "Experienced players",
      "sample": 310,
      "net_sentiment": -0.07,
      "top_risk": "performance"
    }
  ]
}
```

### 4.8 section=final_recommendation

```json
{
  "schema_version": "report.v1",
  "app_id": 2456740,
  "snapshot_at": "2026-04-22T10:10:10Z",
  "section": "final_recommendation",
  "data": {
    "label": "buy_with_caution",
    "reason_summary": "Core gameplay is strong, but current performance risk remains meaningful.",
    "conditions_to_buy": [
      "You value gameplay more than technical polish.",
      "You can tolerate occasional stutter."
    ],
    "watch_items": [
      "Patch notes for optimization updates.",
      "Recent trend direction for performance sentiment."
    ],
    "inputs": {
      "risk_index": 0.58,
      "confidence": 0.78,
      "trend_direction": "down"
    }
  }
}
```


## 5. POST /api/v1/reports/jobs

Create one report generation job.

Concurrency policy:
- At most one active job (`queued` or `running`) per `appid`.
- If you call this endpoint again for the same `appid` while active job exists,
  server returns the existing job with `is_existing: true`.

Request:

```json
{
  "appid": 2456740,
  "review_pages": "all",
  "use_llm_fallback": false,
  "max_llm_reviews": 50,
  "llm_timeout_seconds": 20,
  "llm_retry_limit": 2,
  "llm_min_confidence": 0.7,
  "game_name": null
}
```

Response:

```json
{
  "job_id": "8f8f66a7d9e845d0a7418e4f6b7f1a4f",
  "status": "queued",
  "progress": 0,
  "created_at": "2026-04-22T10:10:10.000000+00:00",
  "started_at": null,
  "finished_at": null,
  "error_code": null,
  "error_message": null,
  "params": {
    "appid": 2456740,
    "review_pages": "all",
    "use_llm_fallback": false,
    "max_llm_reviews": 50,
    "llm_timeout_seconds": 20,
    "llm_retry_limit": 2,
    "llm_min_confidence": 0.7,
    "game_name": null,
    "data_root": "backend/data/report"
  },
  "result": null,
  "is_existing": false
}
```

Response (duplicate request while active job exists):

```json
{
  "job_id": "8f8f66a7d9e845d0a7418e4f6b7f1a4f",
  "status": "queued",
  "progress": 0,
  "error_code": null,
  "error_message": null,
  "is_existing": true
}
```


## 6. GET /api/v1/reports/jobs/{job_id}

Get one job status.

Response (success):

```json
{
  "job_id": "8f8f66a7d9e845d0a7418e4f6b7f1a4f",
  "status": "succeeded",
  "progress": 100,
  "created_at": "2026-04-22T10:10:10.000000+00:00",
  "started_at": "2026-04-22T10:10:11.000000+00:00",
  "finished_at": "2026-04-22T10:11:03.000000+00:00",
  "error_code": null,
  "error_message": null,
  "params": {
    "appid": 2456740,
    "review_pages": "all",
    "use_llm_fallback": false,
    "max_llm_reviews": 50,
    "llm_timeout_seconds": 20,
    "llm_retry_limit": 2,
    "llm_min_confidence": 0.7,
    "game_name": null,
    "data_root": "backend/data/report"
  },
  "result": {
    "app_id": 2456740,
    "pipeline_run_id": "2456740-20260422T101011Z",
    "snapshot_schema": "report.v1",
    "snapshot_path": "backend/data/report/report_snapshot/2456740(inZOI).json",
    "finished_at": "2026-04-22T10:11:03.000000+00:00",
    "raw_review_count": 1200,
    "processed_review_count": 1200,
    "included_review_count": 980
  },
  "is_existing": null
}
```

Response (failed by restart recovery):

```json
{
  "job_id": "8f8f66a7d9e845d0a7418e4f6b7f1a4f",
  "status": "failed",
  "progress": 100,
  "error_code": "interrupted_by_restart",
  "error_message": "job was interrupted by server restart before completion."
}
```

Response (failed by missing required snapshot fields):

```json
{
  "job_id": "8f8f66a7d9e845d0a7418e4f6b7f1a4f",
  "status": "failed",
  "progress": 100,
  "error_code": "snapshot_required_missing",
  "error_message": "required snapshot field is missing: final_recommendation.inputs.trend_direction"
}
```


## 7. POST /api/admin/ingest

Uses the same request DTO as `/api/v1/reports/jobs`.

Request:

```json
{
  "appid": 2456740,
  "review_pages": 4,
  "use_llm_fallback": false
}
```

Response:
- Returns offline pipeline result JSON payload.


## 8. Invalid Section Error Example

`GET /api/v1/reports/{appid}/sections/not-a-section`

```json
{
  "error_code": "invalid_section",
  "detail": "section must be one of: category_distribution, evidence_blocks, final_recommendation, reviewer_segment, sentiment_x_category, snapshot, top_themes, trend",
  "hint": "Use one of: snapshot, category_distribution, sentiment_x_category, top_themes, evidence_blocks, trend, reviewer_segment, final_recommendation."
}
```
