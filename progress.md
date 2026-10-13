# Progress

_Running summary so context can be carried forward. Last updated: 2026-10-13._

## Existing functionality reviewed

- [x] FastAPI application and Vercel routing configuration reviewed
- [x] Existing auth, chat/order graph, menu, recommendation, session, and discovery services reviewed
- [x] Existing discovery adapters identified for Google Places, Yelp Fusion, Spoonacular, and Reddit
- [x] Existing local TTL cache and sliding-window limiter identified as process-local
- [x] Existing architecture and limitations documented

## Completed on main

- [x] Hardened Git ignore rules so local environment files are not newly committed, while keeping `.env.example`
- [x] Removed the tracked `.env` file; local and deployed secrets are configured through environment variables
- [x] Added an optional Upstash Redis REST cache layer for eligible public/external and recommendation data, with local TTL fallback
- [x] Added Redis-backed distributed rate limiting with local fallback
- [x] Routed conversational restaurant, recipe, and food-discussion requests to Google Places, Yelp, Spoonacular, and Reddit adapters
- [x] Added mocked discovery/LLM/cache/rate-limit tests and GitHub Actions CI
- [x] Removed Hugging Face from the configured LLM path; rule-based operation remains the default
- [x] Fixed the PostgreSQL driver dependency for SQLAlchemy 2.1 by adding the psycopg v3 binary distribution used by the configured PostgreSQL dialect
- [x] Added regression tests to verify both explicit `postgresql+psycopg://` and default `postgresql://` URLs can initialize a SQLAlchemy engine
- [x] Updated architecture and progress documentation with the deployment incident and fix

## Decisions

- Work directly on `main`; do not create feature branches unless explicitly requested.
- Keep FastAPI + simple HTML/CSS/JS + Supabase Postgres + Vercel as the target stack.
- Preserve deterministic ordering, hard dietary filtering, and explicit order confirmation.
- Keep LLM calls optional and bounded; do not assume a hosted provider's free tier is unlimited.
- Store distilled user preferences and order data, not full chat transcripts.
- Treat third-party discovery results as recommendations, not confirmed menus or availability.
- Use psycopg v3 because the deployed SQLAlchemy PostgreSQL dialect imports `psycopg`; keep psycopg2-binary available for compatibility with any explicit psycopg2 URL.

## Next implementation steps

- [ ] Verify the new dependency and regression tests in GitHub Actions after this commit
- [ ] Verify the Vercel deployment starts successfully after redeployment
- [ ] Verify production Supabase connectivity and authentication/chat/order flows
- [ ] Verify shared-cache and distributed-limit behavior against a real Upstash database
- [ ] Verify live external-provider calls and tune query extraction using real examples
- [ ] Verify local Ollama and a chosen OpenAI-compatible provider against configured model IDs
- [ ] Add tests for provider failures, cross-user/session isolation, and discovery behavior
- [ ] Add a database migration workflow and production configuration validation

## Validation status

- GitHub Actions previously completed `pytest -q` successfully on implementation commit `c45eb06c7bd86201ae1c081578904ae5939f9684`.
- The production error reported from Vercel was `ModuleNotFoundError: No module named 'psycopg'` while SQLAlchemy initialized the PostgreSQL engine.
- This change adds `psycopg[binary]` and regression coverage for SQLAlchemy engine initialization. A successful GitHub test run and live Vercel redeployment still need confirmation.
- Live Upstash Redis, Vercel deployment, Supabase connectivity, real third-party API calls, and browser microphone behavior have not been verified here.
