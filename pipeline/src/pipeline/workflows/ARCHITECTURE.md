# Architecture — `workflows/`

Le framework : `../core/ARCHITECTURE.md`. Les entrées : `../launcher/ARCHITECTURE.md`.

## Périmètre

- Un workflow : une chose qu'on lance et qui dépense de l'argent.
- Trois en place : `agentic_dev_loop/`, `pr_review/`, `refinement/`.
- `common/` : les portes et les étiquettes partagées. Pas un workflow.
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
| Client | `pr_review`, `refinement` | `agentic_dev_loop` |
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
| `test_only_its_own_workflow_names_the_pipeline_labels` | `pipeline:` écrit sous `core/` |
| `test_every_layer_only_imports_the_layers_below_it` | un import qui remonte |
| `test_every_module_a_docstring_names_still_exists` | un pointeur mort |

- Les workflows sont découverts, pas listés. Un troisième est vérifié sans intervention.

## Les huit étiquettes

`workflows/common/labels.py` — deux workflows les lisent, aucun ne les possède.

```
pipeline:roadmap        un item de roadmap, source d'un milestone
pipeline:milestone      un milestone ; ses sous-issues sont les tasks
pipeline:agent          une task que la boucle peut faire
pipeline:human          une task que seul l'humain peut faire
pipeline:ready          l'humain autorise celle-ci. Personne d'autre ne la pose
pipeline:spec-written   le SPEC est dans le corps de l'issue
pipeline:waiting-merge  livrée sur la branche d'intégration, pas dans main
pipeline:refinement     cette issue attend un round de raffinage
```

- `LOOP` : les sept que la boucle exige. `pipeline:refinement` n'en est pas — la boucle ne la lit pas.
- `agentic_dev_loop/internals/tasks.py` les réexporte sous leurs noms actuels.
- Créées à la main. Chaque préflight vérifie les siennes avant de payer.
- Une étiquette mal orthographiée rend le tableau vide, et vide déclenche `/planner`.

## `agentic_dev_loop`

- Forme `Repeat`. Une task par round, `MAX_ROUNDS` rounds au plus.
- Table : `/business-analyst` → `/code` → `/create-test`.
- `/code` ouvre sur `/tech-analyst` : le plan n'est écrit dans aucun fichier.
- Un processus neuf le jetterait. D'où `lead` sur l'entrée de table.

| Module | Porte |
| --- | --- |
| `internals/tasks.py` | le modèle en issues. Métier pur, ni I/O ni réseau |
| `internals/board.py` | le côté lecture : milestone, sous-issues, bloqueurs |
| `internals/round.py` | un round : choisir, faire tourner, constater |
| `internals/loop.py` | l'unité que `Repeat` répète. Reprise, comptabilité |
| `internals/state.py` | `RoundState`, pydantic. Ce qu'une reprise retrouve |
| `internals/gates.py` | ce qu'une étape exige et doit obtenir |
| `stages/` | la table `PIPELINE`, `INJECTOR`, et un module de prose par stage |
| `stages/business_analyst.py`, `code.py`, `planner.py` | les consignes propres à chaque stage |

### Les quatre règles de choix

1. Le milestone courant est le `pipeline:milestone` ouvert de plus petit numéro.
2. La task suivante : ouverte, `pipeline:agent`, `pipeline:ready`, pas `waiting-merge`.
   Sous-issue du milestone courant, et tous ses `blocked_by` fermés.
3. `pipeline:human` n'est pas un mécanisme à part. Elle bloque via `blocked_by`.
4. `pipeline:ready` commande tout. Une task non prête arrête le run.

- Un ordre total, pas « l'issue N-1 est-elle fermée ». Le parallélisme est prévu.
- Un bloqueur en `waiting-merge` ne bloque plus : son code est sur la branche.
- Sans cette exception, la chaîne s'arrêterait après une seule task.
- Une task non prête ne fait **pas** basculer en rollover. Confondre coûte un run opus.

### Livrée

```python
CLOSES = r"^[ \t]*(?:closes|fixes|resolves)[ \t]+#(\d+)[ \t]*$"
```

- Plus strict que GitHub, qui accepte le mot-clé n'importe où dans le corps.
- Lire plus large fermerait une issue sur une phrase qui la mentionne.
- GitHub ne ferme une issue liée qu'au merge dans la branche **par défaut**.
- La boucle merge dans `INTEGRATION_BRANCH`. Elle pose donc `waiting-merge`.
- L'issue reste ouverte, n'est plus jamais choisie, ne bloque plus la suivante.

