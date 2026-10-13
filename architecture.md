# Architecture

## 1. Big picture

```
Browser (HTML/CSS/JS)                   Vercel serverless function (FastAPI)                External services
Web Speech API (STT) -> final text ->   api/index.py -> routes/chat.py                      Supabase Postgres
browser speechSynthesis <- reply         request ID, logs, metrics                           Google Places / Yelp
                                           |                                                 Spoonacular / Reddit
                                           v
                                      LangGraph ordering agent
                                      rules first -> deterministic handlers
                                           | only when needed
                                           v
                                      Optional LLM service
                                      local Ollama or explicitly configured provider
```

The browser sends recognized text, not microphone audio. Ordering and dietary constraints are enforced by deterministic backend code rather than being delegated to an LLM. The optional LLM path supports local Ollama or a configured OpenAI-compatible endpoint; provider-specific free-tier availability is not guaranteed.

## 2. LangGraph agent

`START -> understand -> {add_item | remove_item | show_cart | clear_cart | recommend | show_menu | place_order | confirm | deny | set_profile | smalltalk} -> finalize -> END`

- **Understand:** deterministic parser first; optional LLM parsing is used only when rules cannot identify an intent.
- **Handlers:** cart calculations, dietary checks, recommendation scoring, and order persistence are deterministic Python.
- **Two-step ordering:** `place_order` prepares a summary and marks it pending; a separate confirmation turn is required before the order is persisted.
- **Payments:** none; cash on delivery only.
- **Database session:** passed to the graph through its configurable context.

## 3. Data and memory

| Store | Lifetime | Contents |
|---|---|---|
| `users` | Permanent | Email, name, password hash |
| `user_profiles` | Permanent, distilled | Address, diet, spice level, cuisines, frequent-item counts |
| `orders` | Permanent | Confirmed items, total, address, status |
| `session_states` | Short-lived | Cart and pending confirmation with TTL |

The full chat transcript is not stored. Persistent memory is limited to profile preferences and order data needed for the product. Session state is persisted in Postgres so cart state is not dependent solely on a single process's memory.

## 4. Authentication and configuration

1. Sign-up stores a salted PBKDF2-HMAC-SHA256 password hash.
2. Sign-in compares hashes using constant-time comparison.
3. HS256 JWTs are signed with `SECRET_KEY`; the browser stores the token in `localStorage`.
4. Protected endpoints validate the token and load the user; invalid tokens return 401.
5. In-process rate limits currently protect authentication and chat routes.

Configuration is loaded from environment variables, with `.env` used only for local development. `.env.example` is the committed template; real `.env` files and credentials must not be committed. Production must use a unique secret and environment-specific database credentials. LLM providers are disabled by default; supported options are local Ollama or a caller-configured OpenAI-compatible endpoint. Hugging Face is not used.

## 5. Database driver and serverless connections

- Local development uses SQLite; production uses Supabase Postgres.
- SQLAlchemy is pinned to 2.1. In this version, the PostgreSQL dialect uses psycopg v3 by default, and URLs with `postgresql+psycopg://` explicitly select that driver.
- `requirements.txt` therefore installs `psycopg[binary]`. The separate `psycopg2-binary` dependency remains available for compatibility with configurations that explicitly use `postgresql+psycopg2://`.
- On Vercel, the engine uses `NullPool` to avoid retaining database connections across serverless invocations; use the Supabase pooled connection string where appropriate.
- A missing DBAPI package can crash function initialization before any route responds. Regression tests initialize SQLAlchemy engines for both explicit and default PostgreSQL URL forms without requiring a live database.
- Database initialization currently creates ORM tables at application startup; a formal migration workflow remains planned.

## 6. Latency, token use, and peak traffic

- **Speech:** browser-side Web Speech API; only final text is sent to the API.
- **Rule-first processing:** routine cart/menu/order turns use deterministic handlers and avoid LLM calls.
- **Bounded LLM work:** compact prompts, bounded output tokens, timeouts, response cache, and circuit breaker.
- **Recommendations:** lightweight scoring based on popularity, prior orders, cuisine, spice, and request tags; dietary restrictions are hard filters.
- **Cache:** a thread-safe local TTL/LRU cache remains the fast first layer. When Upstash Redis REST credentials are configured, eligible public/recommendation caches are shared across instances; remote failures fall back to local memory.
- **Rate limiting:** when Upstash is configured, a Redis Lua increment-with-expiry coordinates rate limits across instances. If Redis is unavailable, the existing process-local sliding-window limiter is used.
- **Peak events:** `PEAK_MODE` extends configured cache TTLs and skips optional LLM chit-chat. Shared cache/rate limits require `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`; Redis calls are bounded by short timeouts and fail soft.
- **Serverless constraints:** do not rely on in-memory state surviving between invocations. Keep database connections and upstream calls bounded by timeouts.

## 7. External discovery

`api/services/external_apis.py` contains optional adapters for Google Places, Yelp Fusion, Spoonacular, and Reddit. `api/routes/discover.py` exposes authenticated discovery endpoints. Calls are bounded by timeouts, cached locally, and fail soft when credentials are absent or upstream services fail. Real credentials and production calls have not yet been verified. Results from external sources must be treated as recommendations, not as authoritative menu inventory or guaranteed availability.

Conversational discovery intents are routed by deterministic NLP before generic recommendations. Query cleanup removes common command wording and a trailing location, while preserving cuisine or ingredient terms where possible: restaurant queries call Google Places and Yelp concurrently, recipe queries call Spoonacular, and food-trend queries call Reddit. The integrations are optional, bounded by the existing adapter timeouts/cache, and return a graceful setup message when credentials are missing. Results are summarized in chat and are not treated as verified inventory, current opening hours, or guaranteed availability.

## 8. Monitoring

- JSON request/application logs include request IDs.
- OpenTelemetry can export traces to an OTLP-compatible endpoint or console.
- `GET /api/metrics` exposes in-process counters and latency metrics.
- Monitoring should fail soft and must not prevent ordering requests from completing.

## 9. Repository map

```
api/index.py              FastAPI app assembly and middleware
api/routes/               Auth, profile, menu, chat, discovery, system, pages
api/services/              Ordering graph, LLM, menu, profile, recommendation, sessions, external APIs
api/models/                SQLAlchemy ORM and Pydantic schemas
api/templates, api/static  HTML/CSS/JavaScript UI
api/data/menu.json         Local menu data
config/                    Environment-backed settings
database/                  Engine/session initialization
logger/                    Structured logging and telemetry
prompt_lib/                Small LLM prompts
utils/                     NLP, cache, metrics, rate limiting, security
tests/                     Automated application and LLM tests
```

## 10. Continuous integration and deployment validation

The GitHub Actions test workflow installs `requirements.txt` and `requirements-dev.txt`, then runs `pytest -q` on pushes and pull requests. Earlier implementation tests passed, and the PostgreSQL driver regression tests now ensure the configured SQLAlchemy dialect can import its DBAPI during engine creation. A green test workflow does not replace live Upstash, Vercel, Supabase, browser-microphone, or external-provider checks.

## 11. Deployment and validation status

The app is configured for Vercel and Supabase Postgres, but a configuration file alone does not prove a live deployment works. The recent Vercel 500 report was traced to `ModuleNotFoundError: No module named 'psycopg'` during database engine initialization. This commit adds the missing psycopg v3 binary dependency and regression tests. After deployment, verify `/api/health`, sign-up/sign-in, a text chat turn, cart updates, and explicit order confirmation. Live production success remains unverified until the Vercel deployment and Supabase connection are checked.
