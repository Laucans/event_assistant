"""L'interface d'un moteur d'agent, et le resultat neutre qu'il rend.

Le paquet appelait le SDK d'Anthropic directement : les appelants lisaient
`result.total_cost_usd`, `result.api_error_status`, `result.num_turns` — des
noms de champs qui appartiennent a un fournisseur. Changer de moteur aurait
demande de changer `session.py` et `review.py` avec.

Ce que le reste du paquet voit desormais, c'est `AgentRunner.run()` qui rend
un `AgentResult`. Un fournisseur qui n'aurait ni la notion de cout, ni celle
de tour, remplit ces champs avec `None` : c'est ce que `None` veut dire ici,
et `runtime.monitoring.metrics` sait deja l'afficher comme « ? » plutot que
comme zero.

`raw` est la soupape : l'enveloppe JSON qu'un post-mortem relit doit garder
tout ce que le fournisseur a dit, y compris ce que cette interface ne nomme
pas. C'est un dict de champs bruts, jamais lu pour decider quoi que ce soit.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pipeline.core.adapters.agent.progress import Progress

# Le filet : quand le moteur ne qualifie pas l'erreur, on reconnait encore la
# phrase que la CLI imprime une fois la fenetre d'abonnement epuisee.
QUOTA = re.compile(r"usage limit|rate limit|session limit|limit reached|too many requests",
                   re.I)


def failure_reason(*, is_error: bool, subtype: str, text: str,
                   api_error_status: int | None) -> str | None:
    """Pourquoi ce run n'a produit aucun resultat exploitable, ou None.

    Rend `"quota"`, `"failed"`, `"empty"` — ou None si le stage a repondu.

    L'ordre compte, et c'est la nuance que la premiere version ratait : la
    phrase de quota n'est cherchee que dans un run qui a **deja echoue**. La
    chercher dans une reponse reussie ferait passer pour bloque par le quota
    un stage qui ne fait qu'en *parler*, et comme il ne serait alors pas
    marque fait, le re-run repaierait un /code deja merge. Le 429, lui, est
    structure : il se suffit.

    Neutre par construction : elle ne prend que des valeurs, pas un resultat,
    donc une seconde implementation la reutilise telle quelle.
    """
    failed = is_error or subtype != "success" or not text
    if api_error_status == 429 or (failed and QUOTA.search(text)):
        return "quota"
    if is_error or subtype != "success":
        return "failed"
    if not text:
        return "empty"
    return None


@dataclass(frozen=True)
class AgentResult:
    """Ce qu'une session a rendu, dans un vocabulaire qui n'est celui d'aucun
    fournisseur."""

    text: str
    is_error: bool = False
    subtype: str = "success"
    session_id: str = ""
    cost_usd: float | None = None
    duration_ms: float | None = None
    turns: int | None = None
    usage: dict = field(default_factory=dict)
    api_error_status: int | None = None
    # Tout ce que le fournisseur a rendu, tel quel — pour l'enveloppe seule.
    raw: dict = field(default_factory=dict)

    @property
    def failure(self) -> str | None:
        """`"quota"`, `"failed"`, `"empty"` — ou None si la session a repondu."""
        return failure_reason(is_error=self.is_error, subtype=self.subtype,
                              text=self.text,
                              api_error_status=self.api_error_status)

    def ledger_fields(self, *, model: str, effort: str) -> dict:
        """Les colonnes que les deux registres partagent.

        Les deux n'ont pas le meme schema — une ligne de stage porte aussi le
        run, la task et les compteurs de cache, une ligne de revue la PR et la
        passe — donc chaque appelant ajoute les siennes par-dessus.
        """
        return {"cost": self.cost_usd, "turns": self.turns,
                "duration_ms": self.duration_ms,
                "tokens_in": self.usage.get("input_tokens"),
                "tokens_out": self.usage.get("output_tokens"),
                "session": self.session_id,
                "ran_on": f"{model}/{effort}"}


class AgentRunner(ABC):
    """Une session d'agent : un prompt entre, un resultat sort.

    Le flux de messages ne sort pas par la valeur de retour mais par
    `progress`, parce qu'il sert pendant, pas apres : c'est lui qui dit qu'un
    stage de huit minutes est vivant. Une implementation doit nourrir
    `progress.feed()` de chaque message qu'elle voit passer.
    """

    @abstractmethod
    async def run(self, prompt: str, *, model: str, effort: str,
                  permission_mode: str,
                  progress: Progress | None = None) -> AgentResult | None:
        """Rend le resultat, ou None si la session s'est arretee sans repondre."""
