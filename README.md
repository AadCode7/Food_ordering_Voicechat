# BiteVoice - Voice-based Food Ordering Chatbot

Order food by talking or typing. BiteVoice builds a cart, remembers selected food preferences, recommends dishes, and places orders after explicit confirmation (cash on delivery; no payment processing).

- **Backend:** FastAPI + LangGraph + SQLAlchemy
- **Frontend:** HTML/CSS/JavaScript with browser Web Speech API for voice input and speech output
- **Database:** Supabase Postgres in production; SQLite for local development
- **Recommendations:** Lightweight profile-aware ranking with hard dietary filtering
- **Discovery integrations:** Google Places, Yelp Fusion, Spoonacular, and Reddit (optional API credentials)
- **Monitoring:** Structured logs, optional OpenTelemetry, `/api/health`, and `/api/metrics`
- **Deployment target:** Vercel

## 1. Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy the example configuration and edit it locally:

```bash
# Windows PowerShell
Copy-Item .env.example .env
# macOS/Linux
cp .env.example .env
```

Set `SECRET_KEY` to a unique random value before using real accounts. Keep `.env` private; it is ignored by Git. Do not put credentials in source files or commit them. The app can run without third-party API keys, but discovery sources that require credentials will report as unavailable.

Start the server:

```bash
uvicorn api.index:app --reload
```

Open http://localhost:8000, create an account, allow microphone access in a supported browser, or use the text input. Voice recognition runs in the browser; audio is not uploaded to the backend.

## 2. LLM configuration

The rule-based parser and ordering flow work without an LLM. For local model inference, install Ollama separately and configure `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`, and the model names in `.env`. Use `LLM_PROVIDER=none` for deterministic rule-based operation. Hosted inference providers must be configured explicitly and tested against their current model availability and usage limits before deployment; no provider's free tier is assumed to be unlimited.

## 3. Deploy on Vercel + Supabase

1. Create a Supabase project and use its pooled Postgres connection string when appropriate for serverless workloads.
2. Import this repository into Vercel.
3. Configure environment variables in Vercel Project Settings. At minimum, set a strong unique `SECRET_KEY` and production `DATABASE_URL`. Add provider credentials only for integrations you intend to enable.
4. Deploy, then verify the deployment using `/api/health`, sign-up/sign-in, a text chat turn, cart updates, and order confirmation.

Database initialization currently occurs at application startup. A formal migration workflow is still planned; review schema changes carefully before production deployment.

## 4. API overview

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/signup`, `POST /api/auth/signin`, `GET /api/auth/me` | Authentication |
| `GET/PUT /api/profile` | Saved address, diet, spice level, cuisines, and food preferences |
| `POST /api/chat` | Conversational ordering |
| `GET /api/chat/cart`, `DELETE /api/chat/session` | Cart and session |
| `GET /api/menu`, `GET /api/recommendations` | Menu and personalized recommendations |
| `GET /api/discover/places`, `/recipes`, `/buzz` | Optional external discovery sources |
| `GET /api/health`, `GET /api/metrics` | Health and metrics |

## 5. Current limitations

- The local menu is sourced from `api/data/menu.json`; a live restaurant menu/order provider is not yet connected.
- Discovery wrappers exist, but live provider calls require valid credentials and have not been verified in a deployed environment.
- Cache and rate-limit state are currently process-local, so they are not globally coordinated across serverless instances.
- Production deployment, real Supabase/provider calls, and browser microphone behavior must be tested in their target environments.

See [architecture.md](architecture.md) for design details and [progress.md](progress.md) for implementation status.
