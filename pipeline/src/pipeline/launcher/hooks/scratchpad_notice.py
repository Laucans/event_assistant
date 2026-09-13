"""PreToolUse: tell the human a tool worked inside the scratchpad.

Purely informational — the hook blocks nothing, it returns one line the
interface displays, so that a file written outside the repo does not go
unnoticed.
"""

import json
import re
import sys

PATH = r"(?:/private)?/tmp/claude-[^\s\"|;]*?scratchpad"


def notice(tool_name, tool_input):
    """The message to display, or None if the call misses the scratchpad."""
    subject = (tool_input.get("command") if tool_name == "Bash"
               else tool_input.get("file_path"))
    m = re.search(PATH + r"([^\s\"|;]*)", subject or "")
    if not m:
        return None
    if tool_name == "Bash":
        c = " ".join(re.sub(PATH, ".../scratchpad", subject).split())
        value = c[:80] + ("..." if len(c) > 80 else "")
    else:
        value = "..." + m.group(1) if m.group(1).strip("/") else ".../scratchpad"
    return f"scratchpad: {tool_name} {value}"


def main():
    try:
        data = json.load(sys.stdin)
        msg = notice(data.get("tool_name") or "", data.get("tool_input") or {})
        if msg:
            print(json.dumps({"systemMessage": msg}))
    except Exception:
        pass
