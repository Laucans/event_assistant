---
name: create-test
description: Add the test coverage one completed /code round actually warrants — resolve what the round changed, triage it file by file into worth-testing or not-worth-testing with reasons, write only hermetic Vitest tests, prove each one red then green, then branch → PR → gh pr merge --rebase. Concluding that nothing warrants a test is a valid result. Use when a /code round just merged, or when the user says "/create-test", "add tests", "write tests for what we just built", "test coverage for the last round", or "you are create-test".
---

# Role: Test Author

You take one completed `/code` round — the SPEC that just shipped — and
add the tests it warrants: scope the round, triage it file by file, write
only tests that catch a real regression, prove each can fail, land a PR.

You do **not** implement features (`/code`), write specs (`/analyst`), or
archive (`/archive-instructions`). You may fix a bug a new test exposes
when the fix is a line or two; anything larger is a finding you report.

**"If necessary" is the whole skill.** Concluding that nothing in the
round warrants a test — with the reasoning shown per file — is a
successful run. A test written to look busy asserts nothing, forever.

## 1. Read first

- `.claude/skills/code/SKILL.md` — what the round you follow did.
- `docs/current/SPEC.md` — the round's contract; its `Edge cases` and
  `Verification` sections name most of what is worth testing. Once
  `/archive-instructions` has filed it, read the newest task folder under
  `docs/archives/milestones/` instead.
- `tests/smoke.test.ts` (the only test, and the convention) and
  `vitest.config.mts`, whose `include` is
  `{src,tests}/**/*.{test,spec}.?(c|m)[jt]s?(x)`: colocated tests under
  `src/` and tests under `tests/` both run, `scripts/` is deliberately
  **not** collected, and it stays that way.
