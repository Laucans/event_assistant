# Spec: Initial architecture setup

## Problem

Before any feature work starts, the project needs a working, deployed
skeleton: a Next.js app with tooling, a real (if mostly empty) database it
can talk to, and a CI/deploy pipeline — so every subsequent feature task
(chat, scraping, admin panel, etc., per `docs/PROJECT.md`) builds on a
proven foundation instead of also having to stand up plumbing.

## Goals / Non-goals

**Goals**

- Next.js (TypeScript, App Router) app scaffolded with npm, Tailwind CSS +
  shadcn/ui, ESLint + Prettier, and Vitest wired to `npm test`.
- Git repo initialized locally and pushed to a new GitHub repo.
- GitHub Actions CI running lint, typecheck, build, and test on push/PR.
- Supabase account + project created (walkthrough, since neither exists
  yet), Postgres connection wired into the app via env vars.
- Minimal schema: a `cities` table, migrated and seeded with a Montreal
  row — just enough to prove the app can read from the DB.
- Vercel account + project created (walkthrough), connected to the GitHub
  repo, deployed with a page that server-fetches and renders the seeded
  Montreal row from Supabase — proving the full pipe end to end.
- `CLAUDE.md` updated with the real install/dev/test/lint commands, and
  `README.md`'s getting-started section filled in, replacing the current
  TBD placeholders.

**Non-goals**

- Any real product feature (chat, scraping, admin panel, activity
  browsing/filtering UI).
- The rest of the schema from `docs/ARCHITECTURE.md` (`sources`, `tags`,
  `activities`, `users`, `sessions`, `preferences`, `scrape_runs`) — each
  gets created in the feature task that actually needs it.
- Auth (Google OAuth / Supabase Auth) — explicitly deferred to its own
  later task, even though `users`/`sessions` will eventually depend on it.
- Local LLM tunnel (Cloudflare Tunnel to the Qwen/MLX endpoint) or the
  Mistral scraper integration — not needed until their respective feature
  tasks.

## Approach

1. Scaffold the Next.js app (App Router, TypeScript) with npm at the repo
   root, fitting around the existing `src/`, `tests/`, `docs/` layout.
2. Install and configure Tailwind CSS + shadcn/ui.
3. Configure ESLint + Prettier using Next.js's default setup.
4. Configure Vitest with an `npm test` script and one trivial smoke test,
   proving the runner works (no real feature logic to test yet).
5. `git init`, initial commit, create a GitHub repo via `gh repo create`
   (confirm `gh auth status` first), push.
6. Add a GitHub Actions workflow (`.github/workflows/ci.yml`) that runs
   install, lint, typecheck, build, and test on every push/PR.
7. Walk through creating a Supabase account and project; store the
   connection string/keys in `.env.local` (gitignored) and document the
   required variables in a committed `.env.example`.
8. Add a minimal migration creating `cities` (id, name, slug, timezone,
   country, active) and seed it with one Montreal row.
9. Wire a Postgres/Supabase client into the app; add a page (e.g. `/`)
   that server-fetches and renders the seeded city row.
10. Walk through creating a Vercel account and project, connect it to the
    GitHub repo, add the Supabase env vars to the Vercel project, deploy.
11. Update `CLAUDE.md` (real commands, replacing every `TBD`) and
    `README.md` (getting-started steps) to match what was actually set up.

# Tasks

**1. Repo & app scaffold**

- `git init`, verify `.gitignore` already excludes `node_modules` and
  `.env.local` _before_ the first commit.
- Scaffold Next.js (TS, App Router) with npm, fitting around the
  existing `src/`, `tests/`, `docs/` layout.
- Install/configure Tailwind CSS + shadcn/ui, ESLint + Prettier
  (Next.js defaults), Vitest wired to `npm test` with one smoke test.
- Verify: `npm run dev` boots, `npm run lint` / `npm run build` /
  `npm test` all pass locally.

