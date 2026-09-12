"""L'implementation CrewAI du moteur de graphe.

**Le seul module du paquet qui importe crewai**, et `tests/test_layering.py`
en fait une assertion. crewai coute ~1,3 s d'import a chaud et tire chromadb,
openai et opentelemetry — 2331 modules — donc ce module n'est charge que sur
le chemin d'un run reel : `--status`, `--costs`, `--help` et les hooks n'y
touchent jamais.

Ce qu'il expose est de deux natures. Les **primitives** (`Flow`, `start`,
`listen`, `router`) sont re-exportees pour que
`workflows.agentic_dev_loop.flow` decrive son graphe sans nommer crewai. Les **services** (`quiet_panels`, `persisted`)
sont ce que le moteur sait faire et qu'un autre moteur devrait savoir faire
aussi.

Ce qu'il n'expose pas : la **lecture** du magasin de reprise. crewai l'ecrit,
mais `adapters.store.resume` le relit en sqlite3 standard, parce que
`--status` doit repondre sans payer cet import-ci. Le schema est donc une
donnee partagee entre les deux, et c'est assume.
"""

from __future__ import annotations

import os
from pathlib import Path

from crewai.flow.flow import Flow, listen, router, start

__all__ = ["Flow", "listen", "persisted", "quiet_panels", "router", "start"]


def quiet_panels(log) -> None:
    """Fait taire les panneaux decoratifs de CrewAI.

    Il en imprime un par methode de flow — une quinzaine de cadres ASCII par
    round, qui repetent ce que nos propres lignes disent deja et noient le
    journal qu'on va vraiment relire. Une boucle non surveillee se juge sur
    son journal ; il doit rester lisible.

    `PIPELINE_CREWAI_PANELS=1` les remet, pour deboguer le graphe lui-meme.
    """
    if os.environ.get("PIPELINE_CREWAI_PANELS") == "1":
        return
    try:
        from crewai_core.printer import set_suppress_console_output
    except ImportError as exc:  # une version qui ne l'expose pas
        log.warn(f"cannot silence the crewai panels ({exc}) — the journal will"
                 " be noisy")
        return
    set_suppress_console_output(True)


def persisted(flow_cls: type, db: Path) -> type:
    """La meme classe de flow, mais qui ecrit son etat a chaque noeud.

    C'est ce qui rend un round reprenable : sans ca, une panne au stage 3
    ferait repayer les deux premiers.
    """
    from crewai.flow.persistence import SQLiteFlowPersistence, persist

    db.parent.mkdir(parents=True, exist_ok=True)
    return persist(SQLiteFlowPersistence(str(db)))(flow_cls)
