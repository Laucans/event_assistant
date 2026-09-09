#!/usr/bin/env bash
#
# agent-loop.sh — run the docs pipeline unattended.
#
# One `claude -p` process per stage, so every stage starts on the fresh
# context CLAUDE.md's workflow asks for. The sequence, and what each stage
# runs on, is the PIPELINE table below — that table is the design surface of
# this script.
#
# /code-review and /commit are not stages: /code runs the review at its
# step 6, and /code and /create-test each end in branch -> PR -> merge.
#
# Every stage is billed and the bill is written down: one row per stage in
# .llocal/agent-loop/costs.tsv, the real cost off the run's JSON envelope
# rather than an estimate. Read it before re-tuning the table.
#
# The loop stops rather than guesses — a task marked "needs you", an open
# item under "Before Claude starts", a stage that reports AGENT_LOOP_STOP,
# or a round that moves no task to DONE. Logs land in
# .llocal/agent-loop/<run-id>/ (gitignored).
#
# Resuming is the default. A halted round records which stages actually
# completed in .llocal/agent-loop/state, so re-running after you unblock
# something picks up at the next stage instead of re-doing an expensive
# /code that already merged. The record is scoped to one task and cleared
# when the task closes; --restart throws it away and runs the round from
# the top.
#
# Usage:
#   scripts/agent-loop.sh                 # spend the rounds budget
#   scripts/agent-loop.sh --rounds 1      # one task
#   scripts/agent-loop.sh --status        # what a re-run would resume from
#   scripts/agent-loop.sh --restart       # forget the completed stages
#   scripts/agent-loop.sh --dry-run       # write the prompts, call nothing
#   scripts/agent-loop.sh --costs         # what this loop has spent, by stage
#
# Env overrides: INTEGRATION_BRANCH, PERMISSION_MODE, MAX_ROUNDS, STAGES
# (run only these entries of PIPELINE), MODEL and EFFORT (force one value on
# every stage), ALLOW_DIRTY.

set -euo pipefail

# `claude -p` bills whatever the CLI is logged in as. An API key in the
# environment would silently move this loop off the subscription.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

cd "$(git rev-parse --show-toplevel)"

# --- the pipeline ----------------------------------------------------------
# One entry per stage, run in this order: `skill|model|effort`.
#
#   skill   — a skill in .claude/skills/, run as `/skill`.
#   model   — a `claude --model` value: the alias opus | sonnet | haiku, or a
#             full model id.
#   effort  — `claude --effort`: low | medium | high | xhigh | max.
#
# Add an entry to put a skill in the pipeline, delete one to take it out,
# reorder them to change the sequence. A stage with no `stage_<name>` wrapper
# further down runs generically — `/skill` plus the execution-context
# preamble — so a new entry needs nothing else to work.
#
# The models are split on where a bad answer gets paid for twice. /analyst
# writes the SPEC every later stage reads and /code writes the change itself:
# an error there comes back as rework. /create-test writes hermetic Vitest
# against a spec that already exists, and /archive-instructions moves two
# files and ticks a checkbox — neither is a reasoning problem. Retune from
# .llocal/agent-loop/costs.tsv, not from intuition.
#
# `planner` is the one entry that does not run in the per-task sequence: put
# it in the table and it fires when every task in the milestone is DONE, to
# open the next roadmap item. Leave it out and the loop stops there instead.
PIPELINE=(
  "analyst|opus|high"
  "code|opus|high"
  "create-test|sonnet|high"
  "archive-instructions|haiku|low"
)

INTEGRATION_BRANCH=${INTEGRATION_BRANCH:-main_agent}
PERMISSION_MODE=${PERMISSION_MODE:-bypassPermissions}
MAX_ROUNDS=${MAX_ROUNDS:-3}
STAGES=${STAGES:-}
MODEL=${MODEL:-}
EFFORT=${EFFORT:-}
ALLOW_DIRTY=${ALLOW_DIRTY:-0}
DRY_RUN=0
RESTART=0

MILESTONE=docs/current/CURRENT_MILESTONE.md
SPEC=docs/current/SPEC.md
TRACKING=docs/current/HUMAN_ACTION_TRACKING.md
STATE=.llocal/agent-loop/state
LEDGER=.llocal/agent-loop/costs.tsv