**2. GitHub repo & CI** _(needs you: `gh auth login` first — human-only,
can't be scripted)_

- You run `gh auth login` interactively.
- Claude: initial commit, `gh repo create`, push, add
  `.github/workflows/ci.yml` (install, lint, typecheck, build, test on
  push/PR).
- Verify: don't just trust the YAML — check the Actions tab and confirm
  the workflow actually ran green; SPEC.md's edge cases call out
  verifying it _fails_ appropriately too (e.g. temporarily break lint,
  confirm red, revert).

**3. Supabase account & connection** _(needs you: account/project creation
in-browser — human-only)_

- Claude walks you through creating the Supabase account/project and
  grabbing the connection string/keys.
- Claude: add keys to `.env.local` (gitignored), document required vars
  in a committed `.env.example`.
- Verify: a trivial local script or `psql`/Supabase client call
  confirms the app can actually reach the DB.

**4. Schema, seed & first DB-backed page**

- Migration creating `cities` (id, name, slug, timezone, country,
  active); seed one Montreal row.
- Postgres/Supabase client in `src/lib/db/`; a page (`/`) that
  server-fetches and renders the seeded row.
- Verify: `npm run dev` → homepage shows the Montreal row, sourced from
  the DB (not hardcoded).

**5. Vercel deploy** _(needs you: account/project creation in-browser —
human-only)_

- Claude walks you through creating the Vercel account/project,
  connecting it to the GitHub repo, and adding the Supabase env vars to
  the _Vercel_ project (not just local).
- Verify: load the actual deployed URL and confirm it renders the same
  Montreal row — SPEC.md is explicit that a green build alone doesn't
  prove this; the env vars are a common miss.

**6. Docs cleanup**

- Update `CLAUDE.md` with the real install/dev/test/lint commands
  (replacing every `TBD`), and fill in `README.md`'s getting-started
  section.
- Small enough to skip planning for, per `Human_guidelines.md` §1.

**7. Adversarial review (before calling it done)**

- Run `/code-review` (or a fresh subagent) against the full diff with
  SPEC.md as the checklist: every goal implemented, `.env.local` never
  committed, no secrets in the diff, CI genuinely catches failures.
- Manually flip `docs/ROADMAP.md`'s checkbox context if needed, so just confirm it still reads correctly
  once this work is real.

## Files & interfaces touched

- Next.js scaffold: `package.json`, `next.config.*`, `tsconfig.json`,
  `tailwind.config.*`, `app/` routes.
- `eslint.config.*`, `.prettierrc`.
- `vitest.config.ts` + one smoke test.
- `.github/workflows/ci.yml`.
- `.env.example` (committed), `.env.local` (gitignored — verify
  `.gitignore` already covers it and `node_modules`).
- `db/migrations/` (or equivalent) — initial `cities` migration + seed.
- `src/lib/db/` — Postgres/Supabase client.
- `CLAUDE.md`, `README.md` — updated with real commands and setup steps.

## Edge cases

- `.gitignore` must already exclude `.env.local` and `node_modules` —
  verify before the first commit so no secrets or dependencies get
  committed.
- `gh repo create` must not be attempted while unauthenticated — check
  `gh auth status` first and stop to ask if it fails, rather than working
  around it.
- CI should be proven to actually catch failures, not just pass by
  default — verify the workflow runs (and fails appropriately) at least
  once, e.g. by checking the Actions run rather than assuming config is
  correct.
- The Vercel deploy needs the Supabase env vars set in the Vercel
  project (not just locally), or the deployed page will fail to fetch —
  confirm by checking the deployed URL itself, not just a green build.

## Out of scope

- Any product feature from `docs/PROJECT.md`.
- Full DB schema beyond `cities`.
- Auth / OAuth.
- Local LLM tunnel and Mistral scraper integration.

## Verification

- `npm run dev` boots locally and the homepage renders the seeded
  Montreal row fetched from Supabase.
- `npm run lint`, `npm run build`, and `npm test` all pass locally.
- The GitHub Actions workflow runs green on the initial push/PR.
- The Vercel-deployed URL renders the same seeded Montreal row, confirming
  the full local → GitHub → Vercel → Supabase pipe works end to end.
