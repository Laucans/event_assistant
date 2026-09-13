# Architecture — `workflows/`

Comment ajouter un workflow : `how_to_design_a_workflow.md`.

## Périmètre

- Un workflow : une chose qu'on lance et qui dépense de l'argent.
- Deux en place : `agentic_dev_loop/`, `pr_review/`.
- `common/` : les portes partagées. Pas un workflow.
- `legacy/` : bascule markdown → issues, à usage unique. Pas un workflow.
- Les deux sont exemptés par `NOT_A_WORKFLOW` dans `tests/test_layering.py`.

## Découpage

- `core/` porte la forme. `workflows/` porte l'instance.
- Rien sous `core/` n'importe `workflows/` ni `launcher/`.
- Un workflow n'importe jamais un autre workflow.
- Le partagé remonte : politique dans `common/`, forme dans `core/`.

| Couche | Rôle |
| --- | --- |
| `core/domain` | vocabulaire : `StageSpec`, `Action`, `Issue`, `Result` |
| `core/runtime` | `Workspace`, `Logbook`, `Tally`. Feuille |
| `core/adapters` | `agent/`, `shell/`, `store/`, `hub` |
| `core/execution` | contrat, session, steps, `StageRunner`, shapes |
| `core/design` | `Blueprint` + `build` |
| `workflows` | les déclarations |
| `launcher` | CLI, routes, hooks |

## Le sandwich

- Portes → travail → post-vérification. Ordre imposé par `contract.sequence()`.
- Haut et bas identiques partout. Fournis par `core/design/build.py`.
- Milieu variable. Exprimé par une *shape*.
- Bas de pile : une session payante. `core/execution/session.py`, appelant unique.

## Blueprint

`core/design/blueprint.py`

```python
WORKFLOW = Blueprint(
    name="pr-review",                 # premier argument de la commande
    config=ReviewConfig,              # type, pas instance
    gates=preconditions.CHECKS,       # tuple[Check, ...]
    artifacts=lambda cfg: ...,        # Path des fichiers du run
    shape=Once(...),                  # ou Repeat(...)
    obtained=None,                    # post-condition ; None est valable
    announce=None,                    # dit après les portes, avant de payer
)
```

- `build.workflow(bp, cfg, log)` monte un objet conforme à `contract.Workflow`.
- `Gates` parcourt `gates`, puis appelle `announce`.
- `Obtained` rend `Result.of(None)` quand `obtained is None`.
- `contract.Workflow` reste un `Protocol` : `execute()` à la main reste valable.

## Structure d'un workflow

```
<nom>/
├── __init__.py
├── workflow.py       le Blueprint
├── settings.py       config + politique de session
├── preconditions.py  CHECKS, announce
├── stages/           la table
└── internals/        le reste
```

- Trois modules racine, exactement. Un quatrième `.py` fait échouer les tests de forme.
- Deux sous-dossiers, exactement (`WORKFLOW_DIRS`).
- Pas de `postconditions.py` : c'est le champ `obtained`.

## Shapes

`core/execution/shapes/` — 54 lignes de code. Seuil de vigilance : 150.

| | `Once` | `Repeat` |
| --- | --- | --- |
| Pour | une cible | un budget |
| Client | `pr_review` | `agentic_dev_loop` |
| Requis | `plan`, `state` | `unit`, `budget` |
| Optionnel | `extra`, `precheck`, `guard`, `held`, `tolerate`, `summary` | `label`, `exhausted`, `summary` |

- `plan(cfg) -> tuple[Step, ...]`. Fonction, pas constante : la revue lit ses modèles dans la config.
- `precheck(cfg, log, state) -> Result[str]`. Valeur non vide = rien à faire, succès.
- `guard(cfg, state) -> ContextManager[bool]`. `False` = un autre run tient la cible.
- `tolerate(step, failed) -> str | None`. `None` = arrêter.
- `unit(cfg, turn, log, log_dir, tally) -> Result[bool]`. Valeur = reste-t-il du travail.

## Étapes

- `Step` : `skill`, `skip`, `before`, `after`. Protocol dans `core/execution/steps.py`.
- Deux implémentations : `StageSpec` (paie) et `Action` (n'appelle qu'en local).
- `shapes.perform` est le seul point qui les distingue.
- `run_sequence` rend au premier échec. Pas de moteur, pas de nœuds.
- L'ordre de la table **est** l'ordre d'exécution.
- Trois moments : `skip` (déjà fait), `before` (exige), `after` (doit avoir obtenu).
- Sortie d'une étape payante : `ctx.results[skill]`.
- `save()` appelé après chaque étape terminée, gardes comprises.

