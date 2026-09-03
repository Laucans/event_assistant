# Spec: CI, branch protection & merge strategy

## Problem

This is task 2 of the "Initial architecture setup" milestone
(`docs/current/CURRENT_MILESTONE.md`). The milestone words it as
_"you run `gh auth login`; Claude: initial commit, `gh repo create`, push,
add `.github/workflows/ci.yml`"_ — but **most of that is already true**, so
this spec covers only what is genuinely left, plus the branch and merge
strategy the remaining tasks (3–6) need in order to know how to land their
work.

What was already verified as done, so no step re-does it:

- `gh auth status` → logged in as `Laucans`, ssh protocol, scopes
  `admin:public_key, gist, read:org, repo`. **The human-only `gh auth login`
  gate no longer exists.**
- The GitHub repo exists: `git@github.com:Laucans/event_assistant.git`,
  public, default branch `main`, with `origin/main` already pushed.
  **`gh repo create` must not be run.**

What is actually missing:

- `.github/` does not exist; the remote reports **0 workflows**.
- Local `main` is **ahead of `origin/main` by 2 commits** (`94ab5b1`,
  `20b404a`) that were never pushed.
- `main` has **no ruleset and no branch protection**; all three merge
  methods are enabled and merged branches are not auto-deleted.
- Nothing anywhere records how work should reach `main`. Every later task
  runs in a fresh session with no memory of this conversation, so the
  convention has to be written into `CLAUDE.md` or it does not exist.

**Stop line.** This task ends when `main` is protected by a green,
proven-red CI check and the branch/merge convention is recorded in
`CLAUDE.md`. It does **not** touch Supabase, the schema, the DB-backed page,
Vercel, or `README.md` — those are tasks 3, 4, 5 and 6, each spec'd and run
in its own fresh session.

The human-only steps for this spec are listed in
`docs/current/HUMAN_ACTION.md` and tracked, with their rationale, in
`docs/current/HUMAN_ACTION_TRACKING.md`.

## Goals / Non-goals

**Goals**

- The 2 pending commits pushed, so `origin/main` matches local `main` before
  any rule starts blocking pushes.
- `.github/workflows/ci.yml`: one sequential job on `ubuntu-latest` running
  `npm ci` then `lint`, `format:check`, `typecheck`, `build`, `test`, on
  pushes to `main` and on pull requests targeting `main`.
- The workflow proven **green** on a real PR, and proven **red** on a
  deliberately broken throwaway PR that is closed, never merged — per the
  milestone's explicit verify line and `Human_guidelines.md` §1.
- A ruleset on `main`: pull request required, **0** required approvals,
  the CI check required to pass, repository admin retained as a bypass
  actor.
- Repo settings: rebase merge only (squash and merge-commit disabled),
  auto-delete head branches on merge.
- The stray local `backup-pre-rebase` branch deleted, once the human
  confirms it is no longer needed as a safety net.
- The branch-naming and merge convention recorded in `CLAUDE.md`'s
  "Repository etiquette" section, edited **through the `vibe-specialist`
  subagent** as `CLAUDE.md` itself mandates.

**Non-goals**

- Supabase account, connection, keys, or any DB reachability check — task 3.
- The `cities` migration, seed, DB client, or the DB-backed page — task 4.
- Vercel account, project, env vars, or deploy — task 5. In particular, **no
  Vercel deploy-preview status check is added to the ruleset here**; if
  deploy previews are wanted as a required check, task 5 adds them.
- `README.md`'s two remaining `TBD` placeholders — task 6. (`CLAUDE.md` has
  no `TBD` left; only the etiquette section is touched here, and only to add
  the branch/merge convention that tasks 3–6 need immediately.)
- The adversarial `/code-review` pass over the milestone's full diff —
  task 7.
- Dependabot, CODEOWNERS, PR/issue templates, a release workflow, matrix
  builds across Node versions, or any cache beyond `setup-node`'s built-in
  npm cache.
- Rewriting existing history, or touching the `origin/main` commits that are
  already published.

## Approach

1. **Push the pending commits first, while `main` is still unprotected.**
   `git push origin main`, then confirm `git status -sb` prints
   `## main...origin/main` with no `[ahead N]`. This must happen before
   step 6 — the ruleset blocks direct pushes to `main` once it exists.

2. **Write `.github/workflows/ci.yml`.** One job, id and name `ci`, on
   `ubuntu-latest`. Triggers: `push` limited to `branches: [main]` and
   `pull_request` limited to `branches: [main]` — limiting the push trigger
   to `main` is what stops a PR branch from running the workflow twice.
   Steps, in this order so the cheap checks fail before the slow build:

   - `actions/checkout@v7`
   - `actions/setup-node@v7` with `node-version: 24` and `cache: npm`
     (local Node is `v24.16.0`; Next 16.3.4 declares `engines.node >=20.9.0`)
   - `npm ci`
   - `npm run lint`
   - `npm run format:check`
   - `npm run typecheck`
   - `npm run build`
   - `npm test`

   Set `NEXT_TELEMETRY_DISABLED: 1` at job level. Pin the two actions to the
   majors above — they are the current releases as of writing, **verified
   against `gh api repos/actions/checkout/releases/latest` and the same for
   `setup-node`, not from memory**; most examples online still show `v4`.

