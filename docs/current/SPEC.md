# Spec: Supabase account & connection

## Problem

This is task 3 of the "Initial architecture setup" milestone
(`docs/current/CURRENT_MILESTONE.md`): _"Claude walks you through creating the
Supabase account/project and grabbing the connection string/keys; add keys to
`.env.local`, document required vars in `.env.example`; verify a trivial local
script or Supabase client call confirms the app can actually reach the DB."_

What was verified as actually true before writing this spec:

- Tasks 1 and 2 are genuinely done. The repo is on GitHub
  (`Laucans/event_assistant`), `ci` runs green on push/PR, `main` carries an
  active ruleset requiring a PR and the `ci` check, and a local hook blocks
  `git push origin main`.
- **No database dependency is installed at all** — `@supabase/supabase-js`,
  `pg` and `postgres` are all absent from `package.json`, and `src/lib/db/`
  does not exist.
- The Supabase CLI is **not** installed. `psql` is **not** installed. Docker
  29.4.0 and Deno 2.8 are present but neither is needed here.
- Node is `v24.16.0`, npm `11.13.0`. Node 24 strips TypeScript natively with
  no flag and no `tsx` dependency — **verified by running a `.ts` file**.
- `.env.example` already carries a Supabase section, but it names
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` — the key
  types Supabase is **retiring by the end of 2026**. A project created today
  should use the opaque `sb_publishable_…` / `sb_secret_…` keys instead, so
  this spec renames those two variables rather than filling in names that
  expire within months.
- The working tree has one uncommitted change that predates this task:
  `.claude/settings.json` (added permission entries and a Bash hook blocking
  reads of secret paths). **It does not belong in this task's commits.**
- Local `main` is behind `origin/main`, and several merged remote-tracking
  branches are stale. Start with `git fetch --prune` and a fresh `main`.

**Stop line.** This task ends when a real Supabase project exists, its
credentials are in `.env.local`, a committed client module wraps them, and
`npm run db:check` proves over the network that both keys authenticate
against that project's Postgres. It creates **no tables, no migrations and no
UI** — `cities`, the seed, the migration tooling and the DB-backed homepage
are all task 4, spec'd and implemented in its own fresh session.

The human-only steps live in `docs/current/HUMAN_ACTION.md`, with their
rationale and your ticks in `docs/current/HUMAN_ACTION_TRACKING.md`.

## Goals / Non-goals

**Goals**

- A Supabase project created in **`ca-central-1` (Montreal)** — same region as
  the data and as the machine that will run the nightly scraper. The region is
  fixed at creation; changing it later means recreating the project.
- `@supabase/supabase-js` (`^2.116.0` — `2.115.0` when this spec was written,
  superseded by the time `npm install` ran) added as the single database
  dependency.
  The app talks to Postgres over HTTPS/PostgREST — **no connection string, no
  `DATABASE_URL`, no pooler hostname anywhere in this task.**
- `.env.example` updated to the current key names
  (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `SUPABASE_SECRET_KEY`), with the legacy `ANON_KEY` / `SERVICE_ROLE_KEY`
  lines removed.
- `.env.local` filled in with the real values (gitignored, never committed).
- `src/lib/db/supabase.ts` — a framework-agnostic module exposing two client
  factories: one keyed by the publishable key, one by the secret key.
- `scripts/check-db.mts` + an `npm run db:check` script that proves
  reachability over the network and exits non-zero on failure.
- The RLS convention recorded in `CLAUDE.md` (via the `vibe-specialist`
  subagent, as `CLAUDE.md` mandates) so task 4's migration enables it without
  re-deciding.
- Everything lands through a branch → PR → `gh pr merge --rebase`, with `ci`
  green.

**Non-goals**

- **Any table, migration, seed or migration tooling** — task 4. In particular
  the Supabase CLI is deliberately **not** installed here; task 4's spec picks
  the migration mechanism.
- The DB-backed homepage — task 4. `src/app/page.tsx` is not touched.
- Vercel account, project, or copying these env vars into Vercel — task 5.
- `README.md`'s `TBD` placeholders — task 6.
- The adversarial `/code-review` over the full milestone diff — task 7.
- Supabase Auth, Google OAuth, RLS *policies* (there are no tables to attach
  them to yet), pgvector, Edge Functions, Storage, Realtime.
- Any change to `.github/workflows/ci.yml`. CI holds no Supabase secrets and
  must not start needing them.

## Approach

1. **Start from a clean, current `main`.**
   `git fetch --prune`, `git switch main`, `git pull`, then
   `git switch -c feat/supabase-connection`. Confirm
   `git status --short` shows only the pre-existing `.claude/settings.json`
   modification, and **leave that file alone** — it is not part of this task.

2. **Walk the human through creating the project** (they do this in the
   browser; the steps are listed in `HUMAN_ACTION.md`). Ask them for, and wait
   on, three values:

   - **Project URL** — `https://<ref>.supabase.co`
   - **Publishable key** — starts `sb_publishable_`
   - **Secret key** — starts `sb_secret_`

   All three are on **Settings → API Keys**. Note for the walkthrough: there
   is no separate "Settings → API" page any more, and the dashboard will also
   show legacy `anon` / `service_role` JWTs — **those are the wrong ones**;
   they are retired at the end of 2026. If the project shows no
   `sb_publishable_` key, the human creates one on that page.

   The database password chosen at project creation is **not needed by this
   task** (nothing here connects over raw Postgres), but it cannot be
   retrieved later, so tell them to save it.

