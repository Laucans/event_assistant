# Human actions — `docs/current/SPEC.md` (Repo & app scaffold)

The short list of things only you can do for the **current** spec. Everything
else in `docs/current/SPEC.md` is Claude's to execute.

Rationale, guidance, progress ticks and your own notes live in
`docs/current/HUMAN_ACTION_TRACKING.md` (gitignored). This file stays a clean,
unchecked list — when the task is finished `/archive-instructions` moves it,
next to the spec, into
`docs/archives/milestones/<NN>_<milestone-slug>/<N>_<task-slug>/`.

---

## Before Claude starts

- [ ] Decide which git identity this repo's commits carry.
- [ ] _(Optional)_ Pre-allowlist the session's commands via `/permissions`.

## While Claude works

- [ ] Approve the permission prompts as they appear.
- [ ] Watch the `create-next-app` non-empty-directory step — never accept an
      overwrite of existing repo files.

## Before calling it done

- [ ] Open `http://localhost:3000` yourself once `npm run dev` is up.
- [ ] Review the diff (`Human_guidelines.md` §6, §8).
- [ ] Confirm the spec's Verification section passed with real output.
