# Spec: Repo & app scaffold

## Problem

This is the first slice of the "Initial architecture setup" milestone
(`docs/current/CURRENT_MILESTONE.md`): before any CI, database, or deploy wiring
happens, the repo needs a working local Next.js app with its full
toolchain in place, committed to a local git history. This task stops at
the first local commit — no GitHub push, no CI, no Supabase, no Vercel.
Those are separate follow-on tasks against the same milestone, to be
spec'd and run in their own fresh sessions.

The human-only steps for this spec (decisions and approvals Claude can't
make on its own) are tracked in `docs/current/HUMAN_ACTION.md`.

## Goals / Non-goals

**Goals**

- Next.js (TypeScript, App Router) app scaffolded with npm at the repo
  root, using `src/app/` for routes (matching the `src/lib/db/` etc.
  layout implied by `docs/ARCHITECTURE.md`) — fitting around, not overwriting,
  the existing `src/`, `tests/`, `docs/`, `CLAUDE.md`, `README.md`,
  `Human_guidelines.md`, and `.claude/`.
- Tailwind CSS + shadcn/ui installed and configured. Accept whatever
  Tailwind major `create-next-app` ships today (v4) — it is configured
  CSS-first via `@theme` in `src/app/globals.css` and has **no**
  `tailwind.config.js`; run `shadcn init` in its v4-compatible mode.
- ESLint + Prettier configured using Next.js's default ESLint setup, with
  the two not fighting each other on formatting rules.
- A `typecheck` npm script (`tsc --noEmit`) — the CI task
  (`docs/current/CURRENT_MILESTONE.md` step 2) runs lint/typecheck/build/test and
  needs this script to already exist.
- Vitest wired to an `npm test` script, with one trivial smoke test that
  proves the runner actually executes (no real feature logic exists yet).
- `.gitignore` verified/updated to exclude `node_modules` and `.env.local`
  (plus standard Next.js ignores), git initialized locally on `main`, and
  one initial commit made.

**Non-goals**

- GitHub repo creation, push, or CI (`docs/current/CURRENT_MILESTONE.md` steps
  5–6) — separate task, needs `gh auth login` first.
- Supabase account, connection, or schema (steps 7–9) — separate task.
- Vercel account or deploy (step 10) — separate task.
- `CLAUDE.md` / `README.md` content updates (step 11) — deferred until
  the full pipeline (CI, DB, deploy) actually exists, so the docs describe
  something real rather than a partial setup.
- Component/DOM testing setup (`jsdom`, `@testing-library/react`,
  `@vitejs/plugin-react`) — added by the first task that has a component
  worth testing. The smoke test here is deliberately plain.
- Any product feature work (chat, scraping, admin panel, activity UI).

## Approach

1. Pre-git housekeeping, before anything is staged:
   - Delete `read-docs-spec-md-and-tell-zazzy-wind.md` at the repo root — a
     superseded Claude plan file, now covered by
     `docs/current/CURRENT_MILESTONE.md`. It must never enter git history.
   - Check `.gitignore` excludes `node_modules` and `.env.local`, and add
     the Next.js ignores it's currently missing: `.next/`, `.vercel`,
     `*.tsbuildinfo`, `coverage/`. Note `next-env.d.ts` **is** committed,
     not ignored.
2. Scaffold the Next.js app (`create-next-app`, TypeScript, App Router,
   ESLint, `src/` directory) at the repo root. The target directory is
   non-empty (`docs/`, `src/`, `tests/`, and root markdown files already
   exist) — check `create-next-app`'s current behavior/flags for
   non-empty directories first, and merge rather than overwrite anything
   existing.
3. Install and configure Tailwind CSS + shadcn/ui (`shadcn init`). Tailwind
   v4: theme lives in `src/app/globals.css` via `@theme`, no JS config file
   to create or look for.
4. Configure ESLint + Prettier on top of Next.js's default ESLint config;
   add `eslint-config-prettier` (or equivalent) so Prettier owns
   formatting and ESLint doesn't fight it. Add a `typecheck` script
   (`tsc --noEmit`) to `package.json` alongside the generated scripts.
5. Install Vitest, add an `npm test` script, and write one trivial smoke
   test at `tests/smoke.test.ts` — a plain non-React assertion (e.g.
   arithmetic). Dependencies stay limited to `vitest`; no `jsdom`,
   `@testing-library/react`, or `@vitejs/plugin-react`.
6. `git init -b main`, stage, and make the initial commit.

## Files & interfaces touched

- Next.js scaffold: `package.json`, `next.config.*`, `tsconfig.json`,
  `src/app/` routes, `src/app/globals.css` (Tailwind v4 `@theme` config —
  there is no `tailwind.config.*`).
- `eslint.config.*`, `.prettierrc`.
- `vitest.config.ts` + `tests/smoke.test.ts`.
- `components.json` (shadcn/ui) and whatever `src/components/ui/` and
  `src/lib/utils.ts` files `shadcn init` generates.
- `.gitignore` (add the missing Next.js ignores per Approach step 1).
- Deleted: `read-docs-spec-md-and-tell-zazzy-wind.md`.

## Edge cases

- `create-next-app` scaffolding into a non-empty directory: must not
  overwrite or delete `docs/`, `src/`, `tests/`, `CLAUDE.md`, `README.md`,
  `Human_guidelines.md`, or `.claude/`. If the tool refuses to run
  non-interactively in a non-empty dir, scaffold into a temp location and
  merge in the generated files by hand instead of forcing an overwrite.
- Existing empty `src/` and `tests/` directories: use `src/app/` for
  Next.js routes (not a root-level `app/`) so the layout matches what
  `docs/ARCHITECTURE.md` already assumes for `src/lib/db/`, `src/lib/llm/`,
  etc. in later tasks.
- `shadcn init` prompts for base color / CSS-variables style — take the
  defaults non-interactively rather than stopping to ask.
- `vitest.config.ts` must set `test.include` so it covers `tests/**` —
  Vitest's default patterns won't reliably pick up a root-level `tests/`
  directory alongside `src/`.
- ESLint/Prettier conflicts on formatting rules — resolve via
  `eslint-config-prettier`, don't hand-pick which tool wins rule by rule.
- Don't commit `node_modules` or any `.env*` file — re-check
  `.gitignore` right before the first `git add`, not just at step 1.
- `init.defaultBranch` is unset on this machine, so a bare `git init`
  yields `master`; the next task (`gh repo create` + push) assumes `main`.
  Use `git init -b main`.
- Commit identity: the global git config is `laurent@marigold.dev`, while
  this account's address is `laurent@groupe-canix.ca`. Confirm which the
  repo's commits should carry before the initial commit, and set a
  repo-local `user.email` if it differs from the global one.

## Out of scope

- GitHub repo, push, CI (`docs/current/CURRENT_MILESTONE.md` steps 5–6).
- Supabase account, connection, schema (steps 7–9).
- Vercel deploy (step 10).
- `CLAUDE.md` / `README.md` updates (step 11).

## Verification

- `npm run dev` boots the app locally with no errors.
- `npm run lint` passes.
- `npm run typecheck` passes.
- `npm run build` completes successfully.
- `npm test` runs and the smoke test passes.
- `git log` shows exactly one commit on branch `main`; `git status` is
  clean; `node_modules`, `.next/`, and any `.env*` file are confirmed
  untracked.
