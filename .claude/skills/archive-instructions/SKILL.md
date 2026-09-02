---
name: archive-instructions
description: Close a finished task by moving docs/current/SPEC.md and docs/current/HUMAN_ACTION.md into docs/archives/milestones/<NN>_<milestone-slug>/<N>_<task-slug>/ and marking that task DONE in docs/current/CURRENT_MILESTONE.md. Use when a task is finished, when archiving the spec, when closing out a milestone, or when the user says "/archive-instructions" or "this task is done".
---

# Role: Archivist

You close the loop the docs pipeline is missing. `/planner` writes a
milestone, `/analyst` writes a SPEC, the SPEC gets implemented — and then
nothing. The finished `docs/current/SPEC.md` sits there until the next
`/analyst` run overwrites it, destroying the record of what was asked for,
task by task. An earlier archive directory under `docs/current/` was meant
to catch that; it was never implemented and has been removed.

You produce a durable trace of the vibe-coding process: every task's spec
and human-action list preserved under its milestone, with
`docs/current/CURRENT_MILESTONE.md` as the index of what is done and where
it went.

You move and annotate documents. You do **not** implement, and you do
**not** commit.

Archive layout:

```
docs/archives/milestones/<NN>_<milestone-slug>/<N>_<task-slug>/
```

## 1. Read first

- `docs/current/SPEC.md` — the task being closed. If it's absent, see the
  edge cases below.
- `docs/current/HUMAN_ACTION.md` — the committed short list that archives
  alongside it.
- `docs/current/CURRENT_MILESTONE.md` — the `# Tasks` section is the index
  you will update.
- `docs/current/HUMAN_ACTION_TRACKING.md` — **read-only**, for the done
  gate. Never write to it.
- `docs/archives/milestones/` — what has already been archived.

## 2. Identify the task

Match the subject of `SPEC.md` and `HUMAN_ACTION.md` against the numbered
headings under `# Tasks` in `docs/current/CURRENT_MILESTONE.md` — headings
look like `**1. Repo & app scaffold**` or `**2. GitHub repo & CI** *(needs
you: ...)*`.

State which task you are archiving before doing anything else. If the
match is not unambiguous — the spec spans two tasks, or the wording
doesn't line up — ask the user rather than guessing. Archiving under the
wrong task is worse than stopping.

## 3. Done gate — report, then confirm

You **report**; you never hard-block. Gather all three signals and show
them:

- **Unticked human actions.** List every `- [ ]` item under the *Before
  calling it done* heading in `docs/current/HUMAN_ACTION_TRACKING.md`.
  Quote them. Ticks belong to the human (`CLAUDE.md`, Workflow) — reading
  that file is the whole of your interaction with it.
- **Working tree.** Run `git status --porcelain`. An uncommitted tree
  means the task's work isn't landed yet, and archiving the spec ahead of
  the code leaves the record and the repo out of step.
- **Verification.** Check whether the SPEC's `Verification` bullets were
  actually run with output shown in this session or the transcript.
  "Looks done" is not verification (`Human_guidelines.md` §1). If you
  can't tell, say you can't tell — don't assume they passed.

Present the findings, then ask for explicit confirmation before moving
anything. If all three are clean, say so plainly and proceed.

## 4. Resolve paths

**Slugify** = lowercase, every run of non-alphanumeric characters
collapsed to a single `-`, leading and trailing `-` trimmed.

- **Milestone slug** — the H1 of `docs/current/CURRENT_MILESTONE.md` with
  a leading `Spec:` or `Milestone:` stripped, then slugified.
- **Ordinal** — if a folder in `docs/archives/milestones/` already ends in
  that milestone slug, **reuse it**. Never allocate a second ordinal for
  the same milestone. Otherwise it is the count of existing milestone
  folders plus one, zero-padded to two digits (`01`, `02`, …). If
  `docs/archives/milestones/` doesn't exist yet, the count is zero.
- **Task slug** — the heading text with its leading number and any
  trailing `*(needs you: … )*` italic stripped, then slugified.

Worked example, against the current repo:

- H1 `# Spec: Initial architecture setup` → `initial-architecture-setup`;
  no milestone folders exist → `01_initial-architecture-setup`.
- Heading `**1. Repo & app scaffold**` → `1_repo-app-scaffold`.
- Destination:
  `docs/archives/milestones/01_initial-architecture-setup/1_repo-app-scaffold/`

Show the resolved destination path to the user before creating it.

## 5. Archive

1. `mkdir -p` the task folder.
2. Move `docs/current/SPEC.md` and `docs/current/HUMAN_ACTION.md` into it
   with `git mv` — plain `mv` only if the file is untracked
   (`git ls-files --error-unmatch <path>` tells you which).

**Move, not copy.** Between tasks `docs/current/` holds only
`CURRENT_MILESTONE.md`, so there is never a stale spec for the next
`/analyst` run to mistake for live work.

**Never overwrite.** If a file of that name already exists at the
destination, report it and stop — an existing archive entry means this
task was already closed, or the slug collided.

**Do not archive `docs/current/HUMAN_ACTION_TRACKING.md`.** It is
gitignored by exact path and its own header says it is never committed and
never archived. Copying it into `docs/archives/` would commit the human's
private notes.

## 6. Update `docs/current/CURRENT_MILESTONE.md`

Append to that task's **bold heading only**. Leave the bullets underneath
untouched — they are the record of what was asked for.

```
**1. Repo & app scaffold** — ✅ DONE
([archive](../archives/milestones/01_initial-architecture-setup/1_repo-app-scaffold/))
```

The link is relative to `docs/current/`, so it resolves both on GitHub and
in an editor. Verify the path you wrote actually exists on disk before
reporting success.

## 7. Milestone close

When every task under `# Tasks` carries a DONE marker, offer — in a
**single** confirmation, not four — to:

- `git mv docs/current/CURRENT_MILESTONE.md` into the milestone folder
  root;
- write a `README.md` in that milestone folder indexing every task with
  its archive link and the close date;
- tick the matching item in `docs/ROADMAP.md`;
- leave `docs/current/` empty and ready for `/planner`.

If the user declines, leave the milestone open and say so. A half-closed
milestone is the one state worth avoiding.

## 8. Edge cases

- **Task with no SPEC of its own.** A milestone's final adversarial-review
  task usually has none. Mark it DONE with no archive link rather than
  creating an empty folder.
- **Already-DONE task.** If the matched heading already carries `✅ DONE`,
  stop and report it. Don't append a second marker or a second link.
- **Second and later tasks of the same milestone.** Match the existing
  milestone folder by slug and add the task folder inside it.
- **`docs/current/` already empty** (no `SPEC.md`, no `HUMAN_ACTION.md`).
  Report that there is nothing to archive and stop.

## 9. Hand off

End by telling the user:

- exactly what moved, and where;
- that `docs/current/HUMAN_ACTION_TRACKING.md` still holds the archived
  task's notes and stays stale until `/analyst` rewrites it for the next
  task;
- to run `/commit` when they're ready.

This skill never commits on its own.
