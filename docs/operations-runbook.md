# Backend Operations Runbook

## 1. 운영 모드

- 사용자 경로: 스냅샷 조회만 수행
- 운영 경로: 수동 ingest/재분석 수행

## 2. 기본 API

- `GET /api/games`
- `GET /api/games/{appid}/report`
- `GET /api/games/{appid}/analysis`
- `GET /api/games/{appid}/metadata`
- `POST /api/admin/ingest` (운영자 수동 실행)

## 3. 표준 운영 절차

1. 코호트/대상 게임 확정
2. 오프라인 ingest 실행
3. 산출물 확인(`raw/processed/analysis/metadata/report`)
4. 품질 게이트 실행
5. `demo_games.json` 노출 상태 갱신

## 4. refresh-check 절차

1. 최신 리뷰 수와 마지막 분석 리뷰 수 비교
2. 임계치 초과 시 `needs_refresh`
3. 운영자가 수동 재분석 실행

## 5. all-mode 정책

- 운영 수동 실행에서만 허용
- page cap/timeout을 명시적으로 기록
- 부분 수집 여부(`all_mode_cap_reached`)를 판단 근거로 저장

## 6. 장애 대응

- ingest 실패 시 대상 appid를 격리하고 원인 로그를 보존
- 릴리즈 게이트 실패 시 해당 appid 노출 비활성화
