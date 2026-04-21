# Backend Quality Gates

## 1. 목적

오프라인 분석/리포트 산출물의 품질을 정량 점검한다.

## 2. Normalization Gate

- 핵심 기준
  - `included_drop_rate <= 0.10`
  - `unc_ratio_delta < 0`
- 실패 시 rollback 또는 규칙 재보강

## 3. Report Release Gate

- 4점 체크
  1. 핵심 결론 존재
  2. 적합성 정보 존재
  3. 강점/리스크 근거 존재
  4. 금지 라벨 노출 0
- 보조 지표
  - `evidence_mismatch_rate`
  - `unknown_snippet_rate`

## 4. Benchmark 운영 원칙

- 동일 코호트 반복 측정
- 변경 전/후 지표 비교
- 자동화는 탐지/요약까지만, 최종 판단은 사람 검토

## 5. 파일명 정책

저장 파일명은 appid+게임명 형식으로 관리한다.

- `raw/{appid}({game_name_ko}).json`
- `processed/{appid}({game_name_ko}).json`
- `analysis/{appid}({game_name_ko}).json`
- `metadata/{appid}({game_name_ko}).json`

API 조회 기준은 항상 `appid`이다.
