# Report Next Pattern Candidates - 2026-04-27

## Purpose

이 문서는 현재 리포트 풀 QA와 추가 분석 4개를 바탕으로,
다음 라운드에서 검토할 장르군 공백과 subtype / fallback 후보를 정리한 메모다.

핵심 원칙:

- 게임별 땜질 금지
- 특정 게임이 아니라 반복되는 게임군 패턴만 정리
- subtype 추가 전, guardrail / fallback / priority 문제인지 먼저 확인

## What We Confirmed

기존 `Hold / Not Yet` 후보만으로는 애매했던 공백이,
추가 분석 4개에서 다시 반복 확인됐다.

추가 분석 대상:

- `230410` Warframe
- `553850` HELLDIVERS 2
- `1174180` Red Dead Redemption 2
- `1222670` The Sims 4

이 결과로, 아래 문제는 개별 게임 문제가 아니라
장르군 공백일 가능성이 높아졌다.

## Reconfirmed Failure Patterns

### 1. Looter Shooter / Live-Service Progression

대표 신호:

- `Destiny 2`
- `Warframe`

반복된 문제:

- `플레이 흐름`
- `패턴을 익히며 반복 도전`
- `탐험과 세계 해석`

이런 문구가 메인으로 올라오고,
정작 필요한

- 장비 파밍
- 빌드 progression
- 반복 콘텐츠
- 시즌/장기 성장

문법은 약하게 나온다.

의미:

- 기존 `gameplay`, `story`, `content_depth` 조합만으로는
  looter shooter 계열을 제대로 설명하지 못한다.

### 2. Co-op Live-Service Shooter

대표 신호:

- `HELLDIVERS 2`

반복된 문제:

- `플레이 흐름`
- 지나치게 generic한 headline
- 협동/분대/반복 임무보다 추상적 장점이 먼저 올라옴

좋은 신호:

- `협동의 즐거움`
- `다양한 무기와 빌드 조합`

즉, 방향은 일부 맞지만 메인 카피를 지탱할 전용 fallback이 약하다.

### 3. Narrative Open-World / Immersive World

대표 신호:

- `The Witcher 3`
- `Red Dead Redemption 2`

반복된 문제:

- `탐험 / 자유도 / 세계 해석` 쪽으로 너무 단순화
- 싱글 중심 게임인데 `매칭과 서버 상태`가 risk로 올라옴
- 서사, 사건, 선택의 여운보다 공용 탐험 카피가 먼저 나옴

의미:

- `world_lore_discovery` 하나로는 부족하다.
- 탐험형 게임과 서사형 오픈월드 게임을 더 분리해서 볼 필요가 있다.

### 4. Life Sim / Social Simulation

대표 신호:

- `The Sims 4`

반복된 문제:

- `핵심 플레이를 반복하며 손에 익혀가는 재미`
- `세팅과 빌드`
- `탐험과 세계 해석`

같이 장르와 맞지 않는 공용 fallback이 올라옴.

필요한 문법:

- 생활 루프
- 관계/감정
- 집 꾸미기
- 시뮬레이션 상호작용

의미:

- 기존 `simulation` 계열 분화가 아직 life sim에는 충분하지 않다.

### 5. Grand Strategy / Colony Sim (already known, now still unresolved)

대표 신호:

- `Crusader Kings III`
- `RimWorld`

반복된 문제:

- `플레이 흐름`
- `탐험과 세계 해석`
- `전투/이동 흐름`

이런 공용 표현이 전략/운영/사건 중심 게임을 덮는다.

의미:

- 기존에 관찰된 공백이 여전히 유효함
- 이번 추가 분석으로 우선순위가 더 떨어진 것이 아니라, 오히려 유지됨

## Candidate Pattern Groups

다음 라운드에서 새 게임을 더 보기 전에,
후보 패턴은 아래처럼 정리해둘 수 있다.

### Candidate A. `looter_shooter_progression`

설명:

- 장비 파밍
- 빌드/무기 조합
- 반복 플레이 기반 성장
- 장기 live-service 구조

대표 게임:

- Destiny 2
- Warframe

우선 검토 레이어:

1. fallback copy
2. subtype priority
3. subtype 추가 여부

### Candidate B. `cooperative_live_service_shooter`

설명:

- 분대 협동
- 임무 반복
- 협력 기반 고난도 대응

대표 게임:

- HELLDIVERS 2

메모:

- `looter_shooter_progression`과 완전히 같은지,
  아니면 협동축이 더 강한 별도 패턴인지 분리 검토 필요

### Candidate C. `narrative_openworld_immersion`

설명:

- 서사 몰입
- 사건/선택의 여운
- 세계를 천천히 체험하는 감각

대표 게임:

- The Witcher 3
- Red Dead Redemption 2

우선 검토 레이어:

1. `world_lore_discovery` fallback이 과한지
2. matchmaking/server generic risk가 왜 섞이는지
3. 별도 subtype가 필요한지

### Candidate D. `life_sim_social_loop`

설명:

- 생활 루프
- 감정/관계
- 꾸미기/커스터마이징
- social simulation

대표 게임:

- The Sims 4
- inZOI

메모:

- `RimWorld`형 colony sim과 직접 같은 패턴은 아님
- sim 계열 내부 분화를 더 세울 때 후보가 된다

### Candidate E. `grand_strategy_dynasty_roleplay` / `colony_story_management`

설명:

- 장기 운영
- 관계/정치/사건
- emergent story

대표 게임:

- Crusader Kings III
- RimWorld

메모:

- 이번 추가 4개로 직접 더 강화된 건 아니지만,
  기존 Hold/Yet 분석과 충돌 없이 여전히 유효한 후보로 남는다

## Recommended Next Action

지금 바로 subtype를 추가하기보다,
다음 순서로 가는 것이 안전하다.

1. `looter shooter`, `narrative open-world`, `life sim` 공백을 별도 메모로 유지
2. 기존 fallback / guardrail / priority 문제로 먼저 설명 가능한지 확인
3. 그래도 반복되면 subtype 후보로 승격

## Not Recommended Yet

아래는 아직 하지 않는 편이 좋다.

- 특정 게임 이름을 딴 규칙 추가
- `if game == X` 형태의 분기
- 새 subtype를 한 번에 여러 개 바로 추가

이 단계에서는 공백을 확인한 것이지,
곧바로 subtype 추가가 정당화된 것은 아니다.

## Working Conclusion

현재까지 확인된 다음 장르군 공백 후보는 아래 순서로 정리된다.

1. `looter_shooter_progression`
2. `narrative_openworld_immersion`
3. `life_sim_social_loop`
4. `cooperative_live_service_shooter`
5. `grand_strategy_dynasty_roleplay`
6. `colony_story_management`

다음 라운드에서는 이 후보들에 대해
subtype를 바로 늘리기보다,
기존 fallback / guardrail / priority에서 먼저 설명 가능한지 검토하는 것이 우선이다.
