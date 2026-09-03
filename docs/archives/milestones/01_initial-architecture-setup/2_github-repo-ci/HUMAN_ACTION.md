# Human actions — `docs/current/SPEC.md` (CI, branch protection & merge strategy)

The short list of things only you can do for the **current** spec. Everything
else in `docs/current/SPEC.md` is Claude's to execute.

Rationale, guidance, progress ticks and your own notes live in
`docs/current/HUMAN_ACTION_TRACKING.md` (gitignored). This file stays a clean,
unchecked list — when the task is finished `/archive-instructions` moves it,
next to the spec, into
`docs/archives/milestones/<NN>_<milestone-slug>/<N>_<task-slug>/`.

---

## Before Claude starts

- [ ] Confirm the local `backup-pre-rebase` branch can be deleted.
- [ ] _(Optional)_ Pre-allowlist `gh api`, `gh pr`, `gh run` and `git push`
      via `/permissions`.

## While Claude works

- [ ] Approve the GitHub state-changing prompts as they appear.
- [ ] Fallback if the ruleset API payload is rejected: create the rule
      yourself at Settings → Rules → Rulesets.
- [ ] Watch that the red-proof PR is CLOSED, not merged.

## Before calling it done

- [ ] Open the Actions tab yourself and confirm a green run and a red run.
- [ ] Open Settings → Rules → Rulesets and read the rule back.
- [ ] Review the diff (`Human_guidelines.md` §6, §8).
- [ ] Confirm the spec's Verification section passed with real output.