3. **Install the client.** `npm install @supabase/supabase-js` — expect
   `2.115.0`. This is the only dependency this task adds.

4. **Rewrite the Supabase block in `.env.example`.** Replace the three legacy
   lines with:

   ```
   NEXT_PUBLIC_SUPABASE_URL=""
   NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=""
   SUPABASE_SECRET_KEY=""
   ```

   Update the surrounding comment: keys come from **Settings → API Keys**; the
   publishable key is public by design and ships to the browser, so what
   actually protects data is RLS; the secret key bypasses RLS and is
   **server-side only** — it must never gain a `NEXT_PUBLIC_` prefix, because
   Next.js inlines every `NEXT_PUBLIC_` variable into the client bundle at
   build time. Leave the `LOCAL_LLM_BASE_URL`, `MISTRAL_API_KEY` and
   `ADMIN_*` sections untouched.

5. **Fill `.env.local`** with the three real values. The URL and the
   publishable key are public by design, so the human can paste them straight
   into the conversation; the **secret key should not enter the transcript** —
   offer to let the human write that one line into `.env.local` themselves and
   just say when it is done (this is listed in `HUMAN_ACTION.md`). Either way,
   confirm the file is still ignored — `git check-ignore -v .env.local` must
   print a match — and never echo the secret key into terminal output.

   Note: `.env.local` already exists but its contents are unreadable by
   design (a `.claude/settings.json` hook blocks Bash and Read on secret
   paths). Ask the human whether it holds anything worth preserving before
   overwriting it.

6. **Write `src/lib/db/supabase.ts`.** Two factory functions, not top-level
   singletons — a module-level `createClient()` call would read env vars
   during `next build`, which runs without them in CI:

   ```ts
   import { createClient } from "@supabase/supabase-js";

   /** Publishable key — safe in the browser; RLS policies govern access. */
   export function publicClient() {
     return createClient(
       process.env.NEXT_PUBLIC_SUPABASE_URL!,
       process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
     );
   }

   /** Secret key — bypasses RLS. Server and scripts only, never the browser. */
   export function serviceClient() {
     return createClient(
       process.env.NEXT_PUBLIC_SUPABASE_URL!,
       process.env.SUPABASE_SECRET_KEY!,
     );
   }
   ```

   Non-null assertions are the deliberate choice here (no `zod`, no env
   wrapper). `createClient` throws a named error of its own when handed
   `undefined`, so a missing variable still fails fast rather than silently —
   confirm the exact message when writing step 7's error output.

   **This module must stay framework-agnostic**: no `import "server-only"`, no
   `next/*` imports, no `@/` path alias. Plain Node executes it in step 7 and
   resolves none of those.

