# Progress

_Running summary so context is never lost. Last updated: 2026-10-13._

## Done
- [x] Project scaffold and folder structure (api, config, database, logger, prompt_lib, utils)
- [x] Own JWT auth: sign up, sign in, `/me`, logout; PBKDF2 hashing; rate limits
- [x] Dashboard with logout, saved address / diet / spice / cuisines
- [x] Voice UI (Web Speech STT + browser TTS) with text fallback
- [x] LangGraph ordering agent (understand -> handlers -> finalize) with two-step order confirmation
- [x] Open-source LLMs only: Qwen2.5-7B primary, Mistral-7B fallback (Hugging Face free / Ollama); rule-based fallback
- [x] Low token use (rules first, tiny prompts, caching) and low latency
- [x] Recommendation model (popularity + history + taste + tags, diet filter)
- [x] Distilled memory in Postgres (diet, frequent items); short-lived session state for the cart; no chat history stored
- [x] External API wrappers: Google Places, Yelp Fusion, Spoonacular, Reddit (dummy keys -> gracefully disabled)
- [x] Monitoring: JSON logs, OpenTelemetry traces, `/api/metrics`, `/api/health`
- [x] Peak-load measures (caching, rate limit, PEAK_MODE, pooler/NullPool)
- [x] README.md, architecture.md, `.env` with dummy keys, vercel.json
- [x] 16 automated tests passing; live server smoke test OK

## Decisions
No payments (cash on delivery) - English only - Vercel + Supabase Postgres - FastAPI + simple HTML/JS - own JWT auth -
free open-source LLMs only (Qwen/Mistral) - menu source deferred (local `menu.json` for now) - store only distilled info.

## To do / next
- [ ] Add real keys (HF token, Supabase URL, Google/Yelp/Spoonacular/Reddit) and deploy to Vercel
- [ ] Choose and plug in the online menu source (replace `menu_service._load()`)
- [ ] Use external APIs inside the agent (e.g. "restaurants near me") and show them in the dashboard
- [ ] Alembic migrations; password reset; email verification
- [ ] Redis/Upstash for global rate limiting and shared cache; Grafana dashboards for the telemetry
- [ ] Order history page and order status updates

## Notes
- Not tested here: the Vercel deployment itself, real Hugging Face / Supabase / third-party API calls (no keys, restricted network), and microphone input in a real browser.
