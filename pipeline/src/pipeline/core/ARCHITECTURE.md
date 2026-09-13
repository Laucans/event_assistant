# Architecture — `core/`

Le framework. Ce qui l'utilise : `workflows/ARCHITECTURE.md`.

## Règle unique

- Rien sous `core/` n'importe `workflows/` ni `launcher/`.
- Tenu par `test_nothing_under_core_knows_a_workflow_or_the_launcher`.
- Conséquence : un troisième workflow ne demande de toucher à rien ici.
- Les instances vivent chez leur workflow. `core/` porte la forme.

## Couches

| Couche | Importe | Rôle |
| --- | --- | --- |
| `domain/` | `domain` | vocabulaire pur |
| `runtime/` | `runtime` | support transverse. Feuille |
| `adapters/` | `domain`, `runtime` | l'extérieur, emballé |
| `execution/` | `domain`, `runtime`, `adapters` | faire tourner |
| `design/` | `domain`, `runtime`, `execution` | déclarer |

- Table `ALLOWED` dans `tests/test_layering.py`.
- Un dossier de `core/` absent de la table fait échouer un test.
- Sans ça la règle se tairait au lieu de s'appliquer.

## `domain/`

- Ni disque, ni subprocess, ni bibliothèque externe.
- Interdits scannés : `subprocess`, `sqlite3`, `shutil`, `socket`, `urllib`, `requests`.
- Testable en lui passant des chaînes.
- Ne nomme aucun workflow, même en commentaire.

| Module | Porte |
| --- | --- |
| `stage_spec.py` | `StageSpec` : une étape payante. `EFFORTS` |
| `action.py` | `Action` : une étape locale |
| `issues.py` | `Issue` : ce que GitHub rend |
| `pulls.py` | `Pr` : ce qu'on lit d'une PR |
| `prompts.py` | préambule, bloc de portée, composition |
| `outcomes/result.py` | `Result[T]`, `Status` |
| `outcomes/stage_result.py` | `StageResult`, marqueurs |
| `outcomes/exit_codes.py` | les six codes du processus |

### `Result`

- Les arrêts sont des valeurs. Rien dans le paquet ne lève pour s'arrêter.

| Constructeur | `Status` | Exit | Niveau |
| --- | --- | --- | --- |
| `of(v)` | `OK` | 0 | info |
| `halt(r)` | `HALTED` | 1 | info |
| `unreadable(r)` | `UNREADABLE` | 1 | info |
| `fail(r)` | `FAILED` | 2 | error |
| `quota(r)` | `QUOTA` | 3 | warn |

```python
lu.recast()                  # même échec, autre type de valeur
lu.map(f)                    # ok → transforme
lu.but("le contexte")        # ajoute la raison englobante
```

- `unreadable` existe séparément de `halt` : `[]` se lit « plus rien à faire ».
- `EXIT_CRASH = 4`, `EXIT_INTERRUPTED = 130`. Posés par le launcher.

### Marqueurs

```
AGENT_LOOP_OK:    la session dit ce qu'elle a fait
AGENT_LOOP_STOP:  la session s'arrête d'elle-même
```

- Contrat verbal. Une session sans `OK` retombe sur les vérifications structurelles.

## `runtime/`

- Feuille : n'importe rien du paquet.
- Décide de rien.

| Module | Porte |
| --- | --- |
| `filesystem/paths.py` | `repo_root()`. Résolu une fois, mémorisé |
| `filesystem/workspace.py` | `Workspace` : la racine, et les chemins dérivés |
| `filesystem/lock.py` | `claim(where, name)` : un `mkdir` atomique, un porteur |
| `monitoring/logbook.py` | `Logbook`, `open_logbook`, `null` |
| `monitoring/metrics.py` | `Tally`, `stage_line`, ratios de cache |

- `Workspace` : `loop_dir`, `state`, `ledger`, `flow_db`, `review_dir`, `review_ledger`, `refinement_dir`, `refinement_ledger`, `skills`, `ci_workflow`, `rel()`.
- `paths` n'est nommé que par `runtime/filesystem/`. La racine se reçoit, elle ne se lit pas.
- Niveaux : `VERBOSE`, `NORMAL`, `QUIET`. Le fichier garde toujours DEBUG.
- `log.bind("r3", "code")` estampille les lignes. Rend des journaux entrelacés attribuables.

## `adapters/`

- Un sous-paquet par composant externe.
- Le reste du paquet parle aux interfaces, jamais aux bibliothèques.

### `hub.py`

```python
hub.gh(cfg.workspace)      # GitHub
hub.repo(cfg.workspace)    # git
```

- Seul endroit qui **construit** un client.
- Une seule couture de test pour tous les workflows.
- Construit à l'appel : la racine du dépôt n'existe pas à l'import.

### `agent/`

- `base.py` : `AgentRunner` (ABC), `AgentResult` (neutre), `failure_reason`.
- `claude_sdk.py` : la seule implémentation. **Seul module qui importe `claude_agent_sdk`**.
- Confinement tenu par `test_a_confined_library_appears_in_exactly_one_module`.
- `default_runner()` : import tardif du SDK. Point de branchement d'une 2ᵉ implémentation.
- `progress.py` : `Progress`. Battement sur une horloge, pas sur l'arrivée d'un message.
- Un stage peut passer des minutes dans un seul appel d'outil.
- `failure_reason` rend `"quota"`, `"failed"`, `"empty"`, ou `None`.
- La phrase de quota n'est cherchée que dans un run déjà échoué.
- Un 429 se suffit.

