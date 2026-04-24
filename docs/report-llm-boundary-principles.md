# Report Pipeline Boundary Principles

이 문서는 Steam 리뷰 기반 리포트 파이프라인에서

- 어디까지를 규칙(deterministic logic)으로 처리하고
- 어디부터를 LLM으로 처리할지
- 실제 코드 수정 시 어떤 기준으로 판단할지

를 정리한 설계 원칙 문서다.

핵심 원칙은 한 줄로 요약된다.

> 규칙은 "틀린 말 방지"와 "구조 보장"에 쓰고, LLM은 "사람이 읽기 좋은 문장화"에 쓴다.


## 1. 왜 이 경계가 필요한가

리포트 품질 문제는 크게 두 종류로 나뉜다.

1. 사실/장르/문맥이 틀리는 문제
2. 문장이 딱딱하고 UI 카피처럼 읽히지 않는 문제

첫 번째는 규칙이 잡아야 하고, 두 번째는 LLM이 잘한다.

예를 들어:

- battle royale 슈터에 `보스전 패턴 학습`이 나오면 이건 **문체 문제**가 아니라 **문맥 오답**이다.
- 문맥은 맞는데 `지적이 있습니다`, `가능성이 큽니다`처럼 쓰면 이건 **표현 문제**다.

따라서 파이프라인은

- 규칙 레이어: 오답 방지, 구조 고정, 상태 결정
- LLM 레이어: 자연어 표현, 압축, UI 톤 정리

로 나뉘어야 한다.


## 2. 규칙이 맡아야 하는 것

규칙은 "정답을 예쁘게 쓰는 것"보다 "틀린 방향으로 가지 않게 막는 것"에 집중한다.

### 2.1 사실 / 데이터 무결성

다음은 LLM에 맡기지 않는다.

- 리뷰 수
- 출시일
- 무료/유료 여부
- 최근 리뷰 비율
- 수집 리뷰 수
- 장르/태그
- 추천 상태 enum (`buy_now`, `wait` 등)

이 정보는 검증 가능하고, 틀리면 리포트 신뢰성이 바로 무너진다.

### 2.2 구조 / 슬롯 / 스키마

다음은 deterministic 하게 유지한다.

- `report_plan`
- `report_display`
- `evidence_sections`
- `headline`
- `buy_timing_summary`
- `good_for[]`
- `top_strengths[]`
- `top_risks[]`

LLM은 필드 구조를 바꾸면 안 되고, 주어진 슬롯 안의 문장만 생성한다.

### 2.3 금지 규칙 / 안전장치

규칙이 가장 강하게 개입해야 하는 영역이다.

예:

- shooter / battle royale: `보스전`, `패턴 학습` 금지
- cozy / life sim: `전술 운영 판단`, `교전 템포` 금지
- sports management: `손맛`, `보스전`, `교전` 금지
- free-to-play 게임: `할인 때 사라` 금지

이 영역은 "잘 쓸지"가 아니라 "하지 말아야 할 말인지"의 문제다.

### 2.4 중간 추상화 신호 생성

규칙이 만들어야 하는 의미 신호:

- `aspect`
- `subtype`
- `player_fit_signal`
- `recent_state.status`
- `risk severity`
- `consensus_level`

이 신호는 최종 문장이 아니라 LLM이 사용할 의미 좌표다.

예:

- `subtype = openworld_pvp_tension`
- `subtype = cozy_growth_loop`
- `subtype = management_tactics`

이 단계까지는 deterministic 하게 유지하는 것이 디버깅과 회귀 방지에 유리하다.


## 3. LLM이 맡아야 하는 것

LLM은 "무슨 판단을 할지"보다 "그 판단을 어떻게 자연스럽게 말할지"를 담당한다.

### 3.1 UI/UX 카피 톤

다음 문장은 LLM이 다듬는 것이 맞다.

- `headline`
- `buy_timing_summary`
- `top_strengths[].summary`
- `top_risks[].summary`
- `recent_state.summary`

이 영역은 "분석 보고서 문장"이 아니라 "제품 UI 문장"이어야 하므로, 압축과 톤 조정이 중요하다.

### 3.2 중복 제거와 문장 리듬

예:

- title과 summary가 같은 말을 반복하지 않기
- 같은 단어 반복 줄이기
- 긴 문장을 1~2개의 짧은 문장으로 정리하기