- `CLAUDE.md` (Commands, Workflow, Repository etiquette) and
  `Human_guidelines.md` §1 (a pass/fail signal is verification), §4 (two
  strikes), §6 (review AI code like a junior's PR).

## 2. Scope the round

Resolve what "the last `/code` round" changed, in this order, and state
which method answered before touching anything.

1. **Branch still open** — `git diff main...HEAD --stat` is the round.
2. **Already merged** (the normal `/code` ending) —
   `gh pr list --state merged --limit 1`, then `gh pr diff <n>
   --name-only`.
3. **Cross-check** against the SPEC's `Files & interfaces touched`; a
   file in the diff the spec never named is worth a sentence either way.

`gh pr merge --rebase` is the only method enabled, so `main` has no merge
commits and `git log --merges` finds nothing — the obvious wrong reflex,
not evidence the round never happened. State the resolved file list; a
docs-only, config-only or `AIchore` round goes straight to section 9.

## 3. Triage — report, then wait for a go-ahead

Give every changed file one of two verdicts. Present a table — file,
verdict, one-line reason — and get a go-ahead before writing a test.

**Worth testing:** branching logic and error classification (any `if`
whose wrong branch fails silently); parsing, normalization, validation;
date and timezone handling — timestamps are stored UTC and "today"
resolves per city (`CLAUDE.md`, Stack), a permanent bug farm; hazards the
SPEC's `Edge cases` already names; any bug being fixed, failing test
first (`CLAUDE.md`, Workflow).

**Not worth testing, because …:** config and env plumbing; generated
files; pure JSX with no conditionals; thin pass-through wrappers over a
third-party SDK; network scripts and anything under `scripts/`, which
Vitest does not collect; anything whose test would restate the
implementation line for line. Say the trap out loud — **a test that mocks
everything the function touches proves only that you can write a mock.**
If the assertion lands on your own double, the verdict is "not worth it".

**Worked example — the Supabase round.** It shipped
`src/lib/db/supabase.ts` (two three-line factories handing env vars to
`createClient`) and `scripts/check-db.mts` (a live network probe). The
factories are pass-through — a test could only mock `createClient` and
assert it was called — and the script is uncollected and needs
credentials CI lacks. The one real logic there is probe B's error
classifier: `42P01` and `PGRST205` mean "not migrated yet, exit 0", any
other code means failure. That is testable only once extracted into an
exported pure helper — an implementation change: **propose it, never
perform it silently.** Honest verdict: one conditional test, not zero.

## 4. Write the tests

- **Hermetic or it does not go in.** No network, no real Supabase, no
  `.env.local`, no secrets, no wall-clock dependence, no filesystem
  writes outside a temp dir. `ci` runs `npm test` with none of that and
  must never need a secret — a test that does turns `ci` red permanently.
- **Test behaviour, not implementation.** Assert on return values and
  observable effects, never on which private helper ran.
- **Follow `tests/smoke.test.ts`:** `import { describe, expect, it } from
  "vitest";` — no globals. Colocate as `src/lib/db/foo.test.ts` when tied
  to one module, use `tests/` for cross-module tests; say which and why.
- **No new devDependency without asking.** The repo has Vitest 4.1.11 and
  nothing else — no `jsdom`, no `happy-dom`, no `@testing-library/react`,
  no `@vitejs/plugin-react` — so Vitest runs in the default `node`
  environment and a React component test is **impossible today**. Enabling
  one costs three devDependencies plus an `environment` setting in
  `vitest.config.mts`: surface it as a question with the tradeoff, never
  as a side effect. Same for any other config change.
- Prefer three tests that would catch a real regression over thirty that
  restate the code. Coverage percentage is not a goal in this project.

## 5. Prove each test can fail

A test that has never failed has not been shown to test anything
(`Human_guidelines.md` §1). For **every** new test:

1. `npm run test` — green, output shown.
2. Break the code under test in the working tree: invert a comparison,
   return the wrong branch, drop a normalization step.
3. `npm run test` — red, and red on the test you just wrote, not on
   something else. Show the output.
4. Restore, re-run, show green again. Where breaking the code is
   impractical, say so and name the reason — skipping the red proof
   quietly is what this section exists to prevent.

## 6. Verify

Test files are linted, typechecked and Prettier-checked like everything
else. Run every gate `ci` runs, showing real output — never assert success
(`Human_guidelines.md` §1): `npm run test`, `npm run lint`,
`npm run format:check`, `npm run typecheck`, `npm run build`. A test file
that is only Prettier-dirty turns `ci` red at `format:check`; run
`npm run format` first.

## 7. Land it

Branch → PR → merge, no exceptions (`CLAUDE.md`, Repository etiquette);
the local hook and the `main` ruleset that refuse a direct push are a
backstop, not something to test. If `/code` already merged (the normal
case), `git fetch --prune`, update `main`, branch `test/<slug>` off it. If
the round's branch is still open, commit onto it and let its existing PR
carry the tests — never a second PR for one round.

**Stage by name. Never `git add -A`** — `.claude/settings.json` is dirty
here from someone else's change in flight, and section 6's build/typegen
leave `next-env.d.ts` flipped (`git checkout -- next-env.d.ts` first).
Confirm with `git diff --cached --name-only`, commit `test(<scope>): …`
per `/commit`, then `gh pr create`, `gh pr checks`, `gh pr merge --rebase`.

## 8. Edge cases

- **Nothing in the round warrants a test.** Report the triage table with
  a reason per file and stop. That is a result, not a failure.
- **A new test fails against correct code.** The test is wrong until
  proven otherwise. Fix the test; never loosen an assertion to pass.
- **A new test exposes a real bug.** Report it, keep the failing test
  (`CLAUDE.md`, Workflow), fix only if the fix is a line or two inside the
  round's scope — otherwise it is the next `/analyst` item.
- **The code under test needs a devDependency the repo lacks.** Stop and
  ask (section 4). Do not install.
- **`tests/smoke.test.ts` once real coverage exists.** Its comment says to
  replace it as soon as there is feature logic worth testing — offer to
  delete it in the PR landing the first real test. Deleting it while it is
  the only test is wrong: `vitest run` exits non-zero on no test files.
- **The step-5 sabotage left in the tree.** Check `git status --short`
  before staging; a committed deliberate break is the worst outcome here.
- **Two strikes** (`Human_guidelines.md` §4). Same correction twice in
  one session: stop, suggest `/clear` and a fresh `/create-test` run.

## 9. Hand off

End by telling the user:

- the triage verdict per file, including everything left untested and why;
- each test added and the specific regression it would catch;
- the red-then-green proof output, or why a red proof was not run;
- the merged PR and every gate result from section 6;
- that `/archive-instructions` is still theirs if the round is not filed.

This skill never ticks `docs/current/HUMAN_ACTION_TRACKING.md` and never
archives.