### `shell/`

| Module | Emballe |
| --- | --- |
| `binaries.py` | `installed()`. `shutil` résolu à l'appel, pour la couture de test |
| `git.py` | `Git` : branche, sha, arbre sale, existence de branche |
| `github.py` | `GitHub` : issues, leurs commentaires, sous-issues, bloqueurs, PR, étiquettes |
| `notify.py` | `notify()` via osascript. Ce qu'un humain absent verra |

- Lectures qui décident : rendent `Result`.
- `pr`, `comment_bodies`, `post_comment` : rendent `(valeur, pourquoi)`. Les PR seulement.
- `issue_comments`, `post_issue_comment` : le même geste sur une issue, en `Result`.
- `PR_FIELDS` : les champs demandés à `gh pr view`. Désérialisés en `Pr`.
- L'adaptateur ne décide de rien. Il ne sait pas ce qu'une étiquette signifie.

### `store/`

| Module | Écrit |
| --- | --- |
| `envelope.py` | le JSON du fournisseur, champs filtrés, à côté du log |
| `ledger.py` | deux registres TSV : stages, revues |
| `resume.py` | pointeur + états, sqlite |

- Format des registres gelé caractère pour caractère. Colonnes ajoutées **en fin**.
- Les anciennes lignes restent lisibles.
- `resume` : schéma hérité d'un `@persist` de moteur de graphe. Une ligne par étape.

## `execution/`

### `contract/`

- `workflow.py` : `Workflow`, `Preconditions`, `Postconditions`, `sequence()`.
- `sequence()` : portes → `execute()` → post-vérification. Quinze lignes, jamais réécrites.
- Une précondition qui échoue n'atteint jamais `execute()`.
- Les postconditions ne tournent pas sur un travail qui a échoué.
- `gate.py` : `Check`, `Checked`, `verify_all`. La forme d'un preflight.
- `settings.py` : `WorkflowConfig`. Satisfait `StagePolicy` sauf `prompt_for`.
- `settings.py` : `env_number`, et `ConfigError` — seule exception levée. Une config qui ne se construit pas n'a pas d'appelant.
- `outcome.py` : `WorkflowOutcome`. Un `Result[None]` plus un `summary`.

### Faire tourner

| Module | Rôle |
| --- | --- |
| `context.py` | `Ctx` (par run), `StagePolicy` (ce qu'on exige d'un workflow) |
| `session.py` | une session payante : artefacts, registre, échec → `Result` |
| `stage_runner.py` | filtrer, marquer fait, compter, arrêter |
| `steps.py` | `run_sequence` : les étapes, jusqu'à la première qui échoue |
| `shapes/` | `Once`, `Repeat`, `perform` |

- `StagePolicy` est un `Protocol` : `execution/` ne connaît aucune config concrète.
- `session.run` ne choisit ni le tag des artefacts ni le registre. `cfg` les fournit.
- `Ctx.results[skill]` : ce qu'une étape a rendu. Non persisté.
- `perform` est le seul point qui distingue `StageSpec` de `Action`.
- Pas de moteur, pas de nœuds, pas d'état d'arrêt à se transmettre.

## `design/`

- `blueprint.py` : `Blueprint`. Sept champs, aucun comportement.
- `build.py` : `Gates`, `Obtained`, `Built`, `workflow()`.
- `Built` satisfait `contract.Workflow`. Le lanceur ne voit pas la différence.
- Une facilité, pas un carcan : `execute()` à la main reste valable.

## Chemin rapide

- `--status` et `--costs` doivent répondre sans charger le moteur d'agent.
- Un blueprint est lu à l'import, donc tout ce qu'il nomme est chargé.
- `shapes/` et `design/` annotent `Ctx` et `StageRunner` sous `if TYPE_CHECKING:`.
- Tenu par `test_declaring_a_workflow_does_not_load_the_engine`.
- Mesure : ~130 ms, moteur absent.

## Tests

```
pipeline/.venv/bin/python -m pytest pipeline/tests
```

| Test | Ce qu'il empêche |
| --- | --- |
| `test_nothing_under_core_knows_a_workflow_or_the_launcher` | le framework connaît son utilisateur |
| `test_every_layer_only_imports_the_layers_below_it` | un import qui remonte |
| `test_every_layer_of_core_is_named_by_the_allowed_table` | une couche sans règle |
| `test_a_confined_library_appears_in_exactly_one_module` | le SDK hors de son adaptateur |
| `test_the_domain_touches_neither_the_disk_nor_a_subprocess` | de l'I/O dans le vocabulaire |
| `test_no_module_of_the_domain_names_a_workflow` | une instance dans le vocabulaire |
| `test_only_runtime_filesystem_names_the_paths_module` | la racine relue dans un global |
| `test_declaring_a_workflow_does_not_load_the_engine` | le moteur sur le chemin rapide |

- Chaque scan porte un garde-fou : un scan qui ne trouve rien passerait partout.
