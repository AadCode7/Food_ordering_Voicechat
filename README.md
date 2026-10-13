# BiteVoice - Voice based Food Ordering Chatbot

Order food by talking. Sign up, sign in, speak or type what you want, and the agent builds your cart,
remembers your diet/address/taste, recommends dishes and places the order (cash on delivery for now).

* **Backend:** FastAPI + LangGraph agent, own JWT auth, SQLAlchemy
* **LLMs:** open-source and free only - **Qwen2.5-7B-Instruct** (primary) and **Mistral-7B-Instruct** (fallback)
  via Hugging Face free inference or locally with Ollama. No OpenAI / proprietary model anywhere.
* **Database:** Supabase Postgres in production, SQLite locally
* **Frontend:** simple HTML/CSS/JS. Voice input uses the browser Web Speech API (free, streaming, low latency)
* **Monitoring:** structured JSON logs + OpenTelemetry traces + `/api/metrics`
* **Deploy:** Vercel

## 1. Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.index:app --reload
```
Open http://localhost:8000, create an account, allow the microphone (Chrome/Edge) and say
*"add two butter naan and a paneer tikka"*. `.env` already holds dummy keys; the app runs without any
real key (rule-based understanding). Add real keys later to switch features on.

Tests (no network needed): `pip install -r requirements-dev.txt && pytest -q`

## 2. Turn on the open-source LLM (optional, free)

| Option | Setup |
|---|---|
| **Hugging Face (works on Vercel)** | Create a free token at huggingface.co/settings/tokens, set `LLM_PROVIDER=hf` and `HF_TOKEN=hf_...` |
| **Ollama (local, fully offline)** | `ollama pull qwen2.5:7b-instruct && ollama pull mistral:7b-instruct`, then set `LLM_PROVIDER=ollama`, `LLM_MODEL_PRIMARY=qwen2.5:7b-instruct`, `LLM_MODEL_FALLBACK=mistral:7b-instruct` |
| **None** | `LLM_PROVIDER=none` - everything still works with the rule engine |

Free tiers have rate limits. If a model fails the app tries the fallback model, then falls back to rules.

## 3. Deploy on Vercel + Supabase

1. Supabase: create a project and copy the **Transaction pooler** connection string (port 6543).
2. Push this folder to GitHub, import it in Vercel (framework: Other).
3. Add the variables from `.env` in Vercel -> Settings -> Environment Variables. At minimum:
   `SECRET_KEY` (long random string), `DATABASE_URL` (Supabase, with `?sslmode=require`), `LLM_PROVIDER`, `HF_TOKEN`.
4. Deploy. `vercel.json` routes everything to `api/index.py`. Tables are created automatically on first start.

## 4. API overview (`/docs` has the interactive version)

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/signup`, `POST /api/auth/signin`, `GET /api/auth/me` | JWT auth |
| `GET/PUT /api/profile` | address, diet, spice level, cuisines, frequent items |
| `POST /api/chat` | one conversational turn (LangGraph agent) |
| `GET /api/chat/cart`, `DELETE /api/chat/session` | read / clear the short-lived cart |
| `GET /api/menu`, `GET /api/recommendations` | menu and personalised picks |
| `GET /api/discover/places`, `/recipes`, `/buzz` | Google Places + Yelp, Spoonacular, Reddit |
| `GET /api/health`, `GET /api/metrics` | monitoring |

## 5. Things you can say

"add two butter naan" - "remove the naan" - "show my cart" - "recommend something spicy" - "what desserts do you have" -
"I'm vegetarian" - "deliver to 14 Gandhi Road" - "place my order" - "yes".

## 6. Configuration notes

* `PEAK_MODE=true` before big events (e.g. IPL): caches live 3x longer and chit-chat LLM calls are skipped.
* Placeholder keys (starting with `dummy`) are treated as "not configured"; nothing is called.
* Menu source: currently `api/data/menu.json`. Swap `menu_service._load()` for an online source later.
* Folder layout: `api/` (models, routes, services, static, templates, data), `config/`, `database/`, `logger/`, `prompt_lib/`, `utils/`, `tests/`.