3. **Green proof.** Branch `feat/github-actions-ci` off the synced `main`,
   commit the workflow, push, and open a PR with `gh pr create`. Watch the
   run with `gh run watch` (or `gh pr checks`) and confirm the `ci` check
   reports **success**. Do not merge yet — step 4 needs a red run before the
   ruleset in step 6 can name a check it has actually seen.

4. **Red proof, on a throwaway branch that is never merged.** Branch
   `test/ci-red-path` off `main`, change the assertion in
   `tests/smoke.test.ts` to something deliberately false
   (`expect(1 + 1).toBe(3)`), push, open a PR. A failing test is chosen
   deliberately over a lint error: `eslint-config-next` reports several rules
   as warnings rather than errors, so "add an unused variable" is not a
   reliable way to make `npm run lint` exit non-zero, whereas a false
   assertion always fails `npm test`. Confirm the `ci` check reports
   **failure**, then `gh pr close` the PR and delete both the remote and
   local branch. Nothing from this branch reaches `main`.

5. **Merge the CI PR** with `gh pr merge --rebase`, then confirm the `push`
   trigger fires a second green run on `main` itself.

6. **Create the ruleset on `main`** with
   `gh api --method POST /repos/Laucans/event_assistant/rulesets`, targeting
   `refs/heads/main`, enforcement `active`, with:

   - a `pull_request` rule, `required_approving_review_count: 0` — you are
     the only contributor and GitHub will not let you approve your own PR,
     so any non-zero count locks the repo;
   - a `required_status_checks` rule naming the context **`ci`** — this
     string must match the job name from step 2 exactly;
   - `bypass_actors` retaining repository admin, so a genuine emergency does
     not require deleting the rule.

   Do not paste a remembered JSON payload — read the current ruleset schema
   from `gh api /repos/Laucans/event_assistant/rulesets` and the REST docs
   first, and if the payload proves fiddly, fall back to configuring it in
   Settings → Rules → Rulesets in the browser (a human step already listed
   in `HUMAN_ACTION.md`) and verify the result over the API either way.

7. **Repo settings hygiene.**
   `gh api --method PATCH repos/Laucans/event_assistant` setting
   `allow_rebase_merge=true`, `allow_squash_merge=false`,
   `allow_merge_commit=false`, `delete_branch_on_merge=true`.

8. **Delete the stray `backup-pre-rebase` local branch** — `git branch -D
   backup-pre-rebase` — only after the human has confirmed it in
   `HUMAN_ACTION_TRACKING.md`. It is local-only (no remote counterpart) and
   holds pre-rebase scaffold history; deleting it is irreversible.

9. **Record the convention in `CLAUDE.md`.** Invoke the `vibe-specialist`
   subagent (mandatory: `CLAUDE.md` states changes to itself go through that
   subagent) to extend "Repository etiquette" with: work lands on `main`
   through a pull request, never a direct push; branches are named
   `<type>/<slug>` reusing the commit types in
   `.claude/skills/commit/SKILL.md` (`feat`, `fix`, `docs`, `style`,
   `refactor`, `test`, `chore`, `AIchore`); merges are **rebase-only** and
   the branch auto-deletes; CI must be green to merge. Keep it to a few
   lines — `Human_guidelines.md` §3 caps `CLAUDE.md` at ~150–200 lines.

## Files & interfaces touched

- `.github/workflows/ci.yml` — **new**, the only application-side file this
  task creates.
- `tests/smoke.test.ts` — temporarily broken on the throwaway
  `test/ci-red-path` branch only; **unchanged on `main`**.
- `CLAUDE.md` — "Repository etiquette" section extended, via the
  `vibe-specialist` subagent.
- GitHub-side state, not files: the `main` ruleset, the repo's merge-method
  and auto-delete settings.
- Deleted: local branch `backup-pre-rebase`.

Untouched, and stated so a broad `git add` is not tempted: `package.json`,
`.gitignore`, `.env.example`, `README.md`, `docs/ROADMAP.md`.

## Edge cases

- **Ordering is load-bearing.** Steps 1 and 5 push to `main`; step 6 blocks
  direct pushes to `main`. Creating the ruleset early leaves the 2 pending
  commits stranded behind a rule that requires a PR they do not have.
