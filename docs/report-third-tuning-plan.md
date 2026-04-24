# Report Third Tuning Plan

This document captures the third-stage tuning plan derived from the six-game QA pass:

- `Slay the Spire`
- `Factorio`
- `Hades`
- `Cities: Skylines`
- `XCOM 2`
- `Doki Doki Literature Club!`

The goal is not to memorize game-specific copy. The goal is to expand the
deterministic subtype layer so that the LLM receives better genre-aware signals
and fewer obviously wrong fallbacks.

## Why a Third Tuning Pass Is Needed

The second tuning pass stabilized several clusters well:

- soulslike / action RPG
- shooter / battle royale
- cozy / life sim
- management / sports management
- survival / sandbox

The six-game validation run exposed the next set of gaps:

1. `visual novel / narrative-only`
2. `city builder / urban management`
3. `automation / factory optimization`
4. `card deckbuilding / run planning`
5. `turn-based tactical pressure`

These are not single-game exceptions. They are repeatable play-pattern clusters
that deserve their own subtype treatment.

## New Subtype Priorities

### 1. `visual_narrative_immersion`
Use when the game is fundamentally driven by story, emotion, character
relationships, scene transitions, or interpretation rather than core action.

Good language:

- 서사와 감정선
- 관계와 장면 전환
- 이야기를 따라가는 몰입

Avoid:

- 전투
- 손맛
- 매칭 / 서버
- 성장 루프

### 2. `city_builder_management`
Use when the core satisfaction comes from city flow, traffic, zoning,
infrastructure, expansion, or urban balance.

Good language:

- 도시 운영
- 교통 흐름
- 배치와 확장
- 관리 피로

Avoid:

- 전투
- 교전
- 보스전

### 3. `automation_factory_optimization`
Use when the core loop is factory building, logistics, belts, bottlenecks,
throughput, and optimization.

Good language:

- 자동화
- 생산 라인
- 병목 해소
- 효율 설계

Avoid:

- 매칭 / 서버
- 전투 손맛
- 보스전

### 4. `deckbuilding_run_planning`
Use when the game is driven by cards, deck composition, path selection, relics,
or per-run planning.

Good language:

- 덱 구성
- 카드 선택
- 경로 판단
- 한 판 설계

Avoid:

- 전투 손맛
- 서사 몰입
- 오픈월드 탐험

### 5. `turn_based_tactical_pressure`
Use when the main appeal is turn-level decision pressure, positioning, squad
loss risk, and tactical tradeoffs.

Good language:

- 한 턴의 판단
- 전술 선택
- 병력 손실 압박
- 포지셔닝

Avoid:

- 탐험 / 단서 해석
- 실시간 전투 템포

## Step 1 Scope

Step 1 is deterministic only. It should not redesign the whole pipeline.

Files:

- `backend/report/services/player_fit_mapper.py`
- `backend/tests/test_player_fit_mapper.py`

Step 1 includes:

1. Add the five new subtypes above.
2. Expand genre/theme mapping so the new subtypes can be selected safely.
3. Add buyer-facing phrase tables for:
   - player fit
   - display theme
   - summaries
   - headline themes
   - evidence titles
   - evidence why-it-matters summaries
4. Keep fallbacks generic and safe.

Step 1 does **not**:

- change report writer prompts
- redesign evidence ranking
- add game-specific exception rules

## Step 2 Scope

Files:

- `backend/report/services/report_view.py`

Goals:

1. Use the new subtype outputs more strongly in:
   - player fit fallback
   - strengths / risks item shaping
   - evidence wording
2. Add stronger final genre mismatch safety nets.

## Step 3 Scope

Files:

- `backend/report/services/report_writer_llm.py`

Goals:

1. Add preferred vocabulary and disallowed vocabulary guidance for:
   - visual novel
   - city builder
   - automation
   - deckbuilder
   - turn-based tactics
2. Keep the writer focused on wording, not on re-deciding genre or subtype.

## Testing Priorities

Target tests for Step 1:

- DDLC should map to `visual_narrative_immersion`
- Cities should map to `city_builder_management`
- Factorio should map to `automation_factory_optimization`
- Slay the Spire should map to `deckbuilding_run_planning`
- XCOM 2 should map to `turn_based_tactical_pressure`

Regression tests should also keep passing for:

- PUBG-like shooter / battle royale
- Stardew-like cozy sim
- Football Manager-like management sim
- Rust-like survival sandbox

## Guardrail

Do not add subtype rules that are effectively game-specific.

Good subtype:

- `deckbuilding_run_planning`

Bad subtype:

- `pubg_drop_phase_mastery`

The question for every new subtype should be:

1. Does this describe a repeatable play-pattern cluster?
2. Does it apply to more than one game?
3. Does the buyer-facing copy become meaningfully different because of it?

If the answer is not clearly yes, prefer prompt tuning or a generic fallback
instead of another subtype.
