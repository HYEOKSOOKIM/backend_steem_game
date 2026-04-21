# Report Material Refiner Spec (Backend)

## 1. 목적

분석 결과에서 리포트 품질에 영향이 큰 subset 리뷰를 선별해 LLM 보정 대상으로 사용한다.

## 2. 적용 위치

오프라인 파이프라인에서만 실행한다.

1. Raw Ingestion
2. Deterministic Preprocess
3. Analysis Aggregation
4. Report Material Refiner
5. Report Writer
6. Report Output

## 3. 핵심 규칙

- 분석 포함 리뷰(`included_in_analysis=true`)만 대상
- 상위 근거성 리뷰 중심으로 제한된 개수만 보정
- 사용자 조회 경로에서는 실행하지 않는다.

## 4. 비기능 요구

- 입력/출력 필드 추적 가능성 보장
- 재실행 시 재현 가능한 기준 유지