### `Board`

- `read(gh)` compose : milestone courant → sous-issues → bloqueurs.
- Échoue plutôt que de rendre un tableau vide. Vide se lit « milestone fini ».
- Lu une fois par round, passé dans le contexte. Évite une seconde salve d'API.
- `stuck()` distingue deux blocages : tout livré en attente de fusion, ou aucun `ready`.
- Les deux appellent des gestes différents. Les confondre laisse l'humain sans consigne.

## `pr_review`

- Forme `Once`. Deux passes payantes, puis la publication.
- Consultative : ne bloque rien, ne merge rien, ne touche aucune branche.
- La boucle peut merger la PR pendant que la revue s'écrit.

| Module | Porte |
| --- | --- |
| `internals/skip_rules.py` | quelles PR ne sont pas revues |
| `internals/review.py` | pré-contrôle, garde du verrou, phrase de fin |
| `internals/notes.py` | le texte publié : marqueur, pied de page |
| `internals/publish.py` | l'étape de publication |
| `internals/gates.py` | `--no-inline`, dry-run, tolérance de la passe 1 |
| `stages/brief.py` | le prompt des notes de synthèse |

### Les quatre règles de saut

1. La PR ne cible pas la branche d'intégration.
2. La PR est un brouillon.
3. La branche source commence par `test/`.
4. Un commentaire porte déjà le marqueur `<!-- agent-review -->`.

- `--force` les lève toutes.
- Règle 3 : une revue par task, pas par PR. `/code` et `/create-test` ouvrent chacun une PR.
- Revoir celle des tests reverrait deux fois le même changement.
- Le texte publié reste en français : il s'adresse à un humain francophone.

## `refinement`

- Forme `Once`. Le routeur, les cinq sections, puis la publication.
- Écrit le corps d'une issue, par rounds. Remplace `/business-analyst` : le SPEC que `/code` lit sort d'ici.
- N'écrit rien dans l'arbre de travail. Ni porte de branche, ni arbre propre.
- Verrou par issue. Journal, corps et artefacts dans `.llocal/refinement/`, registre à part.

| Module | Porte |
| --- | --- |
| `internals/sections.py` | les cinq sections : `parse`, `render`, `missing`. Métier pur |
| `internals/rounds.py` | le compteur, ce qu'un round écrit, la réponse du routeur. Métier pur |
| `internals/refine.py` | `RefinementState`, pré-contrôle, garde du verrou, phrase de fin |
| `internals/publish.py` | l'étape locale : le corps, le commentaire, les étiquettes |
| `internals/gates.py` | section voulue, routeur éteint, sections nommées, dry-run |
| `stages/__init__.py` | `passes(cfg)`, `prompt_of`, `additional_context` |
| `stages/business_goal.py`, `technical.py`, `acceptance_criteria.py`, `business_rules.py`, `technical_plan.py`, `router.py` | un module de prose par stage |

### Les cinq sections, et le routeur

Titres markdown exacts, en anglais : ils sont écrits tels quels dans le corps.

| Section | Clé | Round | Modèle | Variables |
| --- | --- | --- | --- | --- |
| `## Business Goal` | `business-goal` | 1 | opus / high | `REFINEMENT_GOAL_MODEL` / `_EFFORT` |
| `## Technical` | `technical` | 1 | opus / high | `REFINEMENT_TECHNICAL_MODEL` / `_EFFORT` |
| `## Acceptance Criteria` | `acceptance-criteria` | 1 | sonnet / high | `REFINEMENT_CRITERIA_MODEL` / `_EFFORT` |
| `## Business Rules` | `business-rules` | 2 | opus / high | `REFINEMENT_RULES_MODEL` / `_EFFORT` |
| `## Technical Implementation Plan` | `technical-plan` | 2 | opus / high | `REFINEMENT_PLAN_MODEL` / `_EFFORT` |
| *(le routeur)* | `router` | ≥ 3 | sonnet / low | `REFINEMENT_ROUTER_MODEL` / `_EFFORT` |

- `REFINEMENT_MODEL` force un seul modèle sur les six.
- L'ordre du tableau **est** celui du corps, et celui des étapes.
- Un stage qui n'a rien rendu laisse la section précédente en place. Il ne l'efface pas.

### Les rounds

