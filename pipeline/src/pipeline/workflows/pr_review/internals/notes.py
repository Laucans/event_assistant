"""Le texte que la revue publie sur la PR — le seul metier de la revue.

Tout est ici parce que tout est publie : le marqueur qui dit qu'une PR en
porte deja une, et le pied de page. Rien n'y lit un fichier ni n'appelle un
binaire, donc tout se relit et se change sans faire tourner quoi que ce soit.

Ce texte **reste en francais** : il est publie sur une PR GitHub pour un
humain francophone, et il est asserte au bit pres par les tests oracle.
"""

from __future__ import annotations

MARKER = "<!-- agent-review -->"

FOOTER = """_Revue automatique (`pipeline/workflows/pr_review/`) — {passes}{cost}. Indicative : elle ne bloque rien et le lot a pu être mergé entre-temps. Les findings ligne à ligne sont dans l'onglet **Files changed**._"""


def comment(marker: str, stamp: str, body: str, footer: str) -> str:
    """Le commentaire complet, tel qu'il est poste."""
    return f"{marker}\n## 🤖 Notes de revue — {stamp}\n\n{body}\n\n---\n{footer}\n"