# --- reading the table -----------------------------------------------------
# "model|effort" for a stage, or nothing if the stage is not in the table.
pipeline_entry() {
  local entry
  for entry in "${PIPELINE[@]}"; do
    case $entry in "$1|"*) printf '%s' "${entry#*|}"; return 0 ;; esac
  done
  return 1
}

# In the table, and not filtered out for this run by --stages/STAGES.
stage_enabled() {
  pipeline_entry "$1" >/dev/null || return 1
  [ -z "$STAGES" ] && return 0
  case " $STAGES " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

# MODEL/EFFORT are the blunt override — one value for the whole run, for the
# rare "redo this round on sonnet and see" question.
stage_model() { local me; me=$(pipeline_entry "$1") || return 1; printf '%s' "${MODEL:-${me%%|*}}"; }
stage_effort() { local me; me=$(pipeline_entry "$1") || return 1; printf '%s' "${EFFORT:-${me##*|}}"; }

pipeline_summary() {
  local entry stage out=""
  for entry in "${PIPELINE[@]}"; do
    stage=${entry%%|*}
    stage_enabled "$stage" || continue
    out="$out -> $stage($(stage_model "$stage")/$(stage_effort "$stage"))"
  done
  printf '%s' "${out# -> }"
}

show_costs() {
  if [ ! -s "$LEDGER" ]; then
    echo "no cost ledger yet — $LEDGER is written as stages run"
    return 0
  fi
  python3 - "$LEDGER" <<'PY'
import collections, sys

rows = [l.split("\t") for l in open(sys.argv[1], encoding="utf-8").read().splitlines()[1:] if l]
by = collections.OrderedDict()
for r in rows:
    if len(r) < 12:
        continue
    agg = by.setdefault((r[4], r[11]), [0.0, 0])
    agg[0] += float(r[5] or 0)
    agg[1] += 1
print("%-22s %-16s %9s %5s %9s" % ("stage", "ran on", "total $", "runs", "avg $"))
for (stage, ran_on), (total, n) in by.items():
    print("%-22s %-16s %9.4f %5d %9.4f" % (stage, ran_on, total, n, total / n))
print("%-22s %-16s %9.4f %5d" % ("ALL", "", sum(v[0] for v in by.values()),
                                 sum(v[1] for v in by.values())))
PY
}

while [ $# -gt 0 ]; do
  case $1 in
    --rounds) MAX_ROUNDS=$2; shift 2 ;;
    --stages) STAGES=$2; shift 2 ;;
    --branch) INTEGRATION_BRANCH=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --effort) EFFORT=$2; shift 2 ;;
    --costs) show_costs; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --restart) RESTART=1; shift ;;
    --status)
      if [ -s "$STATE" ]; then
        echo "resume point (.llocal/agent-loop/state):"
        sed 's/^/  /' "$STATE"
        [ -f "$SPEC" ] && echo "  spec=$SPEC present — /analyst would be skipped"
      else
        echo "no resume point — the next run starts a round from the top"
      fi
      exit 0 ;;
    -h|--help) sed -n '2,38p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

RUN_ID=$(date +%Y%m%d-%H%M%S)
LOG_DIR=.llocal/agent-loop/$RUN_ID
mkdir -p "$LOG_DIR"
STEP=00

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_DIR/run.log"; }

notify() {
  command -v osascript >/dev/null 2>&1 || return 0
  local msg=${1//\"/}
  osascript -e "display notification \"${msg:0:200}\" with title \"agent-loop\"" >/dev/null 2>&1 || true
}

halt() {
  log "STOP — $*"
  log "logs: $LOG_DIR"
  notify "$*"
  exit 1
}

# --- milestone parsing -----------------------------------------------------
# Emits one line per task: <n> TAB done|todo TAB human|auto TAB <title>.
# A task heading is the paragraph opening with `**<n>.` under `# Tasks`; it
# may wrap over several lines, as task 2's `_(needs you: ...)_` does.
milestone_tasks() {
  python3 - "$MILESTONE" <<'PY'
import re, sys

txt = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'^#\s+Tasks\s*$(.*?)(?=^##\s|\Z)', txt, re.M | re.S)
for block in re.split(r'^(?=\*\*\d+\.)', m.group(1) if m else '', flags=re.M):
    n = re.match(r'^\*\*(\d+)\.', block)
    if not n:
        continue
    head = block.split('\n\n', 1)[0]
    title = re.sub(r'^\d+\.\s*', '', re.sub(r'\s+', ' ', head.split('**')[1])).strip()
    print('%s\t%s\t%s\t%s' % (n.group(1),
                              'done' if 'DONE' in head else 'todo',
                              'human' if 'needs you' in head else 'auto',
                              title))
PY
}

