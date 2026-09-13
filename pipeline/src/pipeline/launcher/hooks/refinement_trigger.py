"""Hook evenementiel : lance scripts/refinement quand une issue est etiquetee.

Deux formes d'evenement sont acceptees sur stdin : la charge utile GitHub
`issues.labeled` (`{"action": "labeled", "label": {"name": "…"},
"issue": {"number": 25}}`) et sa forme plate (`{"action": "labeled",
"label": "…", "issue": 25}`). Tout le reste ne lance rien.

Le raffinage part detache : le hook doit rendre en quelques millisecondes.
Il echoue en ouvert — une forme inattendue ne casse rien.

La lecture de l'evenement est separee du lancement : `refinable` est une
fonction pure, donc les formes qu'un evenement peut prendre se testent en lui
passant un dictionnaire.
"""

import json
import os
import subprocess
import sys

# Ecrite en clair : un hook tourne sous le python du systeme, hors du venv,
# et ne peut donc pas importer `workflows.common.labels`.
LABEL = "pipeline:refinement"

NOTICE = ("agent-refinement: launched on issue #{num} (detached). It rewrites "
          "the issue body and comments the round on its own; do not wait for "
          "it. Log: .llocal/refinement/")


def _name(label) -> str:
    """Le nom d'une etiquette, dite en objet GitHub ou en chaine nue."""
    if isinstance(label, dict):
        value = label.get("name")
        return value if isinstance(value, str) else ""
    return label if isinstance(label, str) else ""


def _number(issue) -> str | None:
    """Le numero d'une issue, dite en objet GitHub ou en nombre nu."""
    value = issue.get("number") if isinstance(issue, dict) else issue
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    text = str(value).strip()
    return text if text.isdigit() else None


def refinable(event: dict) -> str | None:
    """Le numero de l'issue que cet evenement vient d'etiqueter, ou None.

    Pure : elle ne lit ni l'environnement, ni le disque.
    """
    if not isinstance(event, dict):
        return None
    if (event.get("action") or "") != "labeled":
        return None
    if _name(event.get("label")) != LABEL:
        return None
    return _number(event.get("issue"))


def _launch(root: str, num: str) -> bool:
    """Lance le raffinage, detache. Rend False si rien n'a pu partir."""
    script = os.path.join(root, "scripts", "refinement")
    if not os.path.isfile(script):
        return False
    log_dir = os.path.join(root, ".llocal", "refinement")
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
    try:
        event = json.load(sys.stdin)
    except Exception:
        return

    num = refinable(event)
    if num is None:
        return

    root = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    if _launch(root, num):
        print(json.dumps({"systemMessage": NOTICE.format(num=num)}))