7. **Write `scripts/check-db.mts`.** Two probes, in this order:

   - **Probe A — authentication and reachability** (must pass). One probe per
     key, because the two key types do not answer to the same endpoint —
     **corrected during implementation: a single shared endpoint, as this step
     originally demanded, is factually wrong. Both branches below were verified
     empirically.**

     The **secret** key reads PostgREST's OpenAPI root: `fetch(
     `${url}/rest/v1/`, { headers: { apikey: key, Authorization: `Bearer
     ${key}` } })` must return HTTP **200**. That endpoint needs **no tables**,
     so it is a definitive credential check before any schema exists.

     The **publishable** key is rejected there — Supabase answers `401 "Only
     secret API keys can be used for this endpoint."` — so it is probed against
     a table path instead, where a *missing table* (`404` with PostgREST code
     `PGRST205` or `42P01`) still proves the key authenticated; an invalid key
     never gets that far, it is turned away with `401 "Invalid API key"`. Point
     it at a name **no migration will ever create**
     (`__connectivity_probe__`), not at `cities`: a real table would make the
     check mean one thing before its migration (404) and another after (200),
     and a `200` with zero rows — what RLS returns on a table with no read
     policy — would pass for the same reason as the 404. Require the
     missing-table 404 and nothing else.

     A `401` means the key is wrong; a DNS/connect failure means the URL is
     wrong or the project is paused.
   - **Probe B — schema state** (informational until task 4). Call
     `serviceClient().from("cities").select("*").limit(1)`. Three outcomes:
     no error → print the row count; an error meaning *the table does not
     exist* → print `cities not migrated yet (expected before task 4)` and
     still exit 0; **any other error** → print it and exit non-zero.

     Do **not** match a single hard-coded error code. Depending on the
     PostgREST version the missing-table error surfaces as `42P01` or
     `PGRST205`; accept either, and print the raw `code` and `message` so task
     4 inherits the real strings.

   The file is `.mts` on purpose: `package.json` has no `"type": "module"`, so
   a plain `.ts` entry point is treated as CommonJS and `import` throws
   `Cannot use import statement outside a module` — **verified**. Import the
   client module by relative path **with its extension**:
   `import { serviceClient } from "../src/lib/db/supabase.ts";`

8. **Add `"allowImportingTsExtensions": true` to `tsconfig.json`.** Step 7's
   import is required by Node and rejected by `tsc` without this flag —
   **verified**: `error TS5097: An import path can only end with a '.ts'
   extension when 'allowImportingTsExtensions' is enabled.` The flag is legal
   because `noEmit` is already `true`. After adding it, re-run
   `npm run typecheck` **and** `npm run build`; if Next.js objects to the
   option, the documented fallback is to add `tsx` as a devDependency and run
   the script with `npx tsx scripts/check-db.ts` instead — do not work around
   it by duplicating the client inline, which would defeat the point of the
   check.

