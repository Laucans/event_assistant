"""L'implementation Claude Code de `AgentRunner`.

**Le seul module du paquet qui importe `claude_agent_sdk`**, et
`tests/test_layering.py` en fait une assertion. Le SDK est un pilote au-dessus
du binaire `claude` : memes flags, meme authentification par abonnement, memes
hooks que declare `.claude/settings.json`.

L'import vit dans la methode, pas au niveau du module, a dessein : `--dry-run`,
`--help` et les chemins rapides ne doivent jamais payer le chargement du SDK.
"""

from __future__ import annotations

import dataclasses

from pipeline.adapters.agent.base import AgentResult, AgentRunner
from pipeline.adapters.agent.progress import Progress, silent
from pipeline.runtime.filesystem.workspace import Workspace


class ClaudeSdkRunner(AgentRunner):
    """Une session `claude -p`, pilotee par `claude-agent-sdk`."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    async def run(self, prompt: str, *, model: str, effort: str,
                  permission_mode: str,
                  progress: Progress | None = None) -> AgentResult | None:
        """Fait tourner une session et rend son resultat, ou None s'il n'en
        est venu aucun.

        Une session emet un flux de messages et exactement un resultat. Le
        resultat est ce qu'on rend, mais le flux est ce qui dit a un humain
        que le run est vivant : il etait draine puis jete, et c'est comme ca
        qu'un stage pouvait passer huit minutes sans imprimer une ligne.
        Chaque message passe par `progress` au vol.
        """
        # Import tardif : le chemin dry-run et les commandes rapides ne
        # doivent pas payer le chargement du SDK.
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        options = ClaudeAgentOptions(
            model=model,
            effort=effort,
            permission_mode=permission_mode,
            # Explicite plutot qu'implicite : c'est ce qui charge les hooks,
            # agents, skills et permissions du depot.
            setting_sources=["user", "project", "local"],
            cwd=str(self.workspace.root),
        )

        message = None
        async with (progress or silent()) as watch:
            async for msg in query(prompt=prompt, options=options):
                watch.feed(msg)
                if isinstance(msg, ResultMessage):
                    message = msg
        return None if message is None else self.translate(message)

    @staticmethod
    def translate(message) -> AgentResult:
        """Un `ResultMessage` du SDK, dit dans le vocabulaire du paquet.

        `raw` est une copie **plate** des champs de la dataclasse, pas un
        `asdict()` : la conversion profonde changerait le JSON de l'enveloppe,
        que des tests oracle lisent au bit pres.
        """
        raw = {f.name: getattr(message, f.name, None)
               for f in dataclasses.fields(message)}
        return AgentResult(
            text=(message.result or "").strip(),
            is_error=message.is_error,
            subtype=message.subtype,
            session_id=message.session_id,
            cost_usd=message.total_cost_usd,
            duration_ms=message.duration_ms,
            turns=message.num_turns,
            usage=message.usage or {},
            api_error_status=message.api_error_status,
            raw=raw,
        )
