# Report Operations Playbook

이 문서는 게임 리포트 파이프라인을 실제로 운영할 때의 기준을 정리한 플레이북이다.

목표는 세 가지다.

1. 리포트 생성 비용과 품질을 일관되게 관리한다.
2. 회귀를 빠르게 찾고, 게임별 땜질 대신 공통 패턴 단위로 수정한다.
3. 새 튜닝이 필요할 때 무엇부터 점검해야 하는지 순서를 고정한다.

## 1. 운영 모드

리포트 생성은 아래 3개 모드 중 하나로 구분한다.

### 1. `cheap batch mode`

대량 생성, 정기 갱신, 내부 재고 확보용 모드다.

- 목적: 비용을 낮추면서 기본 품질 확보
- 권장 모델:
  - `report_plan`: `gpt-4o-mini`
  - `report_display`: `gpt-4o-mini`
  - `proofreader`: off 또는 `gpt-4o-mini`
- 권장 설정:
  - `USE_LLM_PROOFREAD=false`
  - `USE_LLM_EVIDENCE_JUDGE=false`
  - `--use-llm-fallback`는 필요할 때만
  - `--max-llm-reviews`는 낮게 유지

언제 쓰나:

- 신규 게임 다건 생성
- 기존 리포트 재고 갱신
- QA 이전의 1차 산출물 생성

### 2. `qa mode`

장르 회귀 점검, fallback 변경 검증, 대표 샘플셋 확인용 모드다.

- 목적: 구조 변경이 실제 결과에 어떻게 반영되는지 확인
- 권장 모델:
  - `report_plan`: `gpt-4o-mini`
  - `report_display`: `gpt-4o-mini` 또는 필요 시 상향
  - `proofreader`: off 권장
- 권장 설정:
  - QA 대상 게임만 재생성
  - 변경이 있었던 장르군 중심으로 확인

언제 쓰나:

- subtype/fallback/prompt 수정 직후
- 고정 QA 샘플셋 회귀 점검
- 새 장르 패턴 검증

### 3. `publish mode`

실제 데모, 외부 공유, 최종 점검용 모드다.

- 목적: 비용보다 결과 품질 우선
- 권장 모델:
  - `report_plan`: `gpt-4o-mini`
  - `report_display`: 더 높은 품질 설정 허용
  - `proofreader`: 필요 시 on
- 권장 설정:
  - 꼭 필요한 게임만 재생성
  - 결과 QA 후 공개

언제 쓰나:

- 배포 전 최종 검수
- 중요 샘플 리포트 업데이트
- 외부 시연용 결과 생성

## 2. 고정 QA 샘플셋

회귀 점검은 아래 샘플셋을 기준으로 본다.

1. `Doki Doki Literature Club!`
2. `Cities: Skylines`
3. `Factorio`
4. `Slay the Spire`
5. `XCOM 2`
6. `PUBG: BATTLEGROUNDS`
7. `Football Manager 26`

이 샘플셋은 다음을 빠르게 드러낸다.

- 장르 오답
- generic fallback drift
- subtype 우선순위 문제
- evidence wording 회귀

자세한 기대/금지 문구는 아래 문서를 본다.

- `report-genre-qa-regression-checklist.md`

## 3. Pass / Partial / Fail 기준

### Pass

- 장르 오답이 없다.
- 기대 문구 방향이 대체로 살아 있다.
- 남는 문제는 문장 다듬기 수준이다.

### Partial Pass

- 장르 오답은 없지만 generic fallback이 눈에 띈다.
- 기대 문구가 일부만 반영된다.

### Fail

- 다른 장르 어휘가 섞여 나온다.
- 금지 문구가 다시 등장한다.
- subtype보다 액션/탐험/매칭 같은 공용 fallback이 우세하다.

## 4. 실패 시 점검 순서

게임별 예외를 만들기 전에 항상 아래 순서로 본다.

### 1. guardrail 문제인가

예:

- visual novel에 `전투`, `매칭`
- city builder에 `전투/이동 흐름`
- automation에 `서버`, `매칭`

이 경우:

- `report_view.py`의 장르 가드부터 본다.

### 2. fallback copy 문제인가

예:

- `핵심 플레이 감각`
- `손에 익을수록 재미가 커진다`
- `가격 대비 만족을 매우 엄격하게 따지는 플레이어`

이 경우:

- `player_fit_mapper.py`의 phrase table
- `report_view.py` final rewrite

를 먼저 본다.

### 3. subtype priority 문제인가

예:

- deckbuilder가 narrative 쪽으로 새는 경우
- turn-based tactics가 story/gameplay generic으로 흐르는 경우

이 경우:

- 기존 subtype가 잘못 뽑히는지
- 기존 subtype보다 generic fallback이 우선하는지

를 본다.

### 4. 그래도 해결이 안 되면 subtype 추가 검토

이때도 게임별 subtype는 금지한다.

새 subtype는 아래 원칙을 만족할 때만 추가한다.

- 여러 게임에 재사용 가능
- 기존 subtype로 반복해서 어색함
- buyer-facing 문구가 실제로 달라져야 함

세부 원칙은 아래 문서를 본다.

- `subtype-tuning-checklist.md`

## 5. 재생성 트리거

리포트를 다시 생성하는 기준은 아래처럼 고정한다.

### 재생성이 필요한 경우

- subtype/fallback/prompt 수정이 있었을 때
- 특정 장르군에서 회귀가 확인됐을 때
- 사용자 피드백으로 장르 오답이 보고됐을 때
- 리뷰 수가 크게 늘어 최신성 확보가 필요할 때
- 공개용/배포용 리포트를 새로 만들 때

### 재생성을 미루는 경우

- 문체 polish만 아주 작게 변경됐고 영향 범위가 적을 때
- 기존 QA 샘플셋이 모두 Pass일 때
- 명백한 장르 회귀 없이 generic wording 일부만 남아 있을 때

## 6. 수정 범위 원칙

### 먼저 할 일

- guardrail 정리
- fallback copy 정리
- subtype priority 조정

### 나중에 할 일

- subtype 추가
- prompt 확장

### 하지 말아야 할 일

- 특정 게임 이름 기준 분기
- 개별 게임 전용 subtype
- 회귀 검증 없이 대량 subtype 추가

## 7. 현재 운영 상태

현재 구조는 아래 상태를 목표로 한다.

- 큰 장르 오답 방지: 완료
- 공용 fallback generic drift 축소: 진행 중
- 게임별 튜닝 금지, 패턴 단위 튜닝: 유지

즉, 앞으로는 새 게임이 이상하게 보일 때도 먼저 이 질문부터 한다.

1. 이건 guardrail 문제인가?
2. 이건 fallback copy 문제인가?
3. 이건 subtype priority 문제인가?
4. 그래도 안 되면 정말 새 subtype가 필요한가?

이 순서를 지키면 리포트 파이프라인이 게임별 땜질로 흘러가지 않는다.
