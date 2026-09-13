# pipeline

The unattended runner for this project. It spends a budget of Claude Code
sessions against GitHub issues, one task per round. Mechanics — the journal,
the exit codes, the cost ledger, the layering rules — live in
`pipeline/INTERNALS.md`.

## One round

    /business-analyst  ->  /code  ->  /create-test

Three paid stages, one Claude Code session each, on your subscription. The
round takes the next ready task and stops rather than guess: an open
dependency, an ambiguous spec, or a stage answering `AGENT_LOOP_STOP` ends
the run with a reason and an exit code an outer scheduler can read.

## Where the state lives

GitHub issues. The repo carries no task tracking of its own — no milestone
document, no spec file, no checkbox list.

    [pipeline:roadmap]            a roadmap item
      └─ [pipeline:milestone]     Problem / Goals / Approach / Out of scope
           ├─ [pipeline:human]    what you have to do yourself
           └─ [pipeline:agent]    the SPEC, written by /business-analyst
                                  + [pipeline:waiting-merge] once shipped

Five rules follow from that shape, and each replaces something the old
markdown pipeline did by hand:

- **Order comes from `blocked_by`**, not from position in a document. The next
  task is any open `pipeline:agent` issue that carries `pipeline:ready` and
  whose dependencies are all closed. `/planner` only ever writes a chain
  today, but the runner already reads a DAG — running two tasks at once later
  is a scheduler change, not a data migration.
- **The human gate is a dependency.** A `pipeline:human` issue blocking an
  agent task is the whole mechanism; there is no second one.
- **Nothing runs without `pipeline:ready`.** `/planner` creates every issue
  without it and you open the tap task by task, so a run that opens a
  milestone stops right after. That is deliberate: no plan reaches a paid
  stage before you have read it.
- **Delivered is not done.** When a merged PR on `main_agent` carries
  `Closes #N`, the round labels the issue `pipeline:waiting-merge` and
  leaves it open. It will never be picked up again, and it stops blocking
  the next task — but it stays open, because the work is on the integration
  branch and not in `main`. No stage is believed on its word: the evidence
  is a merged PR, not a stage saying so.
- **You close it**, by merging `main_agent` into `main`. GitHub will not do
  it for you: it only auto-closes on the default branch, and a rebase merge
  does not carry the PR body's `Closes` line into the commits. When every
  task is waiting on you, the loop stops and says so rather than opening
  the next milestone.

Each stage is handed the milestone body and its own issue body in the prompt.
The runner injects both, so a session cannot start without its scope.

## Setup

Beyond the venv (see `INTERNALS.md`), the seven labels have to exist. Preflight
refuses to run without them and prints the exact commands:

    gh label create pipeline:roadmap
    gh label create pipeline:milestone
    gh label create pipeline:agent
    gh label create pipeline:human
    gh label create pipeline:ready
    gh label create pipeline:spec-written
    gh label create pipeline:waiting-merge

## Commands

    scripts/agent-loop                 spend the round budget
    scripts/agent-loop --rounds 1      one task
    scripts/agent-loop --status        what a re-run would resume from
    scripts/agent-loop --costs         what the loop has spent, by stage
    scripts/agent-loop --dry-run       write the prompts, call nothing
    scripts/agent-loop migrate         one-shot: markdown docs -> issues
    scripts/pr-review <pr>             the advisory review of one PR

`--help` carries the environment overrides and the exit codes. Two tests check
that no variable the code reads is missing from it, or from `.env.example`.

`migrate` is idempotent and `--dry-run` prints every issue it would create
without writing anything. It also deletes `docs/ROADMAP.md` and
`docs/current/`, so read the dry run first.

## What is deliberately not in issues

- `docs/PROJECT.md`, `docs/ARCHITECTURE.md` — inputs, not work in flight.
- `docs/archives/` — frozen. Three tasks were archived under the old markdown
  pipeline and nothing is added to it.
- `.llocal/agent-loop/` — the resume point and the cost ledger. Per-run
  mechanics, local and gitignored, which is why `--costs` answers in under a
  tenth of a second and `--status` needs GitHub only when it has a live issue
  to report on.

## Constraints that bite

- **The loop needs `gh` authenticated and `origin` reachable.** It always
  did — three preflight gates check it — so state living in issues adds no
  new dependency, only more calls.
- **An unreadable issue list halts the run.** It is never read as "no tasks":
  that answer would trigger a rollover and spend an opus run opening a
  roadmap item nobody needed.
- **Issues on this repo are public**, including `pipeline:human` bodies and
  their comments. Keep credentials and dashboard URLs out of them.