- Le round courant : le plus grand `N` d'un commentaire `refinement round: N`, plus un.
- Ni fichier d'état, ni étiquette. Le compteur vit là où l'humain le voit et le corrige.
- Un round par invocation. En fin de round, le commentaire `refinement round: N`, rien d'autre.

| Round | Ce qui tourne |
| --- | --- |
| 1 | les trois du round 1. Le corps existant est la matière, puis il est remplacé |
| 2 | les manquantes du round 1, puis les deux du round 2 |
| ≥ 3, sans `--context` | les cinq |
| ≥ 3, avec `--context` | le routeur nomme celles à rouvrir |

- `--context` est injecté dans chaque prompt, sous `additional_context`.
- Un routeur qui ne nomme aucune section échoue : un round muet aurait payé pour rien.

### Les quatre refus d'entrée

1. L'issue est fermée.
2. Elle ne porte ni `pipeline:agent` ni `pipeline:human` — le raffinage travaille une task.
3. Elle ne porte pas `pipeline:refinement`.
4. Ses commentaires ne se lisent pas.

- Vérifiés avant toute session. `--force` ne lève que le troisième.
- Refus 4 : lue comme « aucun commentaire », une lecture ratée ferait repartir le round à 1, par-dessus le travail des précédents.

### Publication

- Le corps est écrit sur disque **avant** d'être envoyé. Un `gh` raté ne perd pas des sections payées, et la phrase dit où elles sont.
- `pipeline:refinement` retirée — seulement si l'issue la portait : `gh` rend 404 sur un `--force`.
- `pipeline:spec-written` posée au round ≥ 2 pour une `pipeline:agent`, ≥ 1 pour une `pipeline:human`.
- Une `pipeline:human` suit la même table et les mêmes rounds. Seul le round où `spec-written` tombe diffère : trois sections suffisent à un humain pour agir.

## `legacy/`

- `migration.py` : le markdown du pipeline, traduit en issues. Métier pur.
- `migrate.py` : l'exécution de cette traduction, une fois.
- Idempotent, et ne pose jamais `pipeline:ready`.
- Meurt entier le jour où plus personne n'en a besoin.

## Ajouter un workflow

1. Copier `pr_review/` — le plus petit, il montre la forme complète.
2. `settings.py`, `preconditions.py`, `stages/`, `internals/`.
3. `workflow.py` : le `Blueprint`.
4. Brancher la commande (ci-dessous).
5. `tests/workflows/<nom>/`, et la config minimale dans `CONFIGS` de `test_shape.py`.

```python
# settings.py — kw_only seulement si un champ n'a pas de défaut.
@dataclass(kw_only=True)
class MaConfig(WorkflowConfig):
    cible: str

    def prompt_for(self, stage, extra) -> str:
        return prompts.build(stage.command, ..., extra)

# preconditions.py — pas de classe : le blueprint reçoit CHECKS.
CHECKS: tuple[Check, ...] = (*checks.TOOLING, Check("ma-porte", ma_porte))

# workflow.py — la déclaration entière.
WORKFLOW = Blueprint(
    name="mon-workflow", config=MaConfig, gates=preconditions.CHECKS,
    artifacts=lambda cfg: cfg.workspace.llocal / "mon-workflow",
    shape=Once(plan=stages.etapes, state=MonEtat, extra=stages.prompt_of),
)
```

- Un champ sans défaut ne peut pas suivre les champs défautés du parent.
- Sans `kw_only`, il faudrait inventer une valeur vide. Le workflow se construirait sans sa cible.

## Pièges

- **N'exprime pas ta séquence en graphe.** Celle du round l'a été.
- Coût constaté : 1,6 s d'import, un `if stopped: return` par nœud, six membres d'état.
- Un moteur déclenche le nœud suivant quelle que soit la valeur de retour du précédent.
- Une séquence qui rend au premier échec n'a besoin d'aucun des trois.
- Un graphe ne se paie qu'avec de vraies branches. Plusieurs, et qui se rejoignent.
- Le round n'en avait qu'une, le rollover. C'est un `if`.

## Brancher une commande

- `launcher/cli/<nom>.py` : `parse_args`, `config_to_check`, `main`.
- `launcher/routes.py` : une `Route`, avec ses règles.
- `launcher/validation.py` : les règles inter-arguments.
- `scripts/<nom>` : le shim bash.
- Toute variable d'environnement lue doit figurer dans un épilogue `--help`.
