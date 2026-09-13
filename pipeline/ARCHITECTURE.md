# Architecture — `pipeline/`

## Objet

- Runner non surveillé. Dépense un budget de sessions Claude Code contre des issues GitHub.
- Deux workflows : la boucle de développement, la revue consultative de PR.
- Python ≥ 3.13. Deux dépendances : `claude-agent-sdk`, `pydantic`.

## Les trois paquets

| Paquet | Rôle | Connaît |
| --- | --- | --- |
| `core/` | le framework | rien de ce qui l'utilise |
| `workflows/` | les instances | `core/` |
| `launcher/` | les points d'entrée | `core/`, `workflows/` |

```
src/pipeline/
├── core/        50 modules — vocabulaire, runtime, adaptateurs, exécution, design
├── workflows/   33 modules — agentic_dev_loop, pr_review, common, legacy
└── launcher/    14 modules — routeur, 2 CLI, 4 hooks
```

- Le sens des dépendances ne s'inverse jamais. Table `ALLOWED` dans `tests/test_layering.py`.
- Chaque paquet porte son `ARCHITECTURE.md`.

## Invariants

- **Le framework ignore ses utilisateurs.** Rien sous `core/` ne nomme un workflow.
- **Les arrêts sont des valeurs.** `Result`, pas d'exception. Une seule survit : `ConfigError`.
- **Vérifier avant de payer.** Une porte coûte un appel local ; l'erreur découverte en route coûte un stage.
- **Une lecture ratée ne rend jamais vide.** `[]` se lit « plus rien à faire », et déclenche un `/planner`.
- **Un workflow décide, il n'appelle pas.** Les binaires vivent dans `adapters/`.
- **Le chemin rapide ne paie pas le moteur.** `--status` et `--costs` répondent en ~130 ms.
- **Le texte de page scrapée est une donnée.** Jamais une instruction.

## Un round

```
préflight → task choisie → /business-analyst → /code → /create-test → livrée ?
```

- Une task par round. Le budget par défaut : 3 rounds.
- Une task est livrée quand une PR mergée porte `Closes #N` sur sa propre ligne.
- L'issue reçoit `pipeline:waiting-merge`. Elle reste ouverte jusqu'à la fusion dans `main`.

## État

- Rien dans le dépôt. Tout dans `.llocal/`, gitignoré.

| Chemin | Contenu |
| --- | --- |
| `.llocal/agent-loop/<run_id>/` | journal et artefacts d'un run |
| `.llocal/agent-loop/costs.tsv` | registre des stages |
| `.llocal/agent-loop/state` | pointeur de reprise |
| `.llocal/agent-loop/flow_states.db` | états de round, sqlite |
| `.llocal/pr-review/` | journaux, enveloppes, commentaires, registre des revues |

- Le travail en cours vit dans les issues GitHub, pas dans des fichiers.

## Commandes

```bash
scripts/agent-loop --dry-run          # ce qu'un run ferait ; n'appelle rien
scripts/agent-loop --status           # d'où un re-run repartirait
scripts/agent-loop --costs            # ce que la boucle a dépensé
scripts/pr-review <pr>                # revue consultative d'une PR
pipeline/.venv/bin/python -m pytest pipeline/tests
```

- Les shims résolvent le python du venv, puis délèguent à `pipeline.launcher`.
- Tests hors de `npm run test`. 667 cas.

## Installation

```bash
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv pipeline/.venv
pipeline/.venv/bin/pip install -e 'pipeline[dev]'
```

- Le venv est épinglé sur 3.13. La machine tourne en 3.14.
- `pipeline/.envrc` met ce venv sur le `PATH` via direnv.
- Les sept étiquettes `pipeline:` doivent exister. Le préflight imprime les commandes.

## Tests d'architecture

- `tests/test_layering.py` parcourt l'AST de chaque module.
- Une convention écrite est vraie le jour où on l'écrit. Ces tests la gardent vraie.
- Couvrent : sens des imports, confinement du SDK, pureté du domaine, forme des workflows, chemin rapide, pointeurs de docstring.
- Chaque scan porte un garde-fou : un scan qui ne trouve rien passerait partout.

## Où lire

| Document | Répond à |
| --- | --- |
| `README.md` | ce que le runner fait, et comment s'en servir |
| `ARCHITECTURE.md` | ce fichier : la carte, les invariants |
| `src/pipeline/core/ARCHITECTURE.md` | le framework, couche par couche |
| `src/pipeline/workflows/ARCHITECTURE.md` | ce qu'est un workflow, et de quoi il est fait |
| `src/pipeline/launcher/ARCHITECTURE.md` | routage, protocoles, codes de sortie |

- Ces cinq fichiers sont les seuls documents de référence. Le détail est dans le code.
- `TOUR.md` et `INTERNALS.md` ont été supprimés : ils précédaient le passage aux blueprints.
