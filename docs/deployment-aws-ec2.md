# AWS EC2 Deployment (Backend)

## 1. 목적

FastAPI 백엔드를 AWS 환경에서 안정적으로 운영하기 위한 최소 절차를 정의한다.

## 2. 기본 순서

1. EC2 인스턴스 생성
2. 보안 그룹(인바운드: 22, 80/443 또는 8000) 구성
3. 코드 배포 및 가상환경 구성
4. 의존성 설치 및 환경변수 설정
5. `uvicorn`/`systemd`로 백엔드 서비스 등록
6. 헬스체크 및 로그 모니터링

## 3. 필수 환경변수

- `BACKEND_CORS_ORIGINS`
- `OPENAI_API_KEY` (추천 fallback 사용 시)
- `OPENAI_MODEL`

## 4. 권장 운영

- 리버스 프록시(Nginx) + HTTPS
- systemd 자동 재시작
- 배포 전후 스모크 테스트

## 5. 스모크 테스트

- `GET /`
- `GET /api/health`
- `GET /api/games`
- `POST /api/recommend`
