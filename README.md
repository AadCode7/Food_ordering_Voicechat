# Voice Food Bot

A voice-first food ordering assistant. You talk to it, it understands what you want, builds your cart from a menu, recommends dishes based on your tastes, and places the order. Built with **FastAPI**, a plain **HTML/JS** frontend, **Supabase Postgres**, and deployed on **Vercel**.

> **Status: early development.** The foundation, project structure and observability are done. Auth, database, frontend, chatbot and voice are being built in small batches. See [`progress.md`](progress.md) for exactly what is finished, and [`architecture.md`](architecture.md) for the full design.

---

## Features

| Feature | Status |
|---|---|
| Health endpoint, typed config, structured logging, OpenTelemetry traces/metrics/logs | ✅ Done |
| Sign up, sign in, logout, dashboard with saved address and preferences | 🔜 Planned |
| Menu from an online source, cart, order history (no payments for now) | 🔜 Planned |
| Voice ordering chatbot (browser speech-to-text and text-to-speech, text fallback) | 🔜 Planned |
| Personalised recommendations (preferences + history + Yelp/Google/Reddit signals) | 🔜 Planned |
| Free LLMs (Mistral, Qwen) with OpenAI fallback, token-saving design | 🔜 Planned |
| Peak-load handling for events like IPL matches (caching, rate limiting, load shedding) | 🔜 Planned |

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Frontend | HTML, CSS, vanilla JavaScript (served from `public/`) |
| Database | Supabase (PostgreSQL) |
| Cache | Upstash Redis (REST) |
| Voice | Browser Web Speech API (STT) and SpeechSynthesis (TTS) |
| LLMs | Mistral → Qwen (OpenRouter) → OpenAI fallback |
| External data | Google Places, Yelp Fusion, Spoonacular, Reddit |
| Observability | OpenTelemetry → Grafana Cloud (any OTLP backend works) |
| Hosting | Vercel |

## Quick start (local)

Requirements: Python 3.12+.

```bash
# 1. Enter the project and create a virtual environment
cd voice-food-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (a .env with dummy values is already provided; see "Configuration")

# 4. Run
uvicorn api.index:app --reload
```

Then open:

- Health check: <http://localhost:8000/api/health>
- Interactive API docs (development only): <http://localhost:8000/api/docs>

Expected health response (abbreviated):

```json
{ "status": "ok", "app": "Voice Food Bot", "version": "0.1.0", "environment": "development",
  "services": { "database": true, "mistral": true, "telemetry": false, "...": "..." } }
```

> The provided `.env` contains **dummy** keys, so `services` shows `true` for things that are only *filled in*, not *working*. Replace the dummy values with real ones as you create each account.

## Configuration

All settings come from environment variables, read in one place: [`config/settings.py`](config/settings.py). Locally they come from `.env`; on Vercel you add them in **Project Settings → Environment Variables**.

| Group | Variables | Notes |
|---|---|---|
| Core | `APP_ENV`, `LOG_LEVEL`, `LOG_FORMAT`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `COOKIE_SECURE` | In production, `JWT_SECRET` must be 32+ random characters or the app refuses to start |
| Database | `DATABASE_URL` | Supabase **transaction pooler** URL (port 6543) |
| LLMs | `MISTRAL_*`, `QWEN_*`, `OPENAI_*` | Tried in this order; model names are configurable |
| External APIs | `GOOGLE_PLACES_API_KEY`, `YELP_API_KEY`, `SPOONACULAR_API_KEY`, `REDDIT_*` | Optional; features degrade when absent |
| Cache | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | |
| Telemetry | `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_TRACE_SAMPLE_RATIO`, ... | Off by default |

`.env.example` documents every variable. **Never commit `.env`**; it is git-ignored.

Generate a real secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Project structure

```
voice-food-bot/
├── api/            # Server code: entrypoint now; routes, services, models, schemas,
│                   #   middleware, templates arrive in later batches
├── config/         # Typed settings from environment variables
├── database/       # (planned) Postgres engine, repositories, schema.sql, seed scripts
├── logger/         # Structured logging + OpenTelemetry (traces, metrics, logs)
├── prompt_lib/     # (planned) Versioned LLM prompts and tool schemas
├── utils/          # (planned) Security, cache, resilience helpers
├── public/         # (planned) Frontend served by Vercel's CDN
├── tests/          # (planned) pytest suites
├── architecture.md # Design reference
├── progress.md     # Build tracker
└── requirements.txt
```

The reasoning behind every folder, the layering rules, and the request lifecycle are in [`architecture.md`](architecture.md).

## Monitoring and logging

Every request gets a `request_id` (returned in the `X-Request-ID` response header) and, when telemetry is on, a `trace_id` stamped on every log line, so one request can be followed across logs, metrics and traces.

**Locally** logs are readable one-liners:

```
09:55:23.793 INFO    foodbot.api [d26be8c06b844533] request_completed  event=http_request method=GET path=/api/docs status=200 duration_ms=0.3
```

**In production** they are JSON, one object per line, ready for Grafana Loki or Vercel's log drains. Secrets are automatically redacted and personal data (email, phone, address, voice transcripts) is never logged.

**Turn on telemetry** (traces, metrics and logs exported over OTLP):

1. Create a free Grafana Cloud stack and get its OTLP endpoint, instance ID and an access token.
2. In `.env` (and Vercel):
   ```
   OTEL_ENABLED=true
   OTEL_EXPORTER_OTLP_ENDPOINT=<OTLP base URL, without /v1/...>
   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(instanceId:token)>
   ```
3. Restart. Hit a few endpoints and explore the data in Grafana.

To see spans in your terminal without any backend, set `OTEL_ENABLED=true` and `OTEL_CONSOLE_EXPORT=true`.

Details: the metric catalogue, log fields, privacy rules and dashboard/alert suggestions are in [architecture.md §12](architecture.md).

## Deploying to Vercel

Full deployment steps arrive in the final batch. In short:

1. Push the repo to GitHub and import it in Vercel. Vercel detects FastAPI from `requirements.txt` and the `api/index.py` entrypoint.
2. Add the environment variables from `.env.example` (with real values) in the Vercel dashboard. Set `APP_ENV=production`, `COOKIE_SECURE=true`, and a strong `JWT_SECRET`.
3. Create the Supabase project, run `database/schema.sql`, and use the transaction-pooler connection string as `DATABASE_URL`.
4. Pin the function region close to the database (for example Mumbai for an India-based Supabase project).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `JWT_SECRET must be set to a random string of 32+ characters` | `APP_ENV=production` with a weak or default secret. Generate one (see above). |
| `ModuleNotFoundError: No module named 'config'` | Run commands from the project root, using `uvicorn api.index:app`. |
| Health shows `"telemetry": false` | `OTEL_ENABLED` is not `true`, or the endpoint is empty. |
| Warnings about failing OTLP exports | The telemetry endpoint or credentials are wrong or unreachable. The app keeps working; fix the values. |

## Development workflow

The project is built in batches of **five files at a time**, each explained and tested before the next. `progress.md` is updated at the end of every batch so context is never lost.