- **A required check that never reports blocks every merge forever.** The
  ruleset's context string and the workflow's job name are the same literal
  `ci`. Renaming the job later without updating the ruleset makes `main`
  unmergeable, and the failure looks like "waiting for status to be
  reported", not like a misconfiguration.
- **The token has no `workflow` scope** (`repo`, `read:org`, `gist`,
  `admin:public_key` only). Pushing a diff that adds `.github/workflows/`
  over **HTTPS** would be rejected; over **ssh** it is fine, and `origin` is
  ssh today. Confirm `git remote -v` still shows `git@github.com:` before
  pushing step 3, and do not "fix" a rejection by switching the remote to
  HTTPS.
- **The red-proof PR must be closed, not merged.** A merged red PR puts a
  knowingly-broken test on `main` and makes every subsequent run red.
- **Lint severity is not a reliable failure signal** — see step 4. If a
  future task wants a red proof again, break a test, not a lint rule.
- **`npm ci` fails hard if `package-lock.json` and `package.json` disagree.**
  They agree today (all five scripts pass locally against the installed
  tree); if CI fails at install with an `EUSAGE` error, the fix is to
  regenerate the lockfile locally, not to switch CI to `npm install`.
- **`npm run typecheck` runs `next typegen && tsc --noEmit`.** `typegen`
  generates its own route types, so it does not need a prior `next build` —
  confirmed locally. Keep `typecheck` before `build` anyway; it is faster.
- **Rebase merge rewrites commit SHAs.** The local branch's commit hashes
  will not match what lands on `main`; `Co-Authored-By` trailers survive.
  Do not try to reconcile the hashes afterwards.
- **`next-env.d.ts` flip-flops between `next build` and `next typegen`, and
  it is committed.** The committed version (from `9556c1b`) points at
  `./.next/dev/types/...`; running `npm run build` rewrites it to
  `./.next/types/...`, leaving the working tree dirty. It does not affect
  CI (nothing commits there), but it will silently ride along in this
  task's diff if the implementer runs a local build and then stages
  broadly. Before committing, check `git diff next-env.d.ts` and
  `git checkout -- next-env.d.ts` if it flipped. Never hand-edit it to
  "fix" the churn — the file says it should not be edited, and the
  underlying inconsistency belongs to a separate task, not this one.
- **Admin bypass is a real hole, deliberately kept.** With bypass enabled,
  a direct push to `main` still succeeds for the repo owner. The convention
  in `CLAUDE.md` is what prevents it in practice; the ruleset is the
  backstop, not the enforcement.

## Out of scope

- Supabase account, connection, schema, seed, DB client, DB-backed page
  (milestone tasks 3–4).
- Vercel account, project, env vars, deploy, and any deploy-preview status
  check (task 5).
- `README.md`'s `TBD` placeholders (task 6).
- The adversarial review over the full milestone diff (task 7).
- Dependabot, CODEOWNERS, PR/issue templates, multi-Node matrix builds.

## Verification

Each of these produces a pass/fail signal, not an impression:

- `git status -sb` prints `## main...origin/main` with **no** `[ahead N]`,
  and `git log --oneline origin/main -1` shows the merged CI commit.
- `gh api repos/Laucans/event_assistant/actions/workflows --jq '.total_count'`
  returns `1` (was `0`).
- `gh run list --workflow=ci.yml --branch=main --limit=1` shows a run with
  conclusion **`success`**.
- `gh run list --workflow=ci.yml --limit=10` contains at least one run with
  conclusion **`failure`** — the throwaway red-path run.
- `gh pr list --state=all` shows the `test/ci-red-path` PR as **`CLOSED`**,
  not `MERGED`, and `git ls-remote --heads origin test/ci-red-path` returns
  nothing.
- `gh api repos/Laucans/event_assistant/rulesets --jq 'length'` returns `1`,
  and fetching that ruleset by id shows the `pull_request` rule with
  `required_approving_review_count: 0`, a `required_status_checks` rule whose
  context is `ci`, and a non-empty `bypass_actors`.
- `gh api repos/Laucans/event_assistant --jq '{squash:.allow_squash_merge,
  merge:.allow_merge_commit, rebase:.allow_rebase_merge,
  del:.delete_branch_on_merge}'` returns
  `{"squash":false,"merge":false,"rebase":true,"del":true}`.
- `git branch --list backup-pre-rebase` returns nothing.
- `grep -n "rebase" CLAUDE.md` shows the new etiquette lines, and
  `wc -l CLAUDE.md` stays under 200.
- Locally, on `main` after the merge: `npm run lint`, `npm run format:check`,
  `npm run typecheck`, `npm run build`, `npm test` all still pass, and
  `git status --porcelain` shows nothing beyond a possible `next-env.d.ts`
  flip from the local build — which must **not** appear in any commit
  (`git log -1 --stat` on the merged commit lists only
  `.github/workflows/ci.yml` and `CLAUDE.md`).