9. **Add the npm script.**

   ```json
   "db:check": "node --env-file-if-exists=.env.local --disable-warning=MODULE_TYPELESS_PACKAGE_JSON scripts/check-db.mts"
   ```

   `--env-file-if-exists` is native to Node 24 (no `dotenv` dependency). Use
   the `-if-exists` form, **not** `--env-file`: the plain flag makes Node exit
   **9** with `node: .env.local: not found` before the script runs a single line,
   so the script's own `FAIL  NEXT_PUBLIC_SUPABASE_URL is not set — copy
   .env.example and fill it in` would be unreachable on exactly the fresh-clone
   path it exists for, and the exit code would not be the **1** the red proof
   expects. Let the script do the complaining. The
   `--disable-warning` flag suppresses `MODULE_TYPELESS_PACKAGE_JSON`, which
   Node otherwise prints for the imported `.ts` module on every run —
   **verified**; without it the script's output is buried in warning text.

10. **Prove it green, then prove it red.** `npm run db:check` exits 0 against
    the real project. Then run it once with a deliberately wrong key and
    confirm a non-zero exit — pass the env inline rather than editing
    `.env.local`, so the real file is never touched:

    ```
    NEXT_PUBLIC_SUPABASE_URL=<real> \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_bogus \
    SUPABASE_SECRET_KEY=sb_secret_bogus \
    node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON scripts/check-db.mts; echo $?
    ```

11. **Record the RLS convention in `CLAUDE.md`** via the `vibe-specialist`
    subagent (mandatory — `CLAUDE.md` states changes to itself go through it).
    Two or three lines under "Constraints that aren't visible in the code":
    the publishable key is public and ships to the browser, so every table
    gets RLS enabled at creation with an explicit policy; reads of public data
    use the publishable key, writes use the secret key server-side only; the
    secret key never gets a `NEXT_PUBLIC_` prefix. `CLAUDE.md` is 101 lines
    today and must stay under 200 (`Human_guidelines.md` §3).

12. **Commit, PR, merge.** Branch `feat/supabase-connection`, per
    `.claude/skills/commit/SKILL.md` conventions. Before staging, run
    `git status --short` and stage files **by name** — never `git add -A` —
    because `.claude/settings.json` and a possibly-flipped `next-env.d.ts`
    are both sitting in the working tree. Then `gh pr create`, wait for `ci`,
    `gh pr merge --rebase`.

## Files & interfaces touched

- `package.json` / `package-lock.json` — `@supabase/supabase-js` dependency,
  `db:check` script.
- `.env.example` — Supabase block rewritten to the new key names.
- `.env.local` — **gitignored**, filled with real values.
- `src/lib/db/supabase.ts` — **new**; `publicClient()` and `serviceClient()`.
- `scripts/check-db.mts` — **new**; the reachability check.
- `tsconfig.json` — `allowImportingTsExtensions: true`.
- `CLAUDE.md` — RLS convention, via `vibe-specialist`.

Untouched, stated so a broad `git add` is not tempted: `.claude/settings.json`
(dirty before this task started), `next-env.d.ts`, `src/app/**`,
`.github/workflows/ci.yml`, `README.md`, `docs/ROADMAP.md`,
`tests/smoke.test.ts`.

## Edge cases

- **Legacy keys are the trap.** The dashboard shows `anon` / `service_role`
  JWTs alongside the new keys, and most tutorials still use them. Anything
  starting `eyJ` is a legacy JWT — wrong for a project created now.
- **`SUPABASE_SECRET_KEY` must never become `NEXT_PUBLIC_SUPABASE_SECRET_KEY`.**
  Next.js inlines `NEXT_PUBLIC_` variables into the client bundle at build
  time, which would publish an RLS-bypassing credential to every visitor. If
  the secret key is ever needed in a component, the component is on the wrong
  side of the boundary.
- **No connection string is involved.** Supabase's direct Postgres endpoint
  (`db.<ref>.supabase.co`) is IPv6-only without the paid IPv4 add-on, and
  serverless callers are supposed to use the Supavisor pooler. None of that
  applies while access goes over HTTPS/PostgREST — if the implementer finds
  themselves hunting for a `DATABASE_URL`, they have left this spec's design.
- **There are no tables yet**, so Probe B *should* report a missing `cities`
  table. That is a pass, not a failure. A check that demanded a table would be
  unrunnable until task 4 lands. Probe A's own table is a different matter: it
  is a name that never exists, so its missing-table 404 stays the expected
  answer forever and the probe keeps one meaning either side of task 4.
- **Missing-table error codes differ by PostgREST version** (`42P01` vs
  `PGRST205`). Match on either; never on one.
- **A `.ts` entry point runs as CommonJS** because `package.json` has no
  `"type": "module"` — hence `.mts` for the script. Verified by running both.
- **Node needs the `.ts` extension; `tsc` rejects it** without
  `allowImportingTsExtensions` (TS5097, verified). Both halves are required —
  changing one without the other breaks either `npm run db:check` or
  `npm run typecheck`.
- **`scripts/` is linted, typechecked and formatted.** `tsconfig.json`
  includes `**/*.ts` and `**/*.mts`, ESLint has no ignore for `scripts/`, and
  `.prettierignore` only excludes `*.md` and build output. A new script that
  is not Prettier-clean turns `ci` red at `format:check`, not at the step the
  author was thinking about. Run `npm run format` before committing.
- **CI has no Supabase secrets and must not acquire any.** `db:check` stays
  out of `ci.yml` and out of the Vitest suite (`vitest.config.mts` includes
  only `{src,tests}/**`, so `scripts/` is not collected — keep it that way).
- **Free-tier projects pause after ~7 days of inactivity.** A `db:check` that
  worked last week can fail with a connection error for this reason alone;
  the fix is to restore the project from the dashboard, not to re-check the
  keys.
- **`next-env.d.ts` flips between `next build` and `next typegen`** — the
  committed version points at `./.next/dev/types/…` and a local build rewrites
  it to `./.next/types/…`. It will show as modified. `git checkout --
  next-env.d.ts` before committing; never hand-edit it.
- **`.claude/settings.json` is already modified** in the working tree from
  before this task. Do not stage it, and do not "clean up" by reverting it —
  it is someone else's change in flight.
- **`main` is protected but admin-bypassable.** The ruleset plus the local
  hook will refuse a direct push; that is correct. Open a PR.

## Out of scope

- `cities`, any migration, any seed, and the choice of migration tooling
  (Supabase CLI vs plain SQL) — task 4.
- The DB-backed homepage — task 4.
- Vercel project and its env vars — task 5.
- `README.md` — task 6.
- Full-milestone adversarial review — task 7.
- Supabase Auth / Google OAuth, pgvector, Storage, Realtime, Edge Functions.
- Any keep-alive automation to defeat free-tier pausing.

## Verification

Every bullet below is a command with a pass/fail result.

- `npm run db:check` exits **0** and prints a success line for **both** the
  publishable and the secret key. Confirm with `npm run db:check; echo $?`.
- The same script with a bogus key (step 10's inline-env invocation) exits
  **non-zero** — proving the check can actually fail, not just pass.
- `npm run lint`, `npm run format:check`, `npm run typecheck`,
  `npm run build`, and `npm test` all pass locally after the `tsconfig.json`
  change.
- `git grep -n "SUPABASE_ANON_KEY\|SERVICE_ROLE" -- ':(exclude)docs/'`
  returns **nothing** — the legacy names are gone from the code and config.
  `docs/` is excluded because this spec *names* both variables (in the
  Problem and Goals sections) to explain why they are being retired; an
  unscoped grep therefore reports its own prose and can never come back empty.
- `git grep -nE "sb_(secret|publishable)_[A-Za-z0-9_-]{20,}"` returns
  **nothing** — no real key literal was committed anywhere. Match on key-shaped
  *material*, not on the bare prefix: `.env.example` documents
  `SUPABASE_SECRET_KEY=sb_secret_…` by design (spec step 4) and step 10's red
  proof uses `sb_secret_bogus`, so `git grep "sb_secret_"` is expected to hit
  and proves nothing. Real keys run far longer than 20 characters.
- `git check-ignore -v .env.local` prints a `.gitignore` match, and
  `git log --all --oneline -- .env.local` is **empty**.
- `npm ls @supabase/supabase-js` reports **`2.116.0`** (`^2.116.0` in
  `package.json`; `2.115.0` was current when this spec was written and had
  been superseded by install time — the exact pin was not worth holding for a
  patch release).
- `git diff origin/main_agent...HEAD --stat` lists **only**: `package.json`,
  `package-lock.json`, `.env.example`, `src/lib/db/supabase.ts`,
  `scripts/check-db.mts`, `tsconfig.json`, `CLAUDE.md`,
  `docs/current/SPEC.md` and `docs/current/HUMAN_ACTION.md`. Anything else —
  especially `.claude/settings.json` or `next-env.d.ts` — means the staging
  was too broad.

  The two `docs/current/` files are in the list on purpose: the analyst stage
  writes them and never commits them, so the implementing PR carries them, as
  e63c1fc did for task 2. They must reach `main_agent` before
  `/archive-instructions` can file them.

  Use the **three-dot** form. `git diff origin/main_agent --stat` also reports
  everything `main_agent` gained since this branch left it (today: two
  agent-loop commits), which looks like over-broad staging and is not.
- `gh pr checks` shows `ci` **success**, and after merge
  `gh run list --workflow=ci.yml --branch=main --limit=1` shows conclusion
  `success`.
- `grep -n -i "rls\|publishable" CLAUDE.md` shows the new convention, and
  `wc -l CLAUDE.md` stays under 200.
- `git status --short` at the end shows nothing beyond the pre-existing
  `.claude/settings.json` modification.
