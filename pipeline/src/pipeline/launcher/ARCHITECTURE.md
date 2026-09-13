# Architecture — `launcher/`

La couche d'usage. Ce qu'elle lance : `../workflows/ARCHITECTURE.md`. Le framework : `../core/ARCHITECTURE.md`.

## Périmètre

- Deux protocoles : `cli` (un humain ou un cron) et `hook` (un événement).
- Un hook est appelé par Claude Code, ou par ce qui produit l'événement — `refinement-trigger` attend un daemon.
- Un routeur commun. `argv[0]` nomme la route.
- Aucune décision métier. Traduit des arguments en config, un `Result` en code de sortie.
- Seule couche autorisée à importer `workflows/`.

```
launcher/
├── main.py         le routeur
├── routes.py       la table
├── validation.py   les règles inter-arguments
├── cli/            un module par commande, + reports
└── hooks/          un module par hook
```

## Routage

```python
Route("loop", "cli", "pipeline.launcher.cli.agentic_dev_loop",
      rules=("stages-exist", "rounds-positive", ...))
```

- `Route` écrite à la main, pas en dataclass : `dataclasses` tire `inspect`, ~7 ms par appel d'outil.
- `DEFAULT = "loop"`. Un `argv[0]` inconnu tombe dessus sans consommer l'argument.
- Huit routes : `loop`, `pr-review`, `refinement`, et cinq hooks.
- La table est la liste unique. Deux tests la suivent au lieu de lister les workflows.

```
argv → routes.find → protocole → import tardif → parse → validate → main
```

- Imports tardifs dans `main.py` : le routeur ne charge que la cible atteinte.
- `__main__.py` : trois lignes, pour `python -m pipeline.launcher <route>`.

## Contrainte stdlib

- `__init__.py`, `main.py`, `routes.py` et tout `hooks/` : **bibliothèque standard uniquement**.
- Ils tournent sous le python du système, hors du venv.
- Un hook s'exécute à chaque appel d'outil. Un import du paquet rendrait la session inutilisable.
- Tenu par `test_the_launcher_entry_points_import_only_the_standard_library`.
- Et par `test_the_stdlib_only_scan_covers_the_router_and_every_hook`.

## Protocole CLI

Trois fonctions, c'est l'interface qu'attend le routeur.

```python
def parse_args(argv) -> argparse.Namespace
def config_to_check(args) -> Config | None      # None = rien à valider
def main(argv) -> int
```

- `main` est **le seul endroit qui journalise la raison** : `outcome.report(log).exit_code`.
- La journaliser aussi dans le workflow la ferait sortir deux fois.
- Chaque CLI purge `ANTHROPIC_API_KEY` et `ANTHROPIC_AUTH_TOKEN` avant tout import.
- Une clé sortirait le run de l'abonnement et le mettrait sur un compte facturé.
- La boucle pose en plus `OTEL_SDK_DISABLED=true`.
- `cli/pr_review.py` exporte `PR_REVIEW_ACTIVE=1` vers les sessions qu'il lance.
- `cli/refinement.py` : un round de raffinage sur une issue. `--context` porte la demande.

| Code | Sens |
| --- | --- |
| 0 | terminé, ou sauté volontairement |
| 1 | arrêt volontaire, un humain doit regarder |
| 2 | pas de résultat exploitable |
| 3 | quota d'abonnement épuisé |
| 4 | inattendu, traceback dans le journal |
| 130 | interrompu |

- Un ordonnanceur extérieur lit ces codes. Documentés dans chaque `--help`.
- `except Exception` autour du run : sinon un `ValidationError` partait sur un stderr que personne ne garde.
- Toute variable d'environnement lue doit figurer dans un épilogue `--help`.

## Validation

