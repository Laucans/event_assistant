"""PostToolUse hook: launch scripts/pr-review when a PR is opened.

`gh pr create` prints the new PR's URL and nothing else useful, so that URL
in the tool output is the trigger. The review runs detached: the hook has to
return in milliseconds, and the loop must stay free to merge the PR while the
review is still being written.

Fails open on every unexpected shape — a broken hook must never be what
stops the agent loop from opening a PR.

La lecture de l'evenement est separee du lancement : `reviewable` est une
fonction pure, donc les formes qu'un evenement peut prendre se testent en lui
passant un dictionnaire.
"""

import json
import os
import re
import subprocess
import sys

PR_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/(\d+)")
# `gh pr create`, however it is spelled — flags between the words, a heredoc
# body after them, another command piped in front.
PR_CREATE = re.compile(r"\bgh\b(?:\s+\S+)*?\s+pr(?:\s+\S+)*?\s+create\b")

NOTICE = ("agent-review: launched on PR #{num} (detached). It posts inline "
          "findings and a summary comment on its own; do not wait for it, "
          "and carry on with the stage. Log: .llocal/pr-review/")


def _output(data: dict) -> str:
    """Ce que l'outil a imprime, quelle que soit la forme de sa reponse."""
    resp = data.get("tool_response")
    if isinstance(resp, dict):
        return f"{resp.get('stdout') or ''}\n{resp.get('stderr') or ''}"
    return str(resp or "")


def reviewable(data: dict) -> str | None:
    """Le numero de la PR que cet evenement vient d'ouvrir, ou None.

    Pure : elle ne lit ni l'environnement, ni le disque.
    """
    if (data.get("tool_name") or "") != "Bash":
        return None
    if not PR_CREATE.search((data.get("tool_input") or {}).get("command") or ""):
        return None
    found = PR_URL.search(_output(data))
    return found.group(1) if found else None


def _launch(root: str, num: str) -> bool:
    """Lance la revue, detachee. Rend False si rien n'a pu partir."""
    script = os.path.join(root, "scripts", "pr-review")
    if not os.path.isfile(script):
        return False
    log_dir = os.path.join(root, ".llocal", "pr-review")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, f"hook-{num}.log"), "ab")
        subprocess.Popen([script, num], cwd=root, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    except Exception:
        return False
    return True


def main() -> None:
    # Set by the review itself: the `gh pr` calls it makes must not
    # trigger a second review.
    if os.environ.get("PR_REVIEW_ACTIVE"):
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    num = reviewable(data)
    if num is None:
        return

    root = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    if _launch(root, num):
        print(json.dumps({"systemMessage": NOTICE.format(num=num)}))