tasks_todo() { milestone_tasks | awk -F'\t' '$2 == "todo"'; }
count_done() { milestone_tasks | awk -F'\t' '$2 == "done"' | wc -l | tr -d ' '; }

# Unticked items under "Before Claude starts" — the ones /code treats as
# blocking by construction. Items the analyst marked (Optional) are advice,
# not prerequisites, so they do not block. Read-only: the ticks are the
# human's to write.
open_human_actions() {
  [ -f "$TRACKING" ] || return 0
  python3 - "$TRACKING" <<'PY'
import re, sys

txt = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'^##\s+Before Claude starts\s*$(.*?)(?=^##\s|\Z)', txt, re.M | re.S)
for line in (m.group(1) if m else '').splitlines():
    s = line.strip()
    if s.startswith('- [ ]') and not re.search(r'\(optional\)', s, re.I):
        print(re.sub(r'[*_]+', '', s[5:]).strip())
PY
}

# --- stages ----------------------------------------------------------------
preamble() {
  sed "s|@BRANCH@|$INTEGRATION_BRANCH|g" <<'EOS'

--- EXECUTION CONTEXT (injected by scripts/agent-loop.sh) ---
You are running head-less in an unattended loop (`claude -p`). Nobody will
read this output before the run ends and nobody can answer a question.
These rules override the skill's interactive stopping points:

1. Where the skill waits for a go-ahead or a confirmation (/code steps 2
   and 3, /archive-instructions steps 3 and 7), write your findings into
   your reply and carry on. Reporting stays mandatory; waiting does not.
2. Where the skill says to ask because a choice is genuinely ambiguous, do
   not guess. Stop, change nothing further, and end your reply with the one
   line `AGENT_LOOP_STOP: <one-line reason>`. The loop halts and a human
   picks it up. Stopping is a correct outcome, not a failure.
3. The integration branch for this run is `@BRANCH@`. Wherever a skill says
   `main` as the PR base or the branch-off point, read `@BRANCH@`: branch
   off it, and `gh pr create --base @BRANCH@`. The rest of CLAUDE.md's
   Repository etiquette stands unchanged — branch -> PR ->
   `gh pr merge --rebase`, and never a direct push.
4. Stage by name, never `git add -A`. The tree may carry unrelated
   in-flight work that is not yours to commit.
5. Do not run another pipeline stage yourself, and do not /clear. The loop
   runs one process per stage.
6. End your reply with `AGENT_LOOP_OK: <one-line summary>` if the stage
   completed, or `AGENT_LOOP_STOP: <reason>` if it did not.
--- END EXECUTION CONTEXT ---
EOS
}

# --- resume state ----------------------------------------------------------
# Which stages of the current task have actually completed. Survives a halt,
# so unblocking something and re-running does not re-run a /code that already
# merged. Scoped to one task: a different task resets it.
state_task() {
  [ -f "$STATE" ] || return 0
  sed -n '1s/^task=//p' "$STATE"
}

# A dry run reads the state — so it previews the real skips — but never
# writes it, or previewing would destroy the resume point it is describing.
state_open() {
  [ "$DRY_RUN" = 1 ] && return 0
  mkdir -p "$(dirname "$STATE")"
  printf 'task=%s\n' "$1" > "$STATE"
}

state_mark() { printf 'stage=%s\n' "$1" >> "$STATE"; }

# $task_key is the round's task, set by the loop. Matching it here keeps a
# dry run — which cannot rewrite the file — from previewing another task's
# skips as if they were this one's.
state_done() {
  [ -f "$STATE" ] && [ "$(state_task)" = "$task_key" ] && grep -qx "stage=$1" "$STATE"
}
state_clear() { [ "$DRY_RUN" = 1 ] || rm -f "$STATE"; }

# run_stage, but only once per task across runs.
run_stage_once() {
  local stage=$1 extra=${2:-}
  if state_done "$stage"; then
    log "/$stage already completed for this task — skipping (--restart to force)"
    return 0
  fi
  run_stage "$stage" "$extra"
  # A dry run executes nothing, so it must not claim a stage as done.
  [ "$DRY_RUN" = 1 ] || state_mark "$stage"
}

