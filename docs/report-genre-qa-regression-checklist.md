# Report Genre QA Regression Checklist

This document defines the fixed QA sample set we use to detect copy regressions
after report tuning changes.

The purpose of this checklist is not to prove that every game is perfect.
The purpose is to make sure the system does **not** drift back into obviously
wrong or overly generic genre language.

## How To Use This Checklist

When a meaningful report-generation change lands:

1. regenerate the reports for the sample set below
2. review the fields listed for each game
3. check the expected wording directions
4. verify the forbidden wording does not reappear

Focus first on:

- `headline`
- `good_for`
- `not_good_for`
- `top_strengths`
- `top_risks`
- `evidence_sections.title`
- `evidence_sections.why_it_matters`

## Fixed QA Sample Set

### 1. Doki Doki Literature Club!

Purpose:
- guard `visual novel / narrative-only`

Expected direction:
- 서사
- 감정선
- 관계
- 몰입
- 텍스트 흐름

Forbidden drift:
- 전투
- 교전
- 손맛
- 매칭
- 서버
- 핵심 플레이
- 성장 루프

### 2. Cities: Skylines

Purpose:
- guard `city builder / urban management`

Expected direction:
- 도시 운영
- 교통 흐름
- 배치
- 확장
- 관리 피로

Forbidden drift:
- 전투
- 교전
- 보스전
- 패턴 학습
- 이동 흐름
- 핵심 플레이 감각

### 3. Factorio

Purpose:
- guard `automation / factory optimization`

Expected direction:
- 자동화
- 생산 라인
- 병목
- 효율
- 확장

Forbidden drift:
- 매칭
- 서버
- 보스전
- 교전 손맛
- 핵심 플레이 감각

### 4. Slay the Spire

Purpose:
- guard `deckbuilding / run planning`

Expected direction:
- 덱 구성
- 카드 선택
- 경로 판단
- 유물 조합
- 한 판 루프

Forbidden drift:
- 오픈월드
- 탐험
- 전투 손맛
- 서사와 분위기
- 핵심 플레이 감각

### 5. XCOM 2

Purpose:
- guard `turn-based tactical pressure`

Expected direction:
- 한 턴의 판단
- 전술 선택
- 병력 손실 압박
- 포지셔닝
- 실수 비용

Forbidden drift:
- 실시간 손맛
- 교전 템포
- 탐험과 세계 해석
- 서사와 분위기
- 전투/이동 흐름

### 6. PUBG: BATTLEGROUNDS

Purpose:
- guard `battle royale / competitive shooter`

Expected direction:
- 교전 템포
- 생존 긴장감
- 팀플레이
- 에임 / 총기 감각
- 매치 흐름

Forbidden drift:
- 보스전
- 패턴 학습
- 서사 몰입 일반론
- cozy / routine wording

### 7. Football Manager 26

Purpose:
- guard `sports management / long-horizon tactics`

Expected direction:
- 전술 설계
- 스쿼드 운영
- 시즌 운영
- 장기 판단
- 로스터 관리

Forbidden drift:
- 전투 손맛
- 보스전
- 패턴 학습
- 교전 템포
- 핵심 플레이 감각

## Review Rules

### Pass

- genre wording is directionally correct
- forbidden drift does not appear
- remaining issues are mostly minor generic copy

### Partial Pass

- no major genre mismatch
- but shared fallback copy is still too generic

Typical example:
- `핵심 플레이 감각`
- `손에 익을수록 재미가 커진다`

### Fail

- obviously wrong genre language returns
- multiple forbidden phrases appear
- player-fit or headline becomes misleading for the game family

## What To Do When A Failure Appears

Use this order:

1. check forbidden-phrase guardrails
2. check shared fallback copy
3. check subtype priority / mapping
4. only then consider a new subtype

Do **not** jump straight to title-specific rules.

## Why This Set Exists

This set was chosen because each game exposes a different failure mode:

- DDLC -> narrative-only
- Cities -> city-builder wording
- Factorio -> automation wording
- Slay the Spire -> deckbuilder wording
- XCOM 2 -> turn-based tactics wording
- PUBG -> shooter / battle royale wording
- Football Manager 26 -> management wording

Together they catch the most important genre-drift regressions without forcing
the system into game-by-game tuning.
