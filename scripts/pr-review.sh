#!/usr/bin/env bash
#
# pr-review.sh — review a PR opened against the integration branch and leave
# the notes a human needs to relire it.
#
# The agent loop writes code nobody watched. This is the compensating read:
# two `claude -p` passes on one PR, both of which end on the PR itself.
#
#   1. /code-review <level> <pr> --comment  -> findings posted inline, on the
#      exact file:line they concern.
#   2. a reviewer's brief -> one summary comment: what changed, what to look
#      at first, what the agent assumed, what is worth a question.
#
# Advisory only. It never blocks, never merges, never edits the branch — the
# loop is free to merge the PR while this is still running, and the comments
# stay readable on the merged PR.
#
# Each pass carries its own model and effort, because they are not the same
# job. /code already ran an adversarial review before merging, so pass 1 is a
# second opinion in a fresh context rather than the only line of defence —
# Sonnet at `medium` finds the things a tired reviewer would, at ~30% of what
# Opus at `high` cost (measured: $1.68 for one review of a 180-line change,
# .llocal/pr-review/costs.tsv). Pass 2 summarizes what pass 1 and the diff
# already say; it is a writing task, not a hunt.
#
# One review per task, not per PR: /code and /create-test each open one, and
# reviewing the test PR re-reads the same change. `test/*` heads are skipped.
#
# Usage:
#   scripts/pr-review.sh <pr-number|url>
#   scripts/pr-review.sh 42 --level high --model opus   # the expensive read
#   scripts/pr-review.sh 42 --dry-run       # write the prompts, call nothing
#
# Flags: --level <low|medium|high|max>, --model <alias> (both passes),
# --base <branch>, --force (review a PR whose base is not the integration
# branch, whose head is a `test/*` branch, or one already reviewed),
# --no-inline (summary comment only), --dry-run.
#
# Env: INTEGRATION_BRANCH, PR_REVIEW_LEVEL, PR_REVIEW_MODEL (overrides both
# passes), PR_REVIEW_INLINE_MODEL, PR_REVIEW_INLINE_EFFORT,
# PR_REVIEW_BRIEF_MODEL, PR_REVIEW_BRIEF_EFFORT.

set -euo pipefail

# Same reason as agent-loop.sh: `claude -p` bills whatever the CLI is logged
# in as, and a stray key in the environment would move this off the
# subscription onto a metered account.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

# Read by the PostToolUse hook that launches this script, so the `gh pr`
# calls made *inside* the review cannot trigger another review.
export PR_REVIEW_ACTIVE=1

cd "$(git rev-parse --show-toplevel)"

INTEGRATION_BRANCH=${INTEGRATION_BRANCH:-main_agent}
LEVEL=${PR_REVIEW_LEVEL:-medium}
MODEL=${PR_REVIEW_MODEL:-}
MARKER='<!-- agent-review -->'

# Per-pass model and effort. `--model`/PR_REVIEW_MODEL, when set, wins over
# both — one flag to put the whole review back on Opus for a change that
# deserves it.
INLINE_MODEL=${PR_REVIEW_INLINE_MODEL:-sonnet}
INLINE_EFFORT=${PR_REVIEW_INLINE_EFFORT:-medium}
BRIEF_MODEL=${PR_REVIEW_BRIEF_MODEL:-sonnet}
BRIEF_EFFORT=${PR_REVIEW_BRIEF_EFFORT:-low}
PR=""
FORCE=0
INLINE=1
DRY_RUN=0

while [ $# -gt 0 ]; do
  case $1 in
    --level) LEVEL=$2; shift 2 ;;
    --base) INTEGRATION_BRANCH=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --force) FORCE=1; shift ;;
    --no-inline) INLINE=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,42p' "$0"; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) PR=$1; shift ;;
  esac
done

[ -n "$PR" ] || { echo "usage: scripts/pr-review.sh <pr-number|url> [flags]" >&2; exit 2; }

LOG_DIR=.llocal/pr-review
mkdir -p "$LOG_DIR"

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }

# --- gates -----------------------------------------------------------------
meta=$(gh pr view "$PR" --json number,baseRefName,headRefName,title,url,state,isDraft) \
  || { echo "pr-review: cannot read PR $PR" >&2; exit 1; }

