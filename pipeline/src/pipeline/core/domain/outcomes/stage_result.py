"""Ce qu'un stage rend, et le contrat verbal par lequel on le lit.

Deux choses, et elles vont ensemble : la forme du resultat d'un stage, et les
deux marqueurs que le preambule demande au modele d'ecrire en fin de reponse.
`AGENT_LOOP_OK:` dit que le stage est alle au bout, `AGENT_LOOP_STOP:` qu'il
s'est arrete volontairement — un resultat correct, pas une panne.

Metier pur : aucun I/O, aucune dependance. C'est ce qui rend le contrat
testable en lui passant trois lignes de texte.
"""

from __future__ import annotations

from dataclasses import dataclass

OK_MARKER = "AGENT_LOOP_OK:"
STOP_MARKER = "AGENT_LOOP_STOP:"


def read_markers(text: str) -> tuple[str | None, str | None]:
    """`(ligne OK, ligne STOP)` — la premiere de chaque, ou None.

    La premiere et non la derniere : un stage qui ecrit son marqueur puis
    continue a parler a quand meme repondu.
    """
    ok = stop = None
    for line in text.splitlines():
        if stop is None and line.startswith(STOP_MARKER):
            stop = line.strip()
        if ok is None and line.startswith(OK_MARKER):
            ok = line.strip()
    return ok, stop


@dataclass
class StageResult:
    """Ce qu'un stage a rendu, et ce qu'il a coute.

    Les mesures voyagent avec le resultat plutot que d'etre agregees ici : le
    flow les additionne, et un stage qui echoue ne fausse pas le total.
    """

    text: str
    cost: float
    session_id: str
    ok_line: str | None
    stop_line: str | None
    duration_ms: float = 0.0
    turns: object = None
    usage: dict | None = None

    @property
    def stopped(self) -> bool:
        return self.stop_line is not None
