# LabMate AI Backend

FastAPI service that powers the Dr. Ada AI Tutor and RBAC/audit endpoints for **LabMate AI** — an interactive lab instrument training platform built for the **Build with MeDo Hackathon 2026**.

This service is registered as a MeDo Custom Plugin and called by the MeDo-generated frontend.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Healthcheck |
| POST | `/tutor/chat` | Dr. Ada chat (via OpenRouter) |
| POST | `/auth/verify` | RBAC role check |
| GET | `/users/{user_id}/progress` | Fetch user progress |
| POST | `/progress/update` | Update user progress |
| GET | `/audit/{user_id}` | Fetch user audit log |
| POST | `/audit/log` | Append audit event |

All endpoints except `/`, `/health`, `/docs` require an `X-API-Secret` header.

## Local development

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your OpenRouter key
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive Swagger UI.

## Deploy to Render

1. Push this repo to GitHub.
2. Go to https://render.com → New → Web Service → connect your GitHub repo.
3. Render auto-detects `render.yaml`. Confirm settings.
4. Set the two secret env vars:
   - `OPENROUTER_API_KEY` — your key from https://openrouter.ai/keys
   - `API_SECRET` — any random string; this same string goes in the MeDo plugin config
5. Click Create. First deploy takes ~3 min.
6. Note your public URL (e.g. `https://labmate-backend.onrender.com`).

## Register as a MeDo Custom Plugin

Use the plugin spec in `MEDO_PLUGIN_SPEC.md`.

## Notes

- In-memory storage is used for progress and audit. For production, swap in a real DB.
- CORS is wide open (`*`) for the hackathon. Lock down in production.
- Llama 3.3 70B on OpenRouter's free tier has rate limits — fine for judging, not for scale.
