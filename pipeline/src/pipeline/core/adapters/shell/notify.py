"""La notification de bureau : la seule chose qu'un humain absent verra.

Une boucle non surveillee finit sans que personne regarde le terminal. La
notification est ce qui dit qu'elle est finie, et surtout comment.

Silencieuse ailleurs que sur macOS, et **jamais une raison d'echouer** :
elle est appelee depuis les quatre gestionnaires de sortie de `cli.loop`, y
compris celui de l'arret propre. Une notification qui leverait la remplacerait
par une trace, et le code de sortie documente serait perdu. Le shell disait la
meme chose en deux fois : `command -v osascript || return 0`, puis `|| true`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def notify(msg: str, *, title: str = "agent-loop") -> None:
    if not sys.platform.startswith("darwin"):
        return
    # Un cron ou un launchd avec un PATH minimal n'a pas /usr/bin.
    if not shutil.which("osascript"):
        return
    # Les guillemets sont retires plutot qu'echappes : le message est du
    # texte a nous, et une notification ne doit pas pouvoir sortir de sa
    # propre citation dans l'AppleScript.
    body = msg.replace('"', "")[:200]
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{body}" with title "{title}"'],
                       capture_output=True)
    except OSError:
        # Entre le `which` et l'appel, ou un osascript qui refuse de demarrer.
        pass