run_stage() {
  local stage=$1 extra=${2:-} model effort prompt log_file json_file rc cost
  model=$(stage_model "$stage")
  effort=$(stage_effort "$stage")
  log_file="$LOG_DIR/${STEP}-${stage}.log"
  json_file="$LOG_DIR/${STEP}-${stage}.json"
  prompt="/$stage"$'\n'"$(preamble)"
  [ -n "$extra" ] && prompt="$prompt"$'\n'"$extra"

  if [ "$DRY_RUN" = 1 ]; then
    printf '%s\n' "$prompt" > "$log_file"
    log "dry-run /$stage ($model, effort $effort) — prompt written to $log_file"
    return 0
  fi

  log "/$stage — $model, effort $effort ..."
  set +e
  claude -p "$prompt" --permission-mode "$PERMISSION_MODE" \
    --model "$model" --effort "$effort" --output-format json \
    > "$json_file" 2>&1
  rc=$?
  set -e

  # The envelope carries both the stage's answer and what it really cost, so
  # it is what decides — `claude -p` exits 0 on a quota message too, and this
  # loop used to treat that as a completed stage. The raw file stays either
  # way; $log_file holds the answer alone, as before.
  if ! parse_run "$json_file" "$stage" "$model/$effort" > "$log_file"; then
    tail -c 1000 "$json_file" >&2 || true
    # "You've hit your session limit" is what the CLI actually prints when the
    # subscription window is spent — the observed shape, not a guess.
    if grep -qiE 'usage limit|rate limit|session limit|limit reached|too many requests' "$json_file"; then
      halt "quota reached during /$stage — resume later ($json_file)"
    fi
    halt "/$stage produced no usable result (claude exited $rc) — $json_file"
  fi

  cost=$(tail -n 1 "$LEDGER" | cut -f6)
  log "/$stage finished — \$$cost"

  if grep -q '^AGENT_LOOP_STOP:' "$log_file"; then
    halt "$(grep -m1 '^AGENT_LOOP_STOP:' "$log_file") (/$stage, $log_file)"
  fi
  grep -m1 '^AGENT_LOOP_OK:' "$log_file" | tee -a "$LOG_DIR/run.log" \
    || log "/$stage produced no AGENT_LOOP_OK marker — relying on the structural checks"
}

# Prints the stage's answer on stdout, appends its real cost to the ledger,
# and exits non-zero when the run did not actually produce one.
parse_run() {
  python3 - "$1" "$LEDGER" "$RUN_ID" "$STEP" "${task_key:-}" "$2" "$3" <<'PY'
import datetime, json, os, sys

path, ledger, run_id, step, task, stage, ran_on = sys.argv[1:8]
raw = open(path, encoding="utf-8").read()

try:
    d = json.loads(raw)
except Exception:
    sys.stderr.write("no JSON envelope — claude stopped before answering: %s\n"
                     % " ".join(raw.split())[:300])
    sys.exit(1)

usage = d.get("usage") or {}
fresh = not os.path.exists(ledger)
with open(ledger, "a", encoding="utf-8") as fh:
    if fresh:
        fh.write("when\trun\tround\ttask\tstage\tcost_usd\tturns"
                 "\tduration_ms\tin\tout\tsession\tran_on\n")
    fh.write("%s\t%s\t%s\t%s\t%s\t%.6f\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
        datetime.datetime.now().isoformat(timespec="seconds"), run_id, step,
        " ".join(task.split()), stage,
        d.get("total_cost_usd") or 0.0, d.get("num_turns"), d.get("duration_ms"),
        usage.get("input_tokens"), usage.get("output_tokens"),
        d.get("session_id"), ran_on))

if d.get("is_error") or d.get("subtype") != "success":
    sys.stderr.write("run failed (%s): %s\n"
                     % (d.get("subtype"), " ".join((d.get("result") or "").split())[:300]))
    sys.exit(1)

text = (d.get("result") or "").strip()
if not text:
    sys.stderr.write("run returned an empty result\n")
    sys.exit(1)
print(text)
PY
}