## Config

`WorkflowConfig` satisfait `StagePolicy`. Redéfinir seulement ce qui diffère.

| Membre | Défaut | Redéfini par |
| --- | --- | --- |
| `prompt_for` | *aucun* | tout workflow |
| `runs` / `enabled` | tout tourne | `RunConfig` (`--stages`) |
| `resolve` | inchangé | `RunConfig` (`--model`, `--effort`) |
| `artifact_tag` | `f"{round_no:02d}"` | `ReviewConfig` (numéro de PR) |
| `record` | ligne dans `costs.tsv` | `ReviewConfig` (registre séparé) |

- Champs communs : `dry_run`, `verbose`, `quiet`, `heartbeat_s`, `workspace`, `run_id`, `permission_mode`, `stages`.
- `ConfigError` : seule exception levée. Une config qui ne se construit pas n'a pas d'appelant.

## Portes

- `Check(name, verify)`. `verify(cfg, log) -> Result[None]`.
- Une porte ne lève jamais.
- `verify_all` s'arrête à la première qui échoue. Les portes se supposent.
- Forme dans `core/execution/contract/gate.py`. Politique dans `common/checks.py`.
- `common.TOOLING` : `claude`, `gh`, `gh auth`.
- `common.BRANCH` : existe, checked out, sur origin, `ci` déclenche.
- Portes du workflow ≠ gardes d'étape. Les secondes vivent dans `internals/`.

## Arrêts

- Valeurs, pas exceptions. `core/domain/outcomes/result.py`.

| Constructeur | Exit | Sens |
| --- | --- | --- |
| `Result.of(v)` | 0 | abouti |
| `Result.halt(r)` | 1 | arrêt volontaire, un humain agit |
| `Result.unreadable(r)` | 1 | un magasin n'a pas répondu |
| `Result.fail(r)` | 2 | rien d'utilisable |
| `Result.quota(r)` | 3 | fenêtre épuisée, revenir plus tard |

- Une lecture ratée ne rend jamais vide. Vide se lit « plus rien à faire ».
- La raison est journalisée une seule fois, par `outcome.report(log)` dans le CLI.

## Chemin rapide

- `--status` et `--costs` importent `workflow.py`, donc la déclaration, donc ce qu'elle nomme.
- Le moteur d'agent doit rester hors de cette chaîne.
- Import tardif dans le corps de l'unité, ou `if TYPE_CHECKING:`.
- Tenu par `test_declaring_a_workflow_does_not_load_the_engine`.
- Mesure actuelle : ~130 ms, moteur non chargé.

## Coutures de test

```python
hub.github                                  # GitHub sur papier (fixture `hub`)
core.execution.session.default_runner       # sessions payantes scriptées
binaries.shutil                             # PATH ; résolu à l'appel
```

## Tests de forme

`pipeline/.venv/bin/python -m pytest pipeline/tests`

| Test | Ce qu'il empêche |
| --- | --- |
| `test_every_workflow_carries_the_same_modules_at_its_root` | un module racine manquant |
| `test_every_workflow_keeps_its_own_code_in_internals` | un `.py` de trop à la racine |
| `test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones` | un sous-dossier non nommé |
| `test_every_workflow_declares_a_blueprint` | pas de `WORKFLOW`, ou forme invalide |
| `test_every_workflow_has_a_config_in_the_table` | un workflow sauté en silence |
| `test_a_workflow_never_imports_another_workflow` | couplage entre workflows |
| `test_the_common_package_never_imports_a_workflow` | portes communes captives d'un client |
| `test_no_module_of_the_domain_names_a_workflow` | une instance rangée dans le vocabulaire |
| `test_only_its_own_workflow_names_the_pipeline_labels` | `pipeline:` hors du workflow qui le définit |
| `test_every_layer_only_imports_the_layers_below_it` | un import qui remonte |
| `test_every_module_a_docstring_names_still_exists` | un pointeur mort |

- Les workflows sont découverts, pas listés. Un troisième est vérifié sans intervention.

## Brancher une commande

- `launcher/cli/<nom>.py` : `parse_args`, `config_to_check`, `main`.
- `launcher/routes.py` : une `Route`, avec ses règles.
- `launcher/validation.py` : les règles inter-arguments.
- `scripts/<nom>` : le shim bash.
- Toute variable d'environnement lue doit figurer dans un épilogue `--help`.