read_field() { printf '%s' "$meta" | python3 -c 'import sys,json;print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }

NUM=$(read_field number)
BASE=$(read_field baseRefName)
HEAD=$(read_field headRefName)
TITLE=$(read_field title)
URL=$(read_field url)
DRAFT=$(read_field isDraft)

if [ "$BASE" != "$INTEGRATION_BRANCH" ] && [ "$FORCE" = 0 ]; then
  log "skip — PR #$NUM targets '$BASE', not '$INTEGRATION_BRANCH' (--force to override)"
  exit 0
fi

if [ "$DRAFT" = "True" ] && [ "$FORCE" = 0 ]; then
  log "skip — PR #$NUM is a draft"
  exit 0
fi

# /code and /create-test each end in a PR, so one task produced two reviews of
# the same change — the second one re-reading the implementation to say the
# same things about it. `/create-test` branches `test/<slug>`
# (.claude/skills/create-test/SKILL.md, "Land it"), which is the only signal
# available before spending a pass on it.
case $HEAD in
  test/*)
    if [ "$FORCE" = 0 ]; then
      log "skip — #$NUM is the test PR for a change already reviewed on its /code PR (--force to review it anyway)"
      exit 0
    fi
    ;;
esac

# One review per PR. A re-run after the loop pushes a fixup is a --force away.
if [ "$FORCE" = 0 ] && gh pr view "$NUM" --json comments \
     -q '.comments[].body' 2>/dev/null | grep -qF "$MARKER"; then
  log "skip — PR #$NUM already carries an agent review (--force to redo)"
  exit 0
fi

# Two hooks firing on the same PR would post the review twice.
LOCK="$LOG_DIR/.lock-$NUM"
if ! mkdir "$LOCK" 2>/dev/null; then
  log "skip — a review of PR #$NUM is already running"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

log "reviewing #$NUM  $HEAD -> $BASE  ($TITLE)"

# A `claude -p` run that never answered still exits with output on stdout —
# "You've hit your session limit", an API error, a refusal. The first run of
# this script posted one of those to the PR as if it were a review, so the
# JSON envelope is now what decides: no envelope, an error subtype or an
# empty result all mean "post nothing".
LEDGER=$LOG_DIR/costs.tsv

claude_run() {
  local prompt=$1 label=$2 model=$3 effort=$4 raw rc
  # An explicit --model is a deliberate override of the per-pass default.
  [ -n "$MODEL" ] && model=$MODEL
  if [ "$DRY_RUN" = 1 ]; then
    printf '%s\n' "--- prompt ($label, model=$model effort=$effort) ---" "$prompt" "--- end ---"
    return 0
  fi
  set +e
  raw=$(claude -p "$prompt" \
    --permission-mode bypassPermissions \
    --output-format json \
    --model "$model" \
    --effort "$effort" 2>&1)
  rc=$?
  set -e
  printf '%s' "$raw" > "$LOG_DIR/$NUM-$label.json"
  [ "$rc" = 0 ] || log "  claude exited $rc on the $label pass"
  parse_run "$LOG_DIR/$NUM-$label.json" "$label" "$model/$effort"
}

# Prints the run's answer on stdout, appends its real cost to the ledger, and
# exits non-zero when the run did not actually produce one.
parse_run() {
  python3 - "$1" "$LEDGER" "$NUM" "$2" "$3" <<'PY'
import datetime, json, os, sys

path, ledger, pr, label, ran_on = sys.argv[1:6]
raw = open(path, encoding="utf-8").read()

try:
    d = json.loads(raw)
except Exception:
    sys.stderr.write("no JSON envelope — claude stopped before answering: %s\n"
                     % " ".join(raw.split())[:200])
    sys.exit(1)

usage = d.get("usage") or {}
fresh = not os.path.exists(ledger)
with open(ledger, "a", encoding="utf-8") as fh:
    if fresh:
        fh.write("when\tpr\tpass\tcost_usd\tturns\tduration_ms\tin\tout\tsession\tran_on\n")
    fh.write("%s\t%s\t%s\t%.6f\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
        datetime.datetime.now().isoformat(timespec="seconds"), pr, label,
        d.get("total_cost_usd") or 0.0, d.get("num_turns"),
        d.get("duration_ms"), usage.get("input_tokens"),
        usage.get("output_tokens"), d.get("session_id"), ran_on))

if d.get("is_error") or d.get("subtype") != "success":
    sys.stderr.write("run failed (%s): %s\n"
                     % (d.get("subtype"), " ".join((d.get("result") or "").split())[:200]))
    sys.exit(1)

text = (d.get("result") or "").strip()
if not text:
    sys.stderr.write("run returned an empty result\n")
    sys.exit(1)
print(text)
PY
}

run_cost() {
  [ -s "$LEDGER" ] || return 0
  python3 - "$LEDGER" "$NUM" <<'PY'
import sys
rows = [l.split("\t") for l in open(sys.argv[1], encoding="utf-8").read().splitlines()[1:]]
total = sum(float(r[3]) for r in rows if len(r) > 3 and r[1] == sys.argv[2])
print("%.4f" % total)
PY
}

# --- pass 1: inline findings ----------------------------------------------
# A failed pass 1 is survivable — pass 2 just loses its input. A failed pass 2
# is not: there is nothing to post.
if [ "$INLINE" = 1 ]; then
  log "pass 1/2 — /code-review $LEVEL $NUM --comment  (${MODEL:-$INLINE_MODEL}, effort $INLINE_EFFORT)"
  if ! findings=$(claude_run "/code-review $LEVEL $NUM --comment" inline "$INLINE_MODEL" "$INLINE_EFFORT"); then
    log "  inline pass produced no review — continuing without it"
    findings="(the inline pass did not run; no findings were posted)"
  fi
else
  findings="(inline pass skipped)"
fi

# --- pass 2: the reviewer's brief ------------------------------------------
# Deliberately not a second bug hunt — pass 1 already did that, and its
# findings are handed over below. This pass answers the question a human
# actually opens the PR with: is this the change the spec asked for, and
# where should I spend my attention.
log "pass 2/2 — reviewer's brief  (${MODEL:-$BRIEF_MODEL}, effort $BRIEF_EFFORT)"
brief_prompt=$(cat <<EOF
You are writing review notes on pull request #$NUM ("$TITLE", $HEAD -> $BASE)
in this repository. The branch was written by an unattended agent loop: a
human is about to read the diff for the first time and has to decide whether
to trust it. Your notes are the only orientation they get.

Start by reading the change and its intent:
  gh pr diff $NUM
  gh pr view $NUM --json title,body,commits

You also need the spec the branch was built from, docs/current/SPEC.md. It
is usually committed inside this very PR: if the diff you just read contains
it, you already have it — do not read the file again. Read it off disk only
when the diff does not carry it. Same for
docs/current/CURRENT_MILESTONE.md, and only if you need to place the task.

A spec that appears in the diff as *modified* rather than added is worth a
look on its own: a requirement rewritten during implementation to match what
was built is the drift this comment exists to surface.

A line-by-line bug hunt already ran and posted its findings inline. Here is
what it reported — reference it, do not repeat it:
<inline-review-output>
$findings
</inline-review-output>

Write ONE markdown comment body, and output nothing else — no preamble, no
"here is the comment", no code fence around the whole thing. Around 200-350
words, these sections, dropping any that would be empty:

**Ce que fait ce lot** — the change in 2-4 sentences, in intent terms, not a
file listing.

**À regarder en priorité** — the 2-4 places where a human's attention is
actually worth spending, each as \`file.ts:line\` (markdown link relative to
the repo root) plus one line on why. Rank them; do not list everything.

**Écarts avec le SPEC** — anything the spec asked for that is not here, or
here but not asked for. Say "conforme" if it matches.

**Hypothèses prises** — decisions the agent made that the spec left open,
and that a human might have made differently. This is the section that most
often matters: the loop guesses silently.

**Questions** — what you would ask the author. Omit if you have none.

Write in French, the way a colleague leaves review notes. Be concrete and
specific to this diff — no generic advice, no praise, no summary of your own
process. If the change is small and clean, say so briefly rather than
inflating it. Do not edit any file and do not post anything yourself; the
script posts what you output.
EOF
)

if ! body=$(claude_run "$brief_prompt" brief "$BRIEF_MODEL" "$BRIEF_EFFORT"); then
  log "STOP — the brief pass produced no review, so nothing is posted."
  log "       re-run once you have capacity: scripts/pr-review.sh $NUM --force"
  exit 1
fi

if [ "$DRY_RUN" = 1 ]; then
  log "dry run — nothing posted"
  exit 0
fi

cost=$(run_cost)
if [ "$INLINE" = 1 ]; then
  passes="findings \`${MODEL:-$INLINE_MODEL}\`/niveau \`$LEVEL\`, notes \`${MODEL:-$BRIEF_MODEL}\`"
else
  passes="notes \`${MODEL:-$BRIEF_MODEL}\` (passe ligne à ligne désactivée)"
fi
comment=$LOG_DIR/$NUM-comment.md
{
  printf '%s\n' "$MARKER"
  printf '## 🤖 Notes de revue — %s\n\n' "$(date '+%Y-%m-%d %H:%M')"
  printf '%s\n\n' "$body"
  printf -- '---\n_Revue automatique (`scripts/pr-review.sh`) — %s%s. Indicative : elle ne bloque rien et le lot a pu être mergé entre-temps. Les findings ligne à ligne sont dans l'"'"'onglet **Files changed**._\n' \
    "$passes" "${cost:+, coût \$$cost}"
} > "$comment"

gh pr comment "$NUM" --body-file "$comment"
log "posted — $URL  (coût de cette revue: \$${cost:-?})"
