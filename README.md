# steam-insights-backend

Backend API service for report and recommender modules.

## Run (local)

```powershell
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

## Environment

Copy `.env.example` to `.env` and set values:

- `BACKEND_CORS_ORIGINS`: comma-separated frontend origins
- `OPENAI_API_KEY`: required for recommender LLM fallback
- `OPENAI_MODEL`: optional, default is `gpt-4o-mini`

## Deployment note (AWS)

- Backend should be deployed independently (EC2/ECS/Lambda).
- Set `BACKEND_CORS_ORIGINS` to your Vercel frontend URL(s).
