# Steam 구매판단 리포트 구현 로드맵 (MVP)

## 0. 문서 목적

이 문서는 현재 `backend/report` 기반 구현 상태를 기준으로,  
앞으로 진행해야 할 과정을 "실행 순서 + 완료 기준"으로 정리한 작업 기준서다.

- 기준: 기존 프로토타입 재활용
- 원칙: 꼭 필요한 기능부터 구현
- 범위: Steam 리뷰 기반 구매판단 리포트 MVP


## 1. 현재 상태 (완료)

### 1.0 최근 반영 사항

- `POST /api/admin/ingest` 요청도 `ReportJobCreateRequestDTO`로 검증 공통화 완료
- report job store를 파일 기반으로 영속화 (`jobs/report_jobs.json`)
- 서버 재시작 시 `queued/running` job을 `failed(interrupted_by_restart)`로 복구 처리
- API 에러 응답 포맷 통일 (`error_code`, `detail`, `hint`)
- report.v1 API JSON 샘플 문서 추가 (`backend/docs/report-api-samples.md`)
- 동일 appid 동시 실행 제한 정책 고정 (active job 재요청 시 기존 job 반환)
- job 완료 전 snapshot 필수 필드 누락 체크 추가 (`snapshot_required_missing`)
- final_recommendation 입력값 생성 규칙 테스트 고정 (`risk_index/confidence/trend_direction`)
- evidence block 생성 규칙 고정 (top category/negative-first/quote-limit/fallback defaults)
- trend 최소 규칙 테스트 고정 (limited 우선, up/down 비교, 동률 stable)
- 프론트 `/report` MVP 골격 + loading/error/empty + job 상태 조회 연결

### 1.1 API/스키마 기반

- `POST /api/v1/reports/jobs` 뼈대 구현
- `GET /api/v1/reports/jobs/{job_id}` 뼈대 구현
- `GET /api/v1/reports/{appid}/latest` 구현 (`report.v1` 반환)
- `GET /api/v1/reports/{appid}/sections/{section}` 구현 (섹션 단위 반환)
- `POST /api/v1/reports/jobs` 요청 DTO 검증 고정

### 1.2 파이프라인/저장

- `offline_pipeline` 결과를 `report_snapshot`에 저장하도록 연결
- snapshot 유효성 실패 시 job 실패 처리 (`snapshot_missing`, `snapshot_invalid`)

### 1.3 프론트 연동 준비

- 백엔드 `report.v1` DTO 고정
- 프론트 타입(`reportV1`) 기본 골격 고정


## 2. 전체 구현 단계 (앞으로 해야 할 일)

## Phase 1. 입력/계약 안정화

### 목적

프론트/백엔드 간 계약을 더 이상 흔들리지 않게 고정한다.

### 작업

1. `POST /api/admin/ingest`도 `jobs`와 동일한 요청 DTO 규칙 적용
2. 에러 응답 포맷 통일 (`error_code`, `detail`, `hint`)
3. 섹션 endpoint 응답 필드 순서/명칭 최종 고정
4. API 문서 샘플(JSON) 작성

### 완료 기준

- 요청 필드/범위가 코드와 문서에서 동일
- 프론트는 샘플 JSON만으로 mock 없이 붙일 수 있음

### 리스크

- DTO가 늦게 바뀌면 프론트 재작업 증가


## Phase 2. Job 실행 신뢰성 강화 (필수)

### 목적

`queued -> running -> succeeded/failed` 상태가 운영 환경에서도 안정적으로 동작하도록 만든다.

### 작업

1. in-memory job store를 파일 또는 DB 기반으로 교체
2. 서버 재시작 시 job 복구 정책 정의
3. 중복 job 정책 확정 (동일 appid 동시 실행 제한)
4. progress 업데이트 기준 고정

### 완료 기준

- 서버 재시작 후에도 job 상태 조회 가능
- 동일 appid 중복 실행 정책이 API에서 일관되게 보임

### 리스크

- 메모리 저장소 유지 시 재시작/멀티프로세스에서 상태 유실


## Phase 3. Snapshot 생성 파이프라인 최소 완성 (필수)

### 목적

리포트 섹션이 빈 껍데기가 아니라 실제 구매판단 데이터로 채워지게 만든다.