- Ce qu'argparse ne sait pas dire : les règles inter-arguments.
- Une règle est pure : `(cfg, args) -> list[str]`.
- Deux tables : `ERRORS` (refuse, code 1) et `WARNINGS` (imprime, continue).
- `RULES` dérivée des tables. Une règle nommée dans une route mais absente ne passe pas inaperçue.
- `config_to_check` rend `None` sur les chemins rapides : ils ne lisent aucune valeur validée.

## Chemins rapides

- `--status` et `--costs` répondent sans construire de config ni de répertoire de run.
- Traités avant toute construction, dans `_fast_path`.
- `cli/reports.py` : mise en forme pure. Lit le registre, rend une chaîne.
- `GROUPS` : `run`, `task`, `day`, `stage`.
- La première table est celle du shell, caractère pour caractère. Un test oracle la compare.
- `--status` reste une commande qui répond : une lecture ratée est une ligne, pas un arrêt.
- Inverse du round, où une lecture ratée arrête — parce que la suite dépense.

## Hooks

- Protocole : JSON sur stdin, JSON ou rien sur stdout, `exit 2` bloque.
- Un message pour l'humain : `{"systemMessage": "..."}` sur stdout.
- Un refus : la raison sur stderr, `exit 2`.
- **Chaque hook échoue ouvert.** Un hook cassé ne doit jamais arrêter le travail.
- Les entrées de `scripts/hooks/` ajoutent `pipeline/src` au path et appellent `main()`.

| Hook | Moment | Fait |
| --- | --- | --- |
| `branch_guard` | PreToolUse | refuse un `git push` visant `main` |
| `no_secret_paths` | PreToolUse | refuse un Bash qui lirait un chemin secret |
| `pr_review_trigger` | PostToolUse | lance `scripts/pr-review` détaché sur une PR ouverte |
| `refinement_trigger` | `pipeline:refinement` posée | lance `scripts/refinement` détaché sur l'issue |
| `scratchpad_notice` | PreToolUse | signale un outil ayant écrit dans le scratchpad |

- `branch_guard` est l'enforcement, pas un filet : `git push` est allowlisté plutôt que demandé.
- `pr_review_trigger` lit l'URL sur le stdout de `gh pr create`.
- Il refuse de partir si `PR_REVIEW_ACTIVE` est posé : pas de seconde revue depuis une revue.
- La revue est lancée **détachée**. La boucle peut merger la PR avant qu'elle atterrisse.
- `refinement_trigger` n'est dans aucun `settings.json` : rien dans une session ne le déclenche.
- Il lit l'étiquette et le numéro d'un événement `issues.labeled`, forme GitHub ou forme plate.
- Il écrit `pipeline:refinement` en clair : un hook ne peut pas importer `workflows/`.

## Shims

```bash
exec "$py" -m "pipeline.launcher" loop "$@"
```

- `scripts/agent-loop`, `scripts/pr-review`, `scripts/refinement`. Dernière ligne identique au nom de route près.
- Le shim résout le python du venv. Rien d'autre.

## Brancher une commande

1. `cli/<nom>.py` — les trois fonctions, avec un épilogue.
2. `routes.py` — la `Route` et ses règles.
3. `validation.py` — réutiliser `RULES`, ou en ajouter une.
4. `scripts/<nom>` — copier `scripts/pr-review`.

## Tests

| Test | Ce qu'il empêche |
| --- | --- |
| `test_the_launcher_entry_points_import_only_the_standard_library` | un hook qui charge le paquet |
| `test_the_stdlib_only_scan_covers_the_router_and_every_hook` | un scan devenu vide |
| `test_the_table_names_the_three_commands_and_the_five_hooks` | une route apparue sans qu'on le dise |
| `test_every_environment_variable_the_code_reads_is_in_a_help_epilog` | un bouton que personne ne peut trouver |
| `test_every_environment_variable_the_code_reads_is_in_env_example` | une variable absente du fichier committé |

- Le balayage des épilogues suit `ROUTES`, pas une liste en dur. Un troisième CLI est couvert.
