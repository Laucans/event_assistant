#!/usr/bin/env python3
"""PreToolUse hook: refuse a Bash command that would read a secret path.

`permissions.deny` in .claude/settings.json stops the Read tool on
.env / .env.* / secrets/** / ~/.ssh / ~/.aws / ~/.config. A Bash command can
read the same files around that rule, so every token of every segment is
checked against the same list; a hit exits 2, which blocks the call.

Quoted-delimiter heredoc bodies are deliberately NOT scanned. A `cat > x.md
<<'EOF'` whose prose mentions a dotenv file *writes* a file, it does not read
one — and blocking that is not theoretical: it cost a /code-review pass
mid-run (see permission_denials in .llocal/pr-review/9-inline.json), then
blocked the commit of this very file. On a project whose specs and reviews
discuss local env files constantly, that false positive is expensive.

An unquoted `<<EOF` body stays in scope on purpose: the shell expands it, so
a command substitution in there really would read the file.

Fails open on every unexpected shape — a broken hook must not be what stops
the work.
"""

import json
import os
import re
import shlex
import sys

OK = (".env.example", ".env.sample", ".env.template")
HEREDOC = re.compile(r"""<<-?[ \t]*(?:'([^']*)'|"([^"]*)")""")


def strip_quoted_heredocs(cmd):
    """Drop the body (and terminator) of every quoted-delimiter heredoc."""
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for single, double in HEREDOC.findall(line):
            delim = single or double
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1  # the terminator line itself
    return "\n".join(out)


def offending(tok, home):
    """The secret path this token names, or "" if it names none."""
    t = tok.strip("\"'")
    if not t:
        return ""
    t = re.sub(r"^(~|\$HOME|\$\{HOME\})(?=/|$)", home, t)
    p = t
    while p.startswith("./"):
        p = p[2:]
    parts = [x for x in p.split("/") if x and x != "."]
    if not parts:
        return ""
    base = parts[-1]
    if base == ".env" or (base.startswith(".env.") and base not in OK):
        return t
    if "secrets" in parts[:-1]:
        return t
    if t.startswith("/"):
        for d in (".ssh", ".aws", ".config"):
            if t.startswith(home + "/" + d + "/"):
                return t
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if (data.get("tool_name") or "") != "Bash":
        return

    cmd = (data.get("tool_input") or {}).get("command") or ""
    home = os.path.expanduser("~")

    for seg in re.split(r"[;|&\n]", strip_quoted_heredocs(cmd)):
        try:
            toks = shlex.split(seg)
        except Exception:
            toks = seg.split()
        for tok in toks:
            hit = offending(tok, home)
            if hit:
                sys.stderr.write(
                    "Blocked: " + hit + " is a secret path. permissions.deny in "
                    ".claude/settings.json blocks the Read tool on "
                    ".env/.env.*/secrets/**/~/.ssh/~/.aws/~/.config, and this Bash "
                    "command would read the same secrets around that rule. If you "
                    "only need to know which variables exist, read .env.example "
                    "instead."
                )
                sys.exit(2)


main()