이건 규칙보다 LLM이 훨씬 잘한다.

### 3.3 장르 문맥 안에서의 자연스러운 어휘 선택

중요한 경계:

- 장르 **판단 자체**는 규칙이 한다.
- 장르 문맥 안에서 **자연스러운 어휘 선택**은 LLM이 한다.

예:

- 규칙: `subtype = cozy_growth_loop`
- LLM: `부담 없이 차근차근 키워가는 재미` / `천천히 쌓이는 루틴의 만족감`

### 3.4 buyer-facing 설명 압축

리뷰 원문과 시그널은 거칠고 길다. 이를 1~2문장으로 줄여 사용자에게 보여주는 건 LLM이 맡는다.


## 4. 규칙이 하면 안 되는 것

### 4.1 게임별 완성형 문구 직접 매핑

피해야 하는 예:

- `PUBG -> 낙하와 자기장 운영이 중요한 플레이어`
- `Stardew -> 작물과 낚시를 좋아하는 플레이어`

이건 유지보수 불가능하고 과적합 위험이 크다.

### 4.2 완성형 문장을 과도하게 deterministic으로 생성

규칙은

- `subtype`
- `theme`
- `warning`

정도까지만 강하게 잡고, 최종 완성형 문장까지 직접 만들려고 하면 금방 generic 해진다.

### 4.3 예외 누적 방식

`이 게임만 따로` 같은 예외를 계속 추가하면 파이프라인이 깨지기 쉽다.

새 규칙을 추가할 때는 항상 먼저 묻는다.

- 이건 특정 게임만의 예외인가?
- 아니면 반복되는 플레이 패턴 범주인가?


## 5. LLM이 하면 안 되는 것

### 5.1 근거 없는 장르 해석

LLM이 리뷰 몇 줄만 보고

- "이건 소울라이크다"
- "이건 cozy 게임이다"

를 멋대로 판단하면 위험하다.

장르/플레이 subtype은 먼저 pipeline이 정해줘야 한다.

### 5.2 enum / 상태 결정

다음은 규칙이 결정하고, LLM은 설명만 한다.

- `buy_now` vs `wait`
- `improving` vs `mixed`
- evidence stance

### 5.3 evidence ranking 핵심 로직

LLM judge는 보조적으로 사용할 수 있지만, 1차 선택은 deterministic 신호가 우선이다.

- stance
- theme match
- mention_count
- genre consistency


## 6. 후처리 레이어의 역할

후처리는 생성기가 아니라 안전 필터다.

### 후처리가 맡는 것

- dangling title ending 제거
- 조사/문장 종결 어색함 정리
- 금지 표현 최종 필터링
- 장르 mismatch 마지막 safety net
- malformed persona fallback

### 후처리가 맡지 않는 것

- 새로운 의미 생성
- 장르 재해석
- recommendation 재결정


## 7. subtype를 추가할 때의 기준

새 subtype는 아래 3가지를 모두 만족할 때만 추가한다.

1. 여러 게임에 공통으로 나타나는 플레이 경험인가?
2. 기존 subtype로 설명하면 계속 부자연스러운가?
3. buyer-facing copy가 실제로 달라져야 할 정도로 다른가?

예:

- `cozy_growth_loop`: 추가 가치 큼
- `management_tactics`: 추가 가치 큼
- `openworld_pvp_tension`: 추가 가치 큼

반면:

- `PUBG_drop_phase_mastery`: 게임 특화 표현이므로 금지


## 8. 실제 코드 기준 체크리스트

아래 체크리스트는 PR 리뷰, 리팩터, 새 규칙 추가 시 바로 사용할 수 있다.

### 8.1 Seed / deterministic layer 체크리스트

대상 파일:

- `backend/report/services/report_view.py`
- `backend/report/services/player_fit_mapper.py`

확인 항목:

