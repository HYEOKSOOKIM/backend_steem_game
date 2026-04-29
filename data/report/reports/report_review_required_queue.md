# Review Required Queue

- Source mode: `dry_run`
- Appids: `578080, 1174180, 3551340`
- Review-required actions: `2`
- Holds: `5`

> 이 문서는 자동 적용용이 아닙니다. `review_required`는 사람이 근거와 문맥을 확인한 뒤 수동 채택 여부를 판단해야 하는 후보입니다.

## PUBG: BATTLEGROUNDS (578080)

- QA status: `repairable_with_holds`
- Semantic status: `fail`
- Failures: `4` / critical `4`
- Report path: `data\report\report\578080(PUBG_ BATTLEGROUNDS).json`

### Review-Required Actions

#### Action 1: `not_good_for[1]`

- Action: `rewrite_from_best_claim`
- Failure type: `theme_drift`
- Claim id: `risk_1`
- Safety: `review_required`
- Reason: display 문장이 약하게 연결된 claim의 theme/phrase 기준으로 교체 후보를 만듭니다.

**Current text**

```text
매칭과 서버 상태 변화에 스트레스를 크게 받는 플레이어
```

**Suggested replacement**

```text
매칭 대기나 서버 상태에 따라 체감 품질이 흔들릴 수 있는 리스크에 민감한 플레이어
```

**Phrases used**

- 스팀 계정
- 정지 당할까봐 무서워서
- 정지 당할까봐

**Decision checklist**

- 실제 evidence claim과 suggested replacement가 같은 주제를 말하는가?
- 기존 문장보다 구매 판단에 더 직접적으로 도움이 되는가?
- 같은 claim을 같은 슬롯군에 반복 사용하지 않는가?
- phrase가 리뷰 원문 잡음이 아니라 의미 있는 표현인가?

**Operator decision**: `pending`

### Holds

#### Hold 1: `str_1`

- Hold type: `evidence_mismatch_hold`
- Failure type: `evidence_mismatch`
- Claim id: `str_1`
- Reason: evidence 제목/설명과 스니펫이 어긋나 claim 자체를 신뢰하기 어렵습니다.

**Blocked text**

```text
생존 긴장감이 크다는 반응
```

#### Hold 2: `top_strengths[1]`

- Hold type: `unsupported_claim_hold`
- Failure type: `unsupported_claim`
- Claim id: `None`
- Reason: 근거 ledger에 없는 주장이라 자동으로 새 문장을 만들지 않습니다.

**Blocked text**

```text
장비와 빌드를 오래 다듬는 성장 루프 장비를 파밍하고 세팅을 맞춰 가며 강해지는 과정이 반복 임무의 동력으로 잘 이어집니다.
```

#### Hold 3: `top_strengths[3]`

- Hold type: `invalid_rewrite_source_hold`
- Failure type: `theme_drift`
- Claim id: `str_1`
- Reason: 이 claim은 같은 라운드에서 중복 제거 또는 evidence mismatch 대상이라 rewrite 근거로 재사용하지 않습니다.

**Blocked text**

```text
꾸준한 콘텐츠 업데이트와 개선 신규 무기, 맵, 모드가 지속적으로 추가되어 신선함을 유지하며 플레이어에게 다양한 재미와 도전 요소를 제공합니다.
```

## Football Manager 26 (3551340)

- QA status: `repairable_with_holds`
- Semantic status: `fail`
- Failures: `3` / critical `3`
- Report path: `data\report\report\3551340(Football Manager 26).json`

### Review-Required Actions

#### Action 1: `top_strengths[1]`

- Action: `rewrite_from_best_claim`
- Failure type: `theme_drift`
- Claim id: `str_1`
- Safety: `review_required`
- Reason: display 문장이 약하게 연결된 claim의 theme/phrase 기준으로 교체 후보를 만듭니다.

**Current text**

```text
향상된 인게임 그래픽과 모션 더욱 디테일하고 현실감 있는 선수 움직임과 경기 표현으로 경기 보는 재미가 크게 향상되었습니다.
```

**Suggested replacement**

```text
제목: 플레이 흐름이 안정적으로 잡힌
설명: 플레이 흐름이 안정적으로 잡힌다는 반응이 많아 익숙해질수록 리듬을 타기 좋은 편입니다.
```

**Phrases used**

- 그래픽이
- 전술을
- 적응하면 할만한 정도임 할인하니깐

**Decision checklist**

- 실제 evidence claim과 suggested replacement가 같은 주제를 말하는가?
- 기존 문장보다 구매 판단에 더 직접적으로 도움이 되는가?
- 같은 claim을 같은 슬롯군에 반복 사용하지 않는가?
- phrase가 리뷰 원문 잡음이 아니라 의미 있는 표현인가?

**Operator decision**: `pending`

### Holds

#### Hold 1: `top_strengths[2]`

- Hold type: `duplicate_rewrite_source_hold`
- Failure type: `theme_drift`
- Claim id: `str_1`
- Reason: 같은 claim 하나로 같은 슬롯군을 여러 번 채우면 문장이 반복되므로 자동 repair에서 제외합니다.

**Blocked text**

```text
공수 분리 전술 구현 공 소유와 미소유 상황에 따른 전술 설정이 가능해져 실제 축구 철학을 반영한 전략 구성이 가능합니다.
```

#### Hold 2: `top_strengths[3]`

- Hold type: `duplicate_rewrite_source_hold`
- Failure type: `theme_drift`
- Claim id: `str_1`
- Reason: 같은 claim 하나로 같은 슬롯군을 여러 번 채우면 문장이 반복되므로 자동 repair에서 제외합니다.

**Blocked text**

```text
전술의 깊이와 현실성 세부적인 전술 조정과 선수 역할 분담이 가능해져 축구 감독으로서의 몰입감과 전략적 재미를 느낄 수 있습니다.
```
