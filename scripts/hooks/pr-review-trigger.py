#!/usr/bin/env python3
"""PostToolUse hook: launch scripts/pr-review.sh when a PR is opened.

`gh pr create` prints the new PR's URL and nothing else useful, so that URL
in the tool output is the trigger. The review runs detached: the hook has to
return in milliseconds, and the loop must stay free to merge the PR while the
review is still being written.

Fails open on every unexpected shape — a broken hook must never be what
stops the agent loop from opening a PR.
"""

import json
import os
import re
import subprocess
import sys

PR_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/(\d+)")


def main() -> None:
    # Set by pr-review.sh: the `gh pr` calls the review itself makes must not
    # trigger a second review.
    if os.environ.get("PR_REVIEW_ACTIVE"):
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    if (data.get("tool_name") or "") != "Bash":
        return

    cmd = (data.get("tool_input") or {}).get("command") or ""
    # `gh pr create`, however it is spelled — flags between the words, a
    # heredoc body after them, another command piped in front.
    if not re.search(r"\bgh\b(?:\s+\S+)*?\s+pr(?:\s+\S+)*?\s+create\b", cmd):
        return

    resp = data.get("tool_response")
    if isinstance(resp, dict):
        out = "%s\n%s" % (resp.get("stdout") or "", resp.get("stderr") or "")
    else:
        out = str(resp or "")

    m = PR_URL.search(out)
    if not m:
        return
    num = m.group(1)

    root = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    script = os.path.join(root, "scripts", "pr-review.sh")
    if not os.path.isfile(script):
        return

    log_dir = os.path.join(root, ".llocal", "pr-review")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, "hook-%s.log" % num), "ab")
        subprocess.Popen(
            [script, num],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception:
        return

    print(json.dumps({
        "systemMessage": (
            "agent-review: launched on PR #%s (detached). It posts inline "
            "findings and a summary comment on its own; do not wait for it, "
            "and carry on with the stage. Log: .llocal/pr-review/" % num
        )
    }))


main()
