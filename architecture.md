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

The browser sends recognized text, not microphone audio. Ordering and dietary constraints are enforced by deterministic backend code rather than being delegated to an LLM.

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

Configuration is loaded from environment variables, with `.env` used only for local development. `.env.example` is the committed template; real `.env` files and credentials must not be committed. Production must use a unique secret and environment-specific database credentials. The repository's previously tracked `.env` duplicated the placeholder template and is being removed from version control.

## 5. Latency, token use, and peak traffic

- **Speech:** browser-side Web Speech API; only final text is sent to the API.
- **Rule-first processing:** routine cart/menu/order turns use deterministic handlers and avoid LLM calls.
- **Bounded LLM work:** compact prompts, bounded output tokens, timeouts, response cache, and circuit breaker.
- **Recommendations:** lightweight scoring based on popularity, prior orders, cuisine, spice, and request tags; dietary restrictions are hard filters.
- **Cache:** the current TTL/LRU cache is thread-safe but process-local.
- **Rate limiting:** the current sliding-window limiter is process-local.
- **Peak events:** longer TTLs can be enabled using `PEAK_MODE`; this helps individual instances but does not provide a global cache or globally consistent rate limits. A shared Redis-compatible service is planned for cross-instance cache and rate-limit coordination.
- **Serverless constraints:** do not rely on in-memory state surviving between invocations. Keep database connections and upstream calls bounded by timeouts.

## 6. External discovery

`api/services/external_apis.py` contains optional adapters for Google Places, Yelp Fusion, Spoonacular, and Reddit. `api/routes/discover.py` exposes authenticated discovery endpoints. Calls are bounded by timeouts, cached locally, and fail soft when credentials are absent or upstream services fail. Real credentials and production calls have not yet been verified. Results from external sources must be treated as recommendations, not as authoritative menu inventory or guaranteed availability.

## 7. Monitoring

- JSON request/application logs include request IDs.
- OpenTelemetry can export traces to an OTLP-compatible endpoint or console.
- `GET /api/metrics` exposes in-process counters and latency metrics.
- Monitoring should fail soft and must not prevent ordering requests from completing.

## 8. Repository map

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

## 9. Deployment and validation status

The app is configured for Vercel and Supabase Postgres, but a configuration file alone does not prove a live deployment works. Validate production environment variables, database connectivity, authentication, chat/cart isolation, explicit order confirmation, and third-party APIs in the deployed environment. Schema migrations, shared cache/rate limiting, and live-provider verification remain follow-up work.
