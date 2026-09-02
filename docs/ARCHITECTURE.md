# Architecture: Event Assistant

Technical decisions for Event Assistant. For product intent — what this is
for, who it serves, and what's deliberately out of scope — see
`docs/PROJECT.md`.

This is a personal/portfolio project: optimize for simplicity, low running
cost, and fast iteration over scale or multi-tenant robustness.

## Stack

- **App**: single Next.js (TypeScript, App Router) app deployed on Vercel,
  covering the public site, the chat API, and the admin panel (auth-gated
  routes). Package manager is npm; routes live in `src/app/`.
- **Database**: managed Postgres with the `pgvector` extension (Supabase
  recommended — bundles Postgres + pgvector + Auth, reducing moving parts).
  Reachable from both the cloud app and the local scraper script.
- **Chat LLM**: user's local Qwen model, served via an existing
  OpenAI-compatible endpoint (MLX). The cloud-hosted site reaches it
  through a persistent tunnel (Cloudflare Tunnel) to a stable URL, kept in
  an env var (`LOCAL_LLM_BASE_URL`). No inference cost.
- **Scraper agent LLM**: a separate, more capable paid model (Mistral API)
  used only for the nightly scrape — chosen over the local model because
  page navigation/extraction benefits from stronger reasoning, and it's
  decoupled from per-user chat cost since it runs once a night regardless
  of traffic.
- **Scraper runtime**: a Node/TS script using Playwright (headless browser)
  for navigation, with the LLM driving tool-use calls (click, scroll,
  read text, extract structured data) to figure out how to pull activities
  off a page it hasn't seen a fixed selector for. Scheduled via the user's
  local `launchd`/cron, writing directly to the cloud Postgres DB.
- **Styling**: Tailwind v4 (CSS-first `@theme` in `globals.css` — there is
  no `tailwind.config.js`) + shadcn/ui.
- **Tests & tooling**: Vitest; ESLint + Prettier, with Prettier owning
  formatting.

## Data model

- `cities` — id, name, slug, timezone, country, active.
- `sources` — id, city_id, name, base_url, status (active/paused),
  last_run_at.
- `tags` — id, label, slug (seeded fixed taxonomy, e.g. outdoor, indoor,
  live-music, museum-art, food-drink, family-friendly, nightlife, sports,
  free-budget, festival).
- `activities` — id, city_id, source_id, title, description, tags[]
  (join table `activity_tags`), start_date, end_date (nullable — supports
  both single-day and multi-day/recurring listings), venue_name, address,
  price_range, source_url, embedding (vector, for semantic re-ranking),
  created_at, updated_at.
- `users` — id, email, created_at (populated on optional Google OAuth
  login).
- `sessions` — id (random token stored in an httpOnly cookie), created_at,
  user_id (nullable — set once a session logs in, to merge history).
- `preferences` — id, session_id or user_id, tag_id, created_at.
- `scrape_runs` — id, source_id, started_at, finished_at, status
  (success/failed/skipped), activities_found, activities_inserted, error.

All timestamps stored in UTC; each city carries its own timezone for
display and for resolving "today"/date-range queries.

## Chat request flow

1. Resolve identity: read the session cookie (create one if absent) or the
   authenticated user.
2. On each message, the chat LLM has tool access to:
   - **query activities** — structured filter by city + date range + tags,
     then pgvector similarity re-rank against the conversation's
     intent/saved preferences;
   - **save a preference** — called when the model infers a durable like/
     dislike from what the user said, mapped to the fixed tag taxonomy.
     Preferences are saved silently; the reply just acknowledges it in
     passing (no separate confirmation step).
3. Matching activities render as cards in the main grid, which updates
   from the latest filter/recommendation state.
4. No matches: return a plain "no activities found for these filters"
   message — no automatic broadening.
5. If the local LLM endpoint is unreachable (tunnel/machine down), the
   chat panel shows a clear "assistant offline" state; the grid still
   works since it's driven by structured queries against Postgres, not
   the LLM. Don't couple grid rendering to chat.

## Preferences storage

- `preferences` rows are keyed by `session_id` or `user_id`, so an
  anonymous visitor accumulates preferences against their session cookie.
