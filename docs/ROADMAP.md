# Roadmap

Feature-level task list for Event Assistant (see `docs/PROJECT.md` for the
full product spec). Each unchecked item becomes its own `docs/current/SPEC.md`,
written via the interview workflow in `Human_guidelines.md` section 2, in a
fresh session — the same way the setup task below was spec'd.

Ordered so there's a usable, testable experience early (browsing seeded
activities) before the harder/riskier pieces (chat, scraper) are built on
top of it.

## Foundation

- [ ] Architecture setup — Next.js scaffold, tooling, CI, Supabase
      connection, Vercel deploy (`docs/current/SPEC.md`)

## Core experience

- [ ] Full data model + hand-seeded fake activities — `cities`, `sources`,
      `tags`, `activities` tables migrated, seeded with a handful of fake
      Montreal activities so later tasks have a real data shape to build
      against without depending on the scraper yet
- [ ] Activity browsing/filtering UI — city + date-range selection, tag
      filters, results grid of activity cards (the non-chat half of the
      split-view layout from `docs/PROJECT.md`)

## Chat & personalization

- [ ] Chat integration — chat sidebar UI wired to the local Qwen/MLX
      endpoint via tunnel, structured-filter tool + pgvector re-ranking,
      "assistant offline" state when the local LLM is unreachable
- [ ] Preferences — fixed tag taxonomy, save/read via chat tool-calls
      (silent-save UX) and a settings page, anonymous session cookie
- [ ] Optional login — Google OAuth via Supabase Auth, merges an
      anonymous session's preferences onto the authenticated account

## Automation

- [ ] Scraper agent — Playwright + Mistral tool-use navigating mtl.org,
      robots.txt compliance, capped request budget, LLM-based dedup on
      ingestion, `scrape_runs` logging
- [ ] Nightly scheduling — local launchd/cron trigger running the scraper
      against the cloud database

## Admin & polish

- [ ] Admin panel — single-admin auth, cities/sources CRUD, manual scrape
      trigger + run history view, activity CRUD
- [ ] Polish & hardening — no-match messaging, timezone correctness across
      the full flow, review of scraped-content prompt-injection
      mitigations, general error states
