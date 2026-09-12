"""PreToolUse: refuse a `git push` that would target `main`.

Admin bypass and the GitHub ruleset are both backstops; this hook is the
enforcement (CLAUDE.md, Repository etiquette), which is why `git push` is
allowlisted rather than prompted.

Parses tokens rather than text: `git -C x push origin HEAD:main`,
`env FOO=1 git push` and `sudo git push --force origin main` must all be
seen, while `git push origin my-branch` must pass.
"""

import json
import os
import re
import shlex
import subprocess
import sys

MESSAGE = ("Blocked: never push to main directly (CLAUDE.md, Repository"
           " etiquette). Admin bypass means the push would succeed. Instead:"
           " git switch -c <type>/<slug>, push that branch, gh pr create, then"
           " gh pr merge --rebase once ci is green.")

# What may precede `git` without changing what the command is.
PREFIXES = ("sudo", "env", "command", "time", "nohup")
# The options of `git` itself that consume an argument.
TAKES_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")


def current_branch(root=None):
    d = root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    try:
        return subprocess.run(["git", "-C", d, "symbolic-ref", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def targets_main(cmd, branch):
    """True if the command would push to `main`.

    `branch` is the current branch: with no explicit destination, `git push`
    pushes the branch you are on.
    """
    for seg in re.split(r"[;|&\n]", cmd):
        try:
            toks = shlex.split(seg)
        except Exception:
            toks = seg.split()
        g = 0
        while g < len(toks) and (re.match(r"^[A-Za-z_][A-Za-z_0-9]*=", toks[g])
                                 or toks[g] in PREFIXES):
            g += 1
        if g >= len(toks) or not (toks[g] == "git" or toks[g].endswith("/git")):
            continue
        j = g + 1
        while j < len(toks):
            if toks[j] in TAKES_ARG:
                j += 2
            elif toks[j].startswith("-"):
                j += 1
            else:
                break
        if j >= len(toks) or toks[j] != "push":
            continue
        positional = [t for t in toks[j + 1:] if not t.startswith("-")]
        if len(positional) < 2:
            if branch == "main":
                return True
            continue
        for ref in positional[1:]:
            dest = re.sub(r"^refs/heads/", "", ref.split(":")[-1].lstrip("+"))
            if dest in ("HEAD", "@"):
                dest = branch
            if dest == "main":
                return True
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if (data.get("tool_name") or "") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if targets_main(cmd, current_branch()):
        sys.stderr.write(MESSAGE)
        sys.exit(2)
    sys.exit(0)
