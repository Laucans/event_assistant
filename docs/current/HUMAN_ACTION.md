# Human actions — `docs/current/SPEC.md` (Repo & app scaffold)

Things only you can do for the **current** spec. Everything else in
`docs/current/SPEC.md` is Claude's to execute.

Rewrite this file when `docs/current/SPEC.md` is replaced by the next task's spec —
it tracks one spec at a time, like `docs/current/CURRENT_MILESTONE.md`.

This spec is deliberately local-only (scaffold → first commit), so the list
is short. **No accounts need creating and nothing needs paying for.**

---

## Before Claude starts

- [x] **Decide which git identity this repo's commits carry.**
      Your global config is `laurent@marigold.dev`; the address on this
      Claude account is `laurent@groupe-canix.ca`. Either confirm the global
      one is right, or tell Claude to set a repo-local `user.email`.
      _Human-only: Claude can't know which identity you want on a public
      GitHub repo — and it's baked into the first commit, so changing it
      later means rewriting history._ -> CONFIRMED, git setup with `laurent@groupe-canix.ca`

- [x] _(Optional, saves clicking)_ **Pre-allowlist the commands** via
      `/permissions`, since `.claude/settings.json` currently has an empty
      allow list. The implementation session will run roughly:
      `npx create-next-app`, `npx shadcn`, `npm install`, `npm run *`,
      `npx vitest`, `git init/add/commit`.
      _Skip this if you'd rather approve each one as it comes._

## While Claude works

- [ ] **Approve the permission prompts** as they appear (unless you did the
      step above). Nothing here is destructive — the one deletion is
      `read-docs-spec-md-and-tell-zazzy-wind.md`, a superseded plan file,
      removed before git is initialized.

- [ ] **Watch for the non-empty-directory step.** `create-next-app` may
      refuse to scaffold over the existing `docs/`, `src/`, `tests/`, and
      root markdown files. The spec's fallback is to scaffold into a temp dir
      and merge by hand. If you're asked to choose, **never accept an
      overwrite** of `README.md`, `CLAUDE.md`, `Human_guidelines.md`, or
      `.claude/`.

## Before calling it done

- [ ] **Open `http://localhost:3000` yourself** once `npm run dev` is up.
      Claude can confirm the server responds; only you can confirm the page
      looks right.

- [ ] **Review the diff** — `Human_guidelines.md` §6 and the §8 checklist.
      This is the first commit, so the things worth actually eyeballing are:
      `.gitignore` contents, that no `.env*` or `node_modules` is staged
      (`git status` before committing), and the `package.json` dependency
      list.

- [ ] **Confirm the spec's verification section passed with real output** —
      `npm run dev`, `lint`, `typecheck`, `build`, `test`, plus one commit on
      branch `main`. "Looks done" isn't verification (`Human_guidelines.md`
      §1); ask for the terminal output if it wasn't shown.

---

## Explicitly NOT needed yet

Don't create these now — they belong to later tasks in
`docs/current/CURRENT_MILESTONE.md` and doing them early just adds unused accounts:

| Action                                           | Needed for                                                  |
| ------------------------------------------------ | ----------------------------------------------------------- |
| `gh auth login`                                  | Next task — GitHub repo & CI (milestone steps 5–6)          |
| Create a GitHub account/repo                     | Next task — Claude runs `gh repo create` once you're authed |
| Create a Supabase account + project              | Milestone steps 7–9                                         |
| Create a Vercel account + project                | Milestone step 10                                           |
| Cloudflare Tunnel to the local Qwen/MLX endpoint | Much later — the chat task in `docs/ROADMAP.md`             |
| Mistral API key                                  | Much later — the scraper task                               |

Node v24.16 and npm 11.13 are already installed — nothing to do there.
