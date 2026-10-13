# Progress

_Running summary so context can be carried forward. Last updated: 2026-10-13._

## Existing functionality reviewed

- [x] FastAPI application and Vercel routing configuration reviewed
- [x] Existing auth, chat/order graph, menu, recommendation, session, and discovery services reviewed
- [x] Existing discovery adapters identified for Google Places, Yelp Fusion, Spoonacular, and Reddit
- [x] Existing local TTL cache and sliding-window limiter identified as process-local
- [x] Existing architecture and limitations documented

## Completed in this branch

- [x] Created feature branch `feature/production-hardening-and-discovery` from `main`
- [x] Tightened Git ignore rules so local environment files are not newly committed, while keeping `.env.example` tracked
- [x] Updated setup instructions to copy `.env.example` to a local `.env` and keep credentials out of source control
- [x] Removed the tracked `.env` file because it duplicated the placeholder template; configure local and deployed secrets through environment variables
- [x] Updated architecture documentation to distinguish existing capabilities from planned work and unverified deployment behavior
- [x] Updated this progress file alongside the implementation documentation

## Decisions

- Existing repository remains the project source; changes are isolated on a feature branch to protect the current `main`.
- Keep FastAPI + simple HTML/CSS/JS + Supabase Postgres + Vercel as the target stack.
- Preserve deterministic ordering, hard dietary filtering, and explicit order confirmation.
- Keep LLM calls optional and bounded; do not assume a hosted provider's free tier is unlimited.
- Store distilled user preferences and order data, not full chat transcripts.
- Treat third-party discovery results as recommendations, not confirmed menus or availability.

## Next implementation steps

- [ ] Add an optional shared Redis-compatible cache and distributed rate limiter with a safe local fallback
- [x] Route conversational restaurant, recipe, and food-discussion requests to the existing Google Places, Yelp, Spoonacular, and Reddit adapters
- [x] Run Google Places and Yelp lookups concurrently; deduplicate restaurant names and gracefully handle missing provider credentials
- [x] Add parser and mocked chat-flow tests for the three discovery intents
- [ ] Verify live external-provider calls and tune query extraction using real examples
- [ ] Review LLM provider configuration and remove dependence on providers whose free access is unreliable
- [ ] Add tests for provider failures, cache fallback, cross-user/session isolation, and discovery behavior
- [ ] Add a database migration workflow and production configuration validation
- [ ] Run the automated test suite and verify the deployed Vercel + Supabase setup

## Validation status

- The codebase was inspected and changes were committed through GitHub.
- Discovery parser and chat-flow tests were added, but automated tests have **not** been executed in this work session; do not interpret test definitions as passing results.
- Live Vercel deployment, Supabase connectivity, real third-party API calls, and browser microphone behavior have not been verified here.