- The settings page and the conversational path (e.g. "forget that I like
  nightlife") go through the same save/remove tool the recommendation flow
  uses — one code path, two entry points.
- On login, any preferences attached to the current anonymous session are
  merged onto the authenticated user's record.

## Scraper agent flow

1. Nightly trigger (local launchd/cron) runs the scraper script.
2. For each active source: fetch and check `robots.txt` — if the target
   path is disallowed, skip the source and mark the run `skipped` with a
   reason, visible in admin.
3. Playwright opens the source's listing page(s); the LLM (Mistral, via
   tool-use) navigates and extracts candidate activities as structured
   data, within a hard-capped request/page budget per source per night
   (keeps cost predictable — one source, mtl.org, at launch).
4. For each candidate: the LLM compares it against existing activities in
   the same city with overlapping dates and judges duplicate vs. new
   (LLM-based dedup, not a rigid key match) — duplicates are skipped or
   used to refresh fields (e.g. updated price) on the existing row.
5. New/updated activities are upserted, each getting an embedding computed
   for semantic search.
6. A `scrape_runs` row records status, counts, and any error for the
   admin panel to display.

**Security note**: scraped page content is untrusted input reaching an
LLM's context (indirect prompt-injection risk — a page could contain text
crafted to redirect the scraping agent). Mitigation: treat all extracted
page text strictly as data to parse, never as instructions; keep the
agent's system/tool-use instructions fixed and out of band from page
content; cap how much raw page text is ever passed back into a single
tool-result.

## Admin panel implementation

- Single-admin auth via one env-configured credential — no roles or
  permissions system for v1.
- Admin lives on auth-gated routes within the same Next.js app.
- Backs four capabilities: cities CRUD (name, slug, timezone, active);
  sources CRUD (name, base_url, city, active/paused); scrape-run history
  per source plus an on-demand manual trigger; and activity CRUD for
  corrections, independent of the scraper.

## Repo layout & interfaces

This is a greenfield build; representative structure (exact layout decided
at implementation time):

- `src/app/` — Next.js routes: public site (`/`), chat API (`/api/chat`),
  preferences API (`/api/preferences`), admin (`/admin/**`, auth-gated).
- `src/lib/db/` — Postgres client + schema/migrations (cities, sources,
  tags, activities, users, sessions, preferences, scrape_runs).
- `src/lib/llm/` — local-LLM client (chat) and Mistral client (scraper),
  kept as separate thin wrappers behind a common interface.
- `scraper/` — standalone Node/TS script (Playwright + Mistral tool-use),
  run via local launchd/cron, connects to the same cloud Postgres DB.
- `docs/PROJECT.md` — product vision.
- `docs/ARCHITECTURE.md` — this document.

## Technical edge cases

- **Duplicate/near-duplicate activities** (same event across re-scrapes or
  listed twice): handled by LLM-based dedup during ingestion.
- **robots.txt disallows a needed path**: source is skipped for that run,
  flagged in the admin scrape-run history rather than silently failing.
- **Indirect prompt injection from scraped content**: see the Security
  note under Scraper agent flow.
- **Timezone handling**: all storage in UTC; each city record carries its
  timezone for resolving "today" and displaying dates correctly.
- **Multi-day/recurring activities**: modeled via nullable `end_date` on
  `activities`, matched against any overlap with the user's requested
  date range.
- **Local LLM/tunnel unreachable**: the grid stays functional because it
  queries Postgres directly; only the chat panel depends on the LLM.

## Verification

- **Local dev**: run the Next.js app locally against the Supabase DB and
  the local LLM endpoint directly (no tunnel needed in dev); confirm chat
  round-trip returns a reply and, when relevant, activity cards.
- **Scraper**: manually run the scraper script against `mtl.org`; confirm
  a `scrape_runs` row is created, new activities appear in `activities`
  with tags and an embedding, and re-running it doesn't create duplicates.
- **Preferences**: in a chat conversation, state a preference; confirm it
  appears in the settings page; remove it there and confirm subsequent
  recommendations stop weighting it; confirm it appears removable via chat
  too.
- **Offline fallback**: stop the local LLM/tunnel; confirm the chat panel
  shows the offline state while the activity grid still filters correctly.
- **Admin**: log in as the single admin; add a second (test) source, edit
  an activity, trigger a manual scrape run, and confirm run history
  updates.
- **robots.txt**: point a test source at a path disallowed by its
  robots.txt; confirm the scraper skips it and the run is marked
  accordingly instead of erroring.
