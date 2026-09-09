# Human actions — `docs/current/SPEC.md` (Supabase account & connection)

The short list of things only you can do for the **current** spec. Everything
else in `docs/current/SPEC.md` is Claude's to execute.

Rationale, guidance, progress ticks and your own notes live in
`docs/current/HUMAN_ACTION_TRACKING.md` (gitignored). This file stays a clean,
unchecked list — when the task is finished `/archive-instructions` moves it,
next to the spec, into
`docs/archives/milestones/<NN>_<milestone-slug>/<N>_<task-slug>/`.

---

## Before Claude starts

- [x] Create the Supabase account (free plan).
- [x] Create the project in region `ca-central-1` (Montreal) and save the
      database password.
- [x] Hand over the Project URL and publishable key from Settings → API Keys;
      write the secret key into `.env.local` yourself.
- [x] Say whether the existing `.env.local` holds anything worth keeping.
- [x] _(Optional)_ Pre-allowlist `npm install`, `npm run db:check` and
      `node scripts/*` via `/permissions`.

## While Claude works

- [ ] Approve `npm install`, `gh pr create` and `gh pr merge --rebase`.
- [ ] Watch that the secret key never appears in terminal output.
- [ ] Decide the fallback if `allowImportingTsExtensions` upsets the Next
      build.

## Before calling it done

- [ ] Open the Supabase dashboard and confirm the project is Active and in
      `ca-central-1`.
- [ ] Review the diff (`Human_guidelines.md` §6, §8).
- [ ] Confirm the spec's Verification section passed with real output,
      including the red proof.
- [ ] Note the 7-day free-tier pause clock before task 4 starts.
