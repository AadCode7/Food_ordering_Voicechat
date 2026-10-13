# Architecture

## 1. Big picture
```
Browser (HTML/JS)                          Vercel serverless function (FastAPI)                 External
 mic -> Web Speech API (STT, streaming)      api/index.py  (middleware: request id, logs, metrics)
 text  ---- POST /api/chat (JWT) ---------->  routes/chat.py
 speaker <- speechSynthesis (TTS)               |  load short-lived session  --------------->  Supabase Postgres
                                                |  load profile (cached 30 s) -------------->  (users, profiles,
                                                v                                              orders, session_states)
                                         LangGraph agent  (services/ordering_graph.py)
                                          understand -> handler -> finalize
                                                |  only if rules fail
                                                v
                                         llm_service -> Qwen2.5-7B (primary) -> Mistral-7B (fallback)
                                                              via Hugging Face / Ollama (open source only)
                                         external_apis -> Google Places, Yelp, Spoonacular, Reddit (cached)
```

## 2. LangGraph agent
`START -> understand -> {add_item | remove_item | show_cart | clear_cart | recommend | show_menu | place_order | confirm | deny | set_profile | smalltalk} -> finalize -> END`

* **understand**: rule parser (`utils/nlp.py`) first. If it cannot identify the intent or any known dish, it asks the LLM for a compact JSON `{intent, items, tags}`. Still unknown -> `chitchat`.
* **handlers**: deterministic Python (cart maths, diet checks, recommender, order insert). Replies are templates, so normal turns use **zero LLM tokens**.
* **two-step ordering**: `place_order` prepares a summary and sets `pending_confirm`; only a later `yes` writes the order. No payments (cash on delivery).
* Dependencies (DB session) are passed through LangGraph's `config["configurable"]`; state is a `TypedDict`.

## 3. Data & memory
| Store | Lifetime | Contents |
|---|---|---|
| `users` | permanent | email, name, PBKDF2 password hash |
| `user_profiles` | permanent, **distilled** | address, diet (veg/non-veg/any), spice level, cuisines, `frequent_items` counts |
| `orders` | permanent | items, total, address, status |
| `session_states` | **short-lived** (`SESSION_TTL_MINUTES`) | cart + pending confirmation only |

The full chat transcript is **never stored**. Only distilled facts (diet, frequent items) are written to Postgres, after an order is confirmed or when the user states a preference.

## 4. Authentication (own JWT)
1. Sign up: validate input -> PBKDF2-HMAC-SHA256 (210k iterations, random 16-byte salt) -> store `pbkdf2_sha256$iters$salt$hash`.
2. Sign in: recompute and compare with `hmac.compare_digest` (constant time); same error for wrong email or password.
3. Issue an HS256 JWT (`sub`, `iat`, `exp`) signed with `SECRET_KEY`. The browser keeps it in `localStorage` and sends `Authorization: Bearer ...`.
4. `get_current_user` verifies signature + expiry and loads the user; invalid -> 401. Logout deletes the token client-side and the cart session server-side.
5. Per-IP limits on auth endpoints, per-user limits on chat.

## 5. Latency, tokens and load
* **STT**: browser Web Speech API streams partial results and sends only the final text (no audio upload, no STT server cost). TTS also in the browser.
* **Latency**: rules answer in a few ms; one DB read/write per turn; profile and recommendations cached; LLM timeout 12 s with a circuit breaker (3 failures -> pause 60 s).
* **Token use**: prompts are ~80 tokens, `max_tokens` 80-120, no history sent, no menu sent (dishes are fuzzy-matched locally), LLM answers cached 10 min.
* **Peak events (IPL)**: stateless functions scale horizontally; Supabase pooler (6543) with `NullPool`; TTL caches; rate limiting; `PEAK_MODE` extends caches and disables optional LLM chit-chat. Caches and limiters are per instance - use Redis/Upstash if you need global limits.
* **Recommender**: score = popularity + personal frequency + cuisine match + spice fit (+ request tags), hard diet filter. Pure Python.

## 6. Monitoring (telemetry)
* `logger/setup.py`: one JSON line per event with `request_id` and `trace_id`.
* `logger/telemetry.py`: OpenTelemetry tracer (FastAPI auto-instrumentation + custom spans for each graph node, LLM call and external API). Export to console (`OTEL_CONSOLE=true`) or any OTLP endpoint (Grafana Tempo / Grafana Cloud, Jaeger) via `OTEL_EXPORTER_OTLP_ENDPOINT`.
* `utils/metrics.py` + `GET /api/metrics`: counters (intents, LLM vs rule, orders, cache hits/misses, HTTP codes) and latency stats.
* Everything fails soft: monitoring can never break a request.

## 7. Folder map
```
api/index.py            app assembly, middleware, startup
api/routes/             auth, profile, menu, chat, discover, system, pages, deps
api/services/           ordering_graph (LangGraph), llm_service, menu/profile/recommend/session/auth, external_apis
api/models/             orm.py (tables), schemas.py (pydantic)
api/templates, static   login + dashboard UI
api/data/menu.json      menu (pluggable source)
config/ database/ logger/ prompt_lib/ utils/    settings, engine, logging+telemetry, prompts, nlp/cache/security/limits
tests/                  16 tests (auth, flow, diet safety, LLM fallbacks, isolation)
```