### 작업

1. 섹션별 필수 집계값 누락 여부 점검
2. `final_recommendation` 계산 입력 필드 고정
3. evidence block 생성 규칙 고정 (대표 인용, 카테고리, polarity)
4. trend 계산 기준 최소 버전 확정 (최근 구간 비교)

### 완료 기준

- demo 대상 appid에서 8개 섹션이 모두 채워진 snapshot 생성
- `final_recommendation`이 입력 데이터 변화에 따라 일관되게 변함

### 리스크

- 분석 결과가 섹션 스키마를 만족하지 못하면 snapshot 실패


## Phase 4. 프론트 리포트 MVP 연결 (필수)

### 목적

사용자가 실제로 "살지 말지"를 스캔만으로 판단할 수 있게 화면을 연결한다.

### 작업

1. report 페이지 데이터 패칭: `latest` + 필요시 `sections`
2. 섹션 컴포넌트 골격 배치
3. loading/error/empty 상태 공통 처리
4. design token(typography/spacing/card) 기준으로 기본 스타일 적용

### 완료 기준

- 최초 로딩 후 주요 섹션이 순서대로 렌더링됨
- 실패/빈데이터 상태에서도 화면이 깨지지 않음

### 리스크

- API 계약과 프론트 타입 불일치


## Phase 5. 운영/배포 필수선 정리 (필수)

### 목적

실서비스 기준 최소 운영이 가능한 형태를 만든다.

### 작업

1. 데이터 저장소 전략 확정
   - 기본: 메타/집계는 DB
   - 대용량 원본(raw/processed/snapshot)은 오브젝트 스토리지(S3)
2. 보존 정책 수립 (TTL, 버전, 재생성 기준)
3. 재실행(runbook) 정리 (실패 재시도, 수동 재생성)
4. 운영 로그 필드 고정 (appid, pipeline_run_id, job_id, error_code)

### 완료 기준

- 장애 시 재현/복구 절차가 문서대로 수행 가능
- 저장 비용/조회 성능 기준이 명시됨

### 리스크

- 저장소 역할 분리가 없으면 비용/성능/운영 복잡도 동시 악화


## Phase 6. 2차 확장 (MVP 이후)

### 후보

1. Trend 고도화 (시계열 smoothing, spike 라벨)
2. Segment 고도화 (playtime 기반 세분화 개선)
3. Recommendation explainability 강화 (가중치 근거 노출)
4. 캐시/재생성 정책 고도화 (부분 갱신)

### 원칙

- 사용자 가치가 명확할 때만 추가
- 디자인 시스템 일관성 우선


## 3. 실행 우선순위 (권장 순서)

1. Phase 1: 입력/계약 안정화
2. Phase 2: Job 저장소 영속화
3. Phase 3: Snapshot 생성 규칙 고정
4. Phase 4: 프론트 MVP 연결
5. Phase 5: 운영/배포 필수선
6. Phase 6: 확장


## 4. 이번 스프린트 권장 TODO

1. `admin/ingest` 요청 DTO를 `jobs` DTO와 공통화
2. job store를 파일 또는 SQLite로 교체
3. snapshot 필수 필드 누락 체크 추가
4. 프론트 report 섹션 골격 + 에러/로딩 상태 먼저 연결
5. 운영 로그 필드 표준화


## 5. 결정 필요 항목

1. Job 저장소: 파일 JSON vs SQLite
2. 오브젝트 저장소: 로컬 우선 vs 바로 S3
3. trend 최소 규칙: 2구간 비교 vs 3구간 비교
4. final recommendation 규칙: 임계치 기반 vs 점수 합산 기반


## 6. Definition of Done (MVP)

아래를 모두 만족하면 MVP 완료로 본다.

1. `jobs` 생성/조회가 재시작 이후에도 유지됨
2. `latest` 리포트가 8개 섹션을 안정적으로 반환함
3. 프론트에서 섹션 순서대로 구매판단 흐름이 보임
4. 실패 시 에러코드와 재실행 절차가 문서화되어 있음
5. 저장소(DB/S3) 역할이 분리되어 운영 가능함
- /report UX hardening: section empty fallback text + active-job auto polling + ?appid= query support
