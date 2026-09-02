# Vibe Coding with Claude — Human Guidelines

A working reference for how to drive this project with Claude Code effectively.
Sourced and condensed from Anthropic's official best practices and current
(2026) vibe-coding security guidance. Read this once, then skim it again after
a rough session.

## 1. The core loop: Explore → Plan → Build → Verify

Don't let Claude jump straight to coding on anything non-trivial — it tends to
solve the wrong problem.

1. **Explore** — Put Claude in plan mode (`Shift+Tab` until you see
   `⏸ plan mode on`, or `claude --permission-mode plan`). Ask it to read the
   relevant files and explain what it finds. No edits happen in this phase.
2. **Plan** — Ask for a concrete implementation plan. Review it (`Ctrl+G` opens
   it in your editor) before approving.
3. **Build** — Exit plan mode and let Claude implement, writing/running tests
   as it goes.
4. **Verify** — Give Claude something that produces a pass/fail signal: a test
   suite, a build, a lint run, a screenshot diff. "Looks done" is not
   verification — a green check is.

Skip planning for genuinely small, one-sentence-diff changes (typo fix, log
line, rename). Use it whenever scope is unclear, multiple files are touched,
or you're unfamiliar with the code being changed.

## 2. Prompting

Vague prompts are fine for open-ended exploration ("what would you improve
here?"). For real work, be specific:

| Instead of              | Say                                                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ |
| "add tests for foo.py"  | "test foo.py's edge case where the user is logged out; avoid mocks"                                          |
| "fix the login bug"     | "login fails after session timeout — check token refresh in src/auth/, write a failing test first, then fix" |
| "add a calendar widget" | "follow the pattern in HotDogWidget.php; no new libraries"                                                   |

Reference files with `@`, paste screenshots directly, pipe in logs
(`cat error.log | claude`), and give example test cases up front so Claude
knows what "correct" means before it starts.

For a real feature, have Claude interview you first:

> I want to build [X]. Interview me in detail using AskUserQuestion. Ask about
> technical implementation, UI/UX, edge cases, and tradeoffs. Keep going until
> we've covered everything, then write a spec to `docs/current/SPEC.md`.

Start a **fresh session** to implement the spec — clean context beats a long
thread full of the interview back-and-forth.

## 3. CLAUDE.md — keep it lean

`CLAUDE.md` (already scaffolded in this repo) is loaded on every session. It
is not documentation — it's the stuff Claude can't infer from reading the
code.

- Keep it under ~150–200 lines. Every line costs context on every turn.
- Include: bash commands Claude can't guess, non-default code style, test
  runner + how to run a single test, branch/PR conventions, required env vars,
  known gotchas.
- Exclude: anything derivable by reading the code, standard language
  conventions, long tutorials, API docs (link instead), "write clean code"
  platitudes.
- Ask of every line: _"would removing this cause a mistake?"_ If not, cut it.
- If Claude keeps ignoring one rule, the file is probably too long and that
  rule is drowning. Add `IMPORTANT` to the one rule that matters, not to
  everything.
- Check it into git. It compounds in value like any other code — review and
  prune it the same way.
- For workflows/knowledge only needed sometimes, use a **skill**
  (`.claude/skills/<name>/SKILL.md`) instead of bloating CLAUDE.md — skills
  load on demand.

## 4. Context management

Performance degrades as the context window fills. Treat it as the scarce
resource.

- `/clear` between unrelated tasks. Don't let a debugging tangent bleed into
  the next feature's context.
- **Two-strikes rule**: if you've corrected Claude on the same issue twice in
  one session, stop. `/clear` and write a better initial prompt with what you
  just learned, rather than correcting a third time into a polluted context.
- For research that touches many files, delegate to a subagent
  ("use subagents to investigate how auth handles token refresh") — it
  explores in its own context and reports back a summary, keeping your main
  thread clean.
- Use `/rewind` (or double-tap `Esc`) to snapshot back to an earlier point if
  an approach goes sideways. It restores conversation and/or code. Note: this
  only captures changes made through Claude's own edit tools, not raw Bash —
  it's not a substitute for git.

## 5. Permissions & environment

- Configure `/permissions` to allowlist commands you trust (`npm run lint`,
  `git commit`, etc.) so you're not clicking through the same approval every
  session.
- Use sandboxing (`/sandbox`) where available for OS-level isolation.
- Install and let Claude use CLI tools for external services (`gh`, `aws`,
  `gcloud`, ...) rather than raw API calls — more context-efficient and
  usually better-supported.
- Use hooks (`.claude/settings.json`) for anything that must happen with zero
  exceptions — e.g. "run eslint after every edit" or "block writes to
  migrations/". Hooks are deterministic; CLAUDE.md instructions are advisory.

## 6. Review AI-generated code like you'd review a junior engineer's PR

This is the part that's easy to skip when things feel like they're moving
fast. Don't.

- **Nothing generated by Claude goes straight to production.** Treat it as
  untrusted until it's been read, tested, and reviewed — regardless of how
  plausible it looks.
- At least one human reviews every AI-touched diff before merge, specifically
  for: injection risks (SQL/XSS/command), missing input validation, auth/
  authorization logic, secrets or credentials committed in code, and unsafe
  defaults.
- Independent literature puts the rate of at least one known security flaw in
  AI-generated code samples at roughly 45% even for current flagship models —
  assume it applies here too.
- Use a **fresh subagent as an adversarial reviewer** before calling
  something done: it sees only the diff and your criteria, not the reasoning
  that produced the change, so it's not biased toward agreeing with itself.
  `/code-review` runs this out of the box.
  > "Use a subagent to review this diff against docs/current/SPEC.md. Check every
  > requirement is implemented, edge cases have tests, and nothing outside
  > scope changed. Report gaps, not style preferences."
- Focus human review effort on high-impact surfaces — permissions, auth,
  payment/data-handling, external integrations — not on nitpicking every
  generated line.
- Keep secrets out of prompts and out of generated code entirely; use env
  vars / a secrets manager, never hardcode.

## 7. Common failure patterns to watch for

- **Kitchen-sink session** — one task drifts into three unrelated ones,
  context fills with noise. Fix: `/clear` between tasks.
- **Correcting in a loop** — same mistake, corrected repeatedly. Fix: after
  two failed corrections, `/clear` and re-prompt with what you learned.
- **Bloated CLAUDE.md** — so long that real rules get lost. Fix: prune
  ruthlessly, convert repeatable enforcement to hooks.
- **Trust without verification** — a plausible-looking implementation that
  silently misses edge cases. Fix: always demand a runnable check (tests,
  build, screenshot) before accepting "done."
- **Unscoped exploration** — "investigate the codebase" with no bound reads
  hundreds of files and torches your context. Fix: scope the ask, or hand it
  to a subagent.

## 8. Quick checklist before merging anything

- [ ] Plan reviewed before implementation started (for anything non-trivial)
- [ ] Tests/build/lint run and passing — evidence shown, not just claimed
- [ ] Diff reviewed by a human, or by a fresh adversarial subagent at minimum
- [ ] No secrets, credentials, or API keys in the diff
- [ ] Auth/permissions/data-handling code specifically double-checked
- [ ] CLAUDE.md updated if this change introduces a new convention worth
      remembering

---

Sources: [Anthropic — Best practices for Claude Code](https://code.claude.com/docs/en/best-practices) ·
[Superblocks — Vibe Coding Best Practices](https://www.superblocks.com/blog/vibe-coding-best-practices) ·
[Superblocks — Vibe Coding Security](https://www.superblocks.com/blog/vibe-coding-security) ·
[Appwrite — Vibe Coding Security Best Practices](https://appwrite.io/blog/post/vibe-coding-security-best-practices)