# --- per-stage wrappers ----------------------------------------------------
# Only a stage whose contract is more than "run the skill" needs one. The
# dispatcher in the round below calls stage_<name> when it exists — with `-`
# spelled `_` — and falls back to run_stage_once for everything else, which
# is what lets a new PIPELINE entry work with no other change.
#
# They read $num, $title and $before from the round.

# A SPEC left over from an interrupted run is the resume point: keep it rather
# than letting /analyst overwrite the record of what was asked.
stage_analyst() {
  if [ -f "$SPEC" ]; then
    log "$SPEC already exists — skipping /analyst (resuming a previous run)"
    return 0
  fi
  run_stage analyst "Take task $num (\"$title\") from docs/current/CURRENT_MILESTONE.md. The
interview in step 3 of the skill cannot happen — no human is reachable.
Answer each question you would have asked from docs/PROJECT.md,
docs/ARCHITECTURE.md and the repo itself, and record every answer you had
to assume under a \`## Assumptions (autonomous run)\` heading in the SPEC.
If an assumption would make the task useless or harmful when wrong — a
paid service, a schema decision the later tasks depend on, a credential
only the human holds — that is ambiguity, not a default: AGENT_LOOP_STOP
instead of guessing."
  [ -f "$SPEC" ] || halt "/analyst did not produce $SPEC"
}

stage_archive_instructions() {
  # Deliberately run_stage, not run_stage_once. Archiving is the last stage,
  # and the post-conditions below are what say it worked: marking it done
  # before checking them would let a failed archive be skipped on every
  # re-run, halting on the same post-condition forever. When it does succeed
  # the task closes and the whole record is cleared, so there is no resume
  # case for it to miss.
  run_stage archive-instructions "Archive task $num (\"$title\") only."
  [ -f "$SPEC" ] && halt "/archive-instructions left $SPEC in place — the task did not close"
  [ "$(count_done)" -gt "$before" ] \
    || halt "round $round moved no task to DONE in $MILESTONE — stopping rather than looping on the same task"
}

# The ticks in the tracking file are what gate the building stages, and they
# are only the right ticks once /analyst has written the list for THIS task —
# so this runs between the analyst and whatever comes after it, once a round.
human_gate() {
  local blocked
  # An absent file is not an absent blocker: it is gitignored, so a fresh
  # clone has none, and reading no items out of it would let the loop build
  # straight through prerequisites nobody has done.
  if [ ! -f "$TRACKING" ]; then
    halt "cannot check the blocking human actions — $TRACKING is absent (gitignored, and written by /analyst). Run /analyst for task $num, or restore the file, before letting the loop build."
  fi
  blocked=$(open_human_actions)
  [ -n "$blocked" ] || return 0
  log "open items under 'Before Claude starts':"
  printf '  - %s\n' "$blocked" | tee -a "$LOG_DIR/run.log"
  halt "task $num needs you first — tick the items in $TRACKING, then re-run (the spec is kept)"
}

# --- preflight -------------------------------------------------------------
preflight() {
  command -v claude >/dev/null 2>&1 || halt "claude CLI not on PATH"
  command -v gh >/dev/null 2>&1 || halt "gh CLI not on PATH"
  gh auth status >/dev/null 2>&1 || halt "gh is not authenticated — run: gh auth login"
  [ -f "$MILESTONE" ] || halt "$MILESTONE is missing — nothing to work from"

  # A typo in PIPELINE costs nothing to find here and a whole stage to find
  # after `claude -p` has been billed for it.
  local entry stage effort
  for entry in "${PIPELINE[@]}"; do
    case $entry in
      *'|'*'|'*) ;;
      *) halt "PIPELINE entry '$entry' is not skill|model|effort" ;;
    esac
    stage=${entry%%|*}
    effort=${entry##*|}
    [ -f ".claude/skills/$stage/SKILL.md" ] \
      || halt "PIPELINE names /$stage but .claude/skills/$stage/SKILL.md does not exist"
    case $effort in
      low|medium|high|xhigh|max) ;;
      *) halt "PIPELINE entry '$entry' — effort '$effort' is not low|medium|high|xhigh|max" ;;
    esac
  done

  git rev-parse --verify --quiet "$INTEGRATION_BRANCH" >/dev/null \
    || halt "branch $INTEGRATION_BRANCH does not exist — run: git branch $INTEGRATION_BRANCH origin/main"

  local current
  current=$(git symbolic-ref --short HEAD)
  [ "$current" = "$INTEGRATION_BRANCH" ] \
    || halt "on branch $current — run: git checkout $INTEGRATION_BRANCH"

  git ls-remote --exit-code --heads origin "$INTEGRATION_BRANCH" >/dev/null 2>&1 \
    || halt "origin has no $INTEGRATION_BRANCH — run: git push -u origin $INTEGRATION_BRANCH"

  # Without this the PRs the stages open get no `ci` check, and the
  # `gh pr checks` the skills wait on never resolves.
  grep -q "$INTEGRATION_BRANCH" .github/workflows/ci.yml \
    || halt ".github/workflows/ci.yml does not trigger on $INTEGRATION_BRANCH"

  if [ "$ALLOW_DIRTY" != 1 ] && [ -n "$(git status --porcelain)" ]; then
    git status --short
    halt "working tree is dirty — commit, stash, or re-run with ALLOW_DIRTY=1"
  fi

  log "run $RUN_ID — branch $INTEGRATION_BRANCH, $MAX_ROUNDS round(s)"
  log "pipeline: $(pipeline_summary)"
  log "permission mode: $PERMISSION_MODE (the PreToolUse hooks in .claude/settings.json still apply)"
}

# --- loop ------------------------------------------------------------------
preflight

for round in $(seq 1 "$MAX_ROUNDS"); do
  STEP=$(printf '%02d' "$round")

  todo=$(tasks_todo)

  if [ -z "$todo" ]; then
    log "every task in $MILESTONE is DONE — opening the next roadmap item"
    if ! stage_enabled planner; then
      log "no planner entry in PIPELINE — nothing left to do"
      break
    fi
    run_stage planner "Every task in docs/current/CURRENT_MILESTONE.md is DONE. Take the first
unchecked item in docs/ROADMAP.md — do not ask which one. Step 3 of the
skill applies in full: verify the ground truth in the repo, and if a
dependency the item builds on is not actually there, AGENT_LOOP_STOP with
what is missing rather than planning on top of it."
    [ -n "$(tasks_todo)" ] || halt "/planner produced no open task in $MILESTONE"
    continue
  fi

  # First line only, without piping into head: `set -o pipefail` would turn
  # head's early close into a SIGPIPE failure for the parser upstream.
  IFS=$'\t' read -r num _state kind title <<< "${todo%%$'\n'*}"
  log "round $round/$MAX_ROUNDS — task $num: $title [$kind]"

  # `needs you` says the task has human prerequisites, not that it can never
  # run. The ticks in the tracking file are the gate, and they are checked
  # below — once /analyst has written the list for THIS task.
  if [ "$kind" = human ]; then
    log "task $num is marked 'needs you' — the ticks in $TRACKING decide, not the marker"
  fi

  # Resume, unless this is a different task than the one the state describes
  # or --restart was passed.
  task_key="$num|$title"
  if [ "$RESTART" = 1 ]; then
    log "--restart — forgetting the completed stages for this task"
    state_open "$task_key"
    RESTART=0
  elif [ "$(state_task)" != "$task_key" ]; then
    state_open "$task_key"
  else
    log "resuming task $num — already completed: $(sed -n 's/^stage=/ /p' "$STATE" | tr -d '\n' | sed 's/^ *//')"
  fi

  before=$(count_done)
  gate_pending=1

  # The table, in order. Everything task-specific lives in the wrappers above,
  # so this stays the one place that decides what runs and in what order.
  for entry in "${PIPELINE[@]}"; do
    stage=${entry%%|*}
    [ "$stage" = planner ] && continue   # rollover only, handled above
    stage_enabled "$stage" || continue

    if [ "$stage" != analyst ] && [ "$gate_pending" = 1 ]; then
      human_gate
      gate_pending=0
    fi

    fn="stage_${stage//-/_}"
    if declare -f "$fn" >/dev/null; then "$fn"; else run_stage_once "$stage"; fi
  done

  # The task closed: the resume record has nothing left to describe.
  state_clear
  log "round $round done — $(count_done) task(s) DONE"
done

log "loop finished — logs in $LOG_DIR"
[ "$DRY_RUN" = 1 ] || show_costs | sed 's/^/  /' | tee -a "$LOG_DIR/run.log"
notify "loop finished: $(count_done) task(s) DONE"