- [ ] 새 로직이 사실 데이터나 enum을 LLM에 넘기지 않는가
- [ ] `aspect -> 문장` 직접 매핑이 아니라 `aspect -> subtype -> seed signal` 구조를 유지하는가
- [ ] 장르 오답을 막는 금지 규칙이 있는가
- [ ] fallback가 게임별 특수 문구가 아니라 범용 플레이 패턴 문구인가
- [ ] shooter / battle royale에서 `보스전`, `패턴 학습` 같은 표현이 deterministic 단계에서 새지 않는가
- [ ] cozy / life sim에서 `전술`, `운영 판단` 같은 표현이 deterministic 단계에서 새지 않는가
- [ ] sports / management에서 `교전`, `손맛`, `보스전` 같은 표현이 deterministic 단계에서 새지 않는가
- [ ] 새 subtype가 "특정 게임 대응"이 아니라 "반복되는 플레이 패턴"으로 설명 가능한가

### 8.2 Prompt layer 체크리스트

대상 파일:

- `backend/report/services/report_writer_llm.py`

확인 항목:

- [ ] prompt가 분석 보고서 톤이 아니라 UI 카피 톤을 요구하는가
- [ ] title은 noun phrase로 끝나도록 제한하는가
- [ ] dangling particle (`은/는/이/가/의/과/와`) ending을 금지하는가
- [ ] seed persona를 불필요하게 재창작하지 않도록 제한하는가
- [ ] genre-specific preferred vocab / disallowed vocab이 들어가 있는가
- [ ] "지적이 있습니다", "가능성이 큽니다", "리스크", "포인트" 같은 분석체를 금지하는가
- [ ] title과 summary의 역할이 분리되도록 안내하는가

### 8.3 Post-processing layer 체크리스트

대상 파일:

- `backend/report/services/report_view.py`
- `backend/report/services/korean_report_proofreader.py`

확인 항목:

- [ ] title ending 보정이 너무 공격적이지 않은가
- [ ] 후처리가 새로운 의미를 만들지 않고, 어색함만 정리하는가
- [ ] malformed persona를 seed fallback으로 되돌리는 안전장치가 있는가
- [ ] 장르 mismatch 단어를 마지막에 한 번 더 걸러낼 수 있는가
- [ ] proofreader가 persona/item 문장을 다시 어색하게 만들지 않는가

### 8.4 테스트 체크리스트

대상 파일:

- `backend/tests/test_player_fit_mapper.py`
- `backend/tests/test_report_view.py`
- 필요 시 관련 테스트 추가

최소 테스트 세트:

- [ ] shooter / battle royale이 boss-pattern subtype로 가지 않는지
- [ ] cozy / farming sim이 management_tactics로 가지 않는지
- [ ] sports management가 management_tactics로 가는지
- [ ] survival / sandbox가 soulslike subtype로 가지 않는지
- [ ] free game recommendation이 `buy_on_sale` 같은 유료 recommendation으로 가지 않는지


## 9. 운영 원칙

### 원칙 1. subtype 수는 적게 유지한다

가능하면 10~20개 안에서 운영한다.  
새 subtype를 늘릴수록 유지보수 비용과 회귀 위험이 커진다.

### 원칙 2. 게임명이 아니라 플레이 패턴으로 확장한다

추가 기준은 항상

- 특정 게임만의 예외인가?
- 반복되는 게임군의 패턴인가?

를 먼저 본다.

### 원칙 3. 새 장르가 들어오면 먼저 fallback 품질을 확인한다

처음부터 subtype를 추가하지 말고,
기존 generic fallback으로도 충분히 자연스러운지 먼저 본다.

### 원칙 4. 장르 오답은 규칙으로, 말투 문제는 prompt로 해결한다

- 장르 mismatch -> seed / subtype / fallback 수정
- 문체 어색함 -> prompt / proofreader 수정

이 순서를 지킨다.


## 10. 결론

리포트 파이프라인은 아래 책임 분리를 유지해야 한다.

- 규칙: 사실, 구조, subtype, 금지 규칙, fallback, 상태 결정
- LLM: UI 카피 톤, 자연스러운 문장화, 중복 제거, buyer-facing 압축
- 후처리: dangling ending 정리, 금지 표현 필터, malformed output 복구

이 경계가 흐려지기 시작하면

- 규칙은 과적합되고
- LLM은 장르 오답을 만들고
- 후처리는 구조를 망가뜨리게 된다.

따라서 새 기능이나 새 장르 대응을 넣을 때는 항상 이 문서를 기준으로

1. 규칙이 맡아야 하는 문제인지
2. LLM이 맡아야 하는 문제인지
3. 후처리에서만 잡아야 하는 문제인지

를 먼저 구분하고 들어간다.
