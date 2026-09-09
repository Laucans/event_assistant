#!/usr/bin/env bash
#
# agent-loop.sh — run the docs pipeline unattended.
#
# One `claude -p` process per stage, so every stage starts on the fresh
# context CLAUDE.md's workflow asks for. Per round:
#
#   /analyst -> /code -> /create-test -> /archive-instructions
#
# and once every task in CURRENT_MILESTONE.md is DONE, /planner opens the
# next roadmap item and the loop keeps going.
#
# /code-review and /commit are not stages: /code runs the review at its
# step 6, and /code and /create-test each end in branch -> PR -> merge.
#
# The loop stops rather than guesses — a task marked "needs you", an open
# item under "Before Claude starts", a stage that reports AGENT_LOOP_STOP,
# or a round that moves no task to DONE. Logs land in
# .llocal/agent-loop/<run-id>/ (gitignored).
#
# Usage:
#   scripts/agent-loop.sh                 # spend the rounds budget
#   scripts/agent-loop.sh --rounds 1      # one task
#   scripts/agent-loop.sh --dry-run       # write the prompts, call nothing
#
# Env overrides: INTEGRATION_BRANCH, PERMISSION_MODE, MAX_ROUNDS, STAGES,
# MODEL, ALLOW_DIRTY.

set -euo pipefail

# `claude -p` bills whatever the CLI is logged in as. An API key in the
# environment would silently move this loop off the subscription.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

cd "$(git rev-parse --show-toplevel)"

INTEGRATION_BRANCH=${INTEGRATION_BRANCH:-main_agent}
PERMISSION_MODE=${PERMISSION_MODE:-bypassPermissions}
MAX_ROUNDS=${MAX_ROUNDS:-3}
STAGES=${STAGES:-"analyst code create-test archive-instructions"}
MODEL=${MODEL:-}
ALLOW_DIRTY=${ALLOW_DIRTY:-0}
DRY_RUN=0

MILESTONE=docs/current/CURRENT_MILESTONE.md
SPEC=docs/current/SPEC.md
TRACKING=docs/current/HUMAN_ACTION_TRACKING.md

while [ $# -gt 0 ]; do
  case $1 in
    --rounds) MAX_ROUNDS=$2; shift 2 ;;
    --stages) STAGES=$2; shift 2 ;;
    --branch) INTEGRATION_BRANCH=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
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

stage_enabled() { case " $STAGES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

run_stage() {
  local stage=$1 extra=${2:-} prompt log_file
  log_file="$LOG_DIR/${STEP}-${stage}.log"
  prompt="/$stage"$'\n'"$(preamble)"
  [ -n "$extra" ] && prompt="$prompt"$'\n'"$extra"

  if [ "$DRY_RUN" = 1 ]; then
    printf '%s\n' "$prompt" > "$log_file"
    log "dry-run /$stage — prompt written to $log_file"
    return 0
  fi

  log "/$stage ..."
  if ! claude -p "$prompt" --permission-mode "$PERMISSION_MODE" ${MODEL:+--model "$MODEL"} \
       > "$log_file" 2>&1; then
    tail -n 20 "$log_file" || true
    if grep -qiE 'usage limit|rate limit|limit reached|too many requests' "$log_file"; then
      halt "quota reached during /$stage — resume later ($log_file)"
    fi
    halt "/$stage exited non-zero — $log_file"
  fi
  if grep -q '^AGENT_LOOP_STOP:' "$log_file"; then
    halt "$(grep -m1 '^AGENT_LOOP_STOP:' "$log_file") (/$stage, $log_file)"
  fi
  grep -m1 '^AGENT_LOOP_OK:' "$log_file" | tee -a "$LOG_DIR/run.log" \
    || log "/$stage produced no AGENT_LOOP_OK marker — relying on the structural checks"
}

# --- preflight -------------------------------------------------------------
preflight() {
  command -v claude >/dev/null 2>&1 || halt "claude CLI not on PATH"
  command -v gh >/dev/null 2>&1 || halt "gh CLI not on PATH"
  gh auth status >/dev/null 2>&1 || halt "gh is not authenticated — run: gh auth login"
  [ -f "$MILESTONE" ] || halt "$MILESTONE is missing — nothing to work from"

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

  log "run $RUN_ID — branch $INTEGRATION_BRANCH, $MAX_ROUNDS round(s), stages: $STAGES"
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
      log "planner is not in STAGES — nothing left to do"
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

  before=$(count_done)

  # A SPEC left over from an interrupted run is the resume point: keep it
  # rather than letting /analyst overwrite the record of what was asked.
  if [ -f "$SPEC" ]; then
    log "$SPEC already exists — skipping /analyst (resuming a previous run)"
  elif stage_enabled analyst; then
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
  fi

  # /analyst has just written the tracking file for THIS task, so this is
  # the first moment its blocking items are the right ones to read.
  blocked=$(open_human_actions)
  if [ -n "$blocked" ]; then
    log "open items under 'Before Claude starts':"
    printf '  - %s\n' "$blocked" | tee -a "$LOG_DIR/run.log"
    halt "task $num needs you first — tick the items in $TRACKING, then re-run (the spec is kept)"
  fi

  stage_enabled code && run_stage code
  stage_enabled create-test && run_stage create-test

  if stage_enabled archive-instructions; then
    run_stage archive-instructions "Archive task $num (\"$title\") only."
    [ -f "$SPEC" ] && halt "/archive-instructions left $SPEC in place — the task did not close"
    [ "$(count_done)" -gt "$before" ] \
      || halt "round $round moved no task to DONE in $MILESTONE — stopping rather than looping on the same task"
  fi

  log "round $round done — $(count_done) task(s) DONE"
done

log "loop finished — logs in $LOG_DIR"
notify "loop finished: $(count_done) task(s) DONE"
