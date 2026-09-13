# Contribuer à `pipeline/`

Référence d'exécution pour un agent qui modifie ce paquet : **où va ce que
j'écris**, **ce qui est interdit**, **quelle commande le prouve**.

Les raisons derrière chaque règle sont dans les `ARCHITECTURE.md`. Elles ne
sont pas répétées ici — ce fichier est la surface d'action, pas la carte.

Portée : `pipeline/` uniquement. Le produit (`src/`, TypeScript) suit
`CLAUDE.md` et `ONBOARDING.md`.

---

## 0. Séquence obligatoire

```bash
# 1. lire, dans cet ordre
pipeline/ARCHITECTURE.md                          # la carte, les invariants
pipeline/src/pipeline/<paquet>/ARCHITECTURE.md    # la couche touchée

# 2. baseline verte AVANT d'écrire
pipeline/.venv/bin/python -m pytest pipeline/tests     # 667 tests, ~3 s

# 3. écrire

# 4. prouver (§6)
```

- Un test rouge à l'étape 2 n'est pas ton changement. Dis-le, ne le corrige pas
  en passant.
- Plus d'un fichier touché → explorer et planifier avant d'éditer.
- Correction de bug → le test qui échoue s'écrit **avant** le correctif.
- Le venv est sur **3.14**. Il n'y a pas de linter Python ici : les
  conventions de §4 sont tenues par la relecture, pas par un outil.

---

## 1. Interdits

Chaque ligne est tenue par un test. La colonne de droite nomme celui qui
tombera — utilise-la pour prédire l'échec avant de lancer la suite.

| Interdit | Test qui échoue |
| --- | --- |
| un module de `core/` importe `workflows/` ou `launcher/` | `test_nothing_under_core_knows_a_workflow_or_the_launcher` |
| une couche importe une couche au-dessus d'elle | `test_every_layer_only_imports_the_layers_below_it` |
| un nouveau dossier sous `core/` absent d'`ALLOWED` | `test_every_layer_of_core_is_named_by_the_allowed_table` |
| `claude_agent_sdk` importé hors de `core/adapters/agent/claude_sdk.py` | `test_a_confined_library_appears_in_exactly_one_module` |
| `subprocess` `sqlite3` `shutil` `socket` `urllib` `requests` dans `core/domain/` | `test_the_domain_touches_neither_the_disk_nor_a_subprocess` |
| un module de `core/domain/` **nomme** un workflow, commentaire compris | `test_no_module_of_the_domain_names_a_workflow` |
| `pipeline:` écrit sous `core/` | `test_only_its_own_workflow_names_the_pipeline_labels` |
| le module `paths` nommé hors de `core/runtime/filesystem/` | `test_only_runtime_filesystem_names_the_paths_module` |
| un import hors stdlib au niveau module dans `launcher/main.py`, `routes.py`, `launcher/__init__.py`, `launcher/hooks/*` | `test_the_launcher_entry_points_import_only_the_standard_library` |
| le moteur importé au niveau module par `core/design/*` ou `core/execution/shapes/*` | `test_declaring_a_workflow_does_not_load_the_engine` |
| un 4ᵉ `.py` à la racine d'un workflow | `test_every_workflow_keeps_its_own_code_in_internals` |
| un 3ᵉ sous-dossier dans un workflow | `test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones` |
| un workflow importe un autre workflow | `test_a_workflow_never_imports_another_workflow` |
| `workflows/common/` importe un workflow | `test_the_common_package_never_imports_a_workflow` |
| une docstring nomme un module qui n'existe plus | `test_every_module_a_docstring_names_still_exists` |
| une variable d'environnement absente d'un épilogue `--help` | `test_every_environment_variable_the_code_reads_is_in_a_help_epilog` |
| la même, absente de `.env.example` | `test_every_environment_variable_the_code_reads_is_in_env_example` |
| une route ajoutée sans mise à jour de la table attendue | `test_the_table_names_the_two_commands_and_the_four_hooks` |

**Le moteur**, au sens du test : `core.execution.session`, `stage_runner`,
`context`, `core.adapters.agent`. Sous `if TYPE_CHECKING:` ou dans un corps
de fonction, pas au niveau module.

Interdits qu'aucun test ne rattrape — c'est la relecture qui les tient :

- **Lever une exception pour s'arrêter.** Tout rend un `Result`. Seule
  exception encore levée dans le paquet : `ConfigError`.
- **Appeler un binaire hors de `adapters/`.** Une porte, une politique, un
  workflow *décident* ; ils n'appellent jamais `subprocess`, `shutil.which`
  ni `gh` eux-mêmes. Cf. §3.8.
- **Rendre `[]` sur une lecture ratée.** Vide se lit « plus rien à faire » et
  déclenche un `/planner` opus. Rends `Result.unreadable(...)`.
- **Capturer une fonction système en argument par défaut**
  (`which=shutil.which`) : figée à l'import, le monkeypatch ne prend plus.
  Résous-la à l'appel.
- **Ajouter un commentaire ou une docstring « de design »** — le pourquoi
  d'un choix, ce qu'une erreur a coûté. Le paquet en est saturé et ils sont
  voués à disparaître. Lors d'un déplacement de code, transporte l'existant
  **verbatim** (en corrigeant seulement les chemins de modules cités). Pour
  du code neuf : une ligne factuelle qui dit ce que fait la fonction.

---

## 2. Où va ce que j'écris

| Ce que j'ajoute | Destination | Jamais |
| --- | --- | --- |
| un type de valeur (ce qu'une chose *est*) | `core/domain/` | ni I/O, ni nom de workflow |
| un chemin, un journal, une mesure | `core/runtime/` | aucune décision |
| un appel à `gh`, `git`, le PATH, le SDK | `core/adapters/shell`, `agent` | rien d'autre n'appelle |
| un magasin sur disque (registre, enveloppe, sqlite) | `core/adapters/store/` | pas de format changé au milieu |
| de la mécanique de run (session, étapes, portes) | `core/execution/` | aucune config concrète |
| une façon de déclarer un workflow | `core/design/` | pas le moteur au niveau module |
| quels stages tournent, avec quel texte | `workflows/<nom>/stages/` | pas dans `domain/` |
| la mécanique propre à un workflow | `workflows/<nom>/internals/` | pas à la racine du workflow |
| une porte partagée par tous les workflows | `workflows/common/checks.py` | ne nomme aucun workflow |
| une commande, un hook, du routage | `launcher/` | aucune décision métier |

Structure imposée d'un workflow — trois `.py` à la racine, deux sous-dossiers,
exactement :

```
workflows/<nom>/
├── __init__.py
├── workflow.py       le Blueprint, et rien d'autre
├── settings.py       la config + la politique de session
├── preconditions.py  CHECKS, announce
├── stages/           la table des stages, et leur prose
└── internals/        le reste
```

---

## 3. Recettes

Chaque recette : les fichiers **dans l'ordre**, puis la commande qui prouve.
Les chemins sont relatifs à `pipeline/src/pipeline/`.

### 3.1 Changer le modèle ou l'effort d'un stage

1. `workflows/agentic_dev_loop/stages/__init__.py`, table `PIPELINE` — une ligne.

Recale-toi sur `.llocal/agent-loop/costs.tsv`, pas sur l'intuition.

### 3.2 Changer ce qu'un stage dit au modèle

1. `workflows/agentic_dev_loop/stages/<stage>.py` — une constante de prose.
2. Si le préambule ou le bloc de portée bouge : `tests/oracle/prompt-*.txt`.

Les oracles comparent le prompt **caractère pour caractère**. Code et oracle
se mettent à jour dans le même commit, jamais l'un sans l'autre.

### 3.3 Ajouter un stage au round

1. `workflows/agentic_dev_loop/stages/<nom>.py` — sa prose (ou `""` dans la table).
2. `workflows/agentic_dev_loop/internals/gates.py` — `skip` / `before` / `after`.
3. `workflows/agentic_dev_loop/stages/__init__.py` — l'entrée dans `PIPELINE`.
   **L'ordre de la table est l'ordre d'exécution.**
4. `tests/workflows/agentic_dev_loop/test_stages.py` — deux tests nomment la
   séquence et sa longueur ; mets-les à jour délibérément.

### 3.4 Ajouter une porte de préflight

1. `workflows/common/checks.py` si toutes les commandes l'exigent, sinon
   `workflows/<nom>/preconditions.py`.
2. Signature : `verify(cfg, log) -> Result[None]`. **Une porte ne lève jamais.**
3. La raison rendue doit **nommer le geste qui débloque**, pas constater.
4. L'ajouter au tuple `CHECKS` ; `verify_all` s'arrête à la première qui échoue,
   donc l'ordre suppose les précédentes.

### 3.5 Ajouter un workflow

1. Copier `pr_review/` — le plus petit, il montre la forme complète.
2. `settings.py` : hériter de `WorkflowConfig`, `@dataclass(kw_only=True)` dès
   qu'un champ n'a pas de défaut. Redéfinir `prompt_for` (sans défaut, à
   dessein) et seulement ce qui diffère.
3. `preconditions.py` : `CHECKS: tuple[Check, ...]`.
4. `stages/`, `internals/`.
5. `workflow.py` : `WORKFLOW = Blueprint(...)`, sept champs.
6. `launcher/cli/<nom>.py`, `launcher/routes.py`, `launcher/validation.py`,
   `scripts/<nom>` (copier `scripts/pr-review`).
7. `tests/workflows/<nom>/`, **et** la config minimale dans `CONFIGS` de
   `tests/workflows/test_shape.py` — un workflow absent de cette table fait
   échouer le test au lieu d'être sauté.

Les workflows sont découverts, pas listés : le reste des tests de forme le
couvre sans intervention.

### 3.6 Ajouter un hook

1. `launcher/hooks/<nom>.py` — **stdlib seule**, il tourne hors venv à chaque
   appel d'outil.
2. `launcher/routes.py` — une `Route` de protocole `hook`, sans règle.
3. `scripts/hooks/<nom>.py` — le shim.
4. `.claude/settings.json` — le câblage (passe par le subagent
   `vibe-specialist`, c'est une règle du dépôt).
5. `tests/test_layering.py` — la liste en dur de
   `test_the_stdlib_only_scan_covers_the_router_and_every_hook`.
6. `tests/launcher/test_routes.py` — `test_the_table_names_the_two_commands_and_the_four_hooks`.

Protocole : JSON sur stdin, JSON ou rien sur stdout, `exit 2` bloque. Réponse
en millisecondes. **Il échoue ouvert** — un hook cassé ne doit jamais arrêter
le travail. Les deux gardes de sécurité (`branch_guard`, `no_secret_paths`)
sont l'exception : elles échouent fermées, en sortant en 2.

### 3.7 Ajouter une commande CLI

1. `launcher/cli/<nom>.py` — trois fonctions, c'est l'interface du routeur :
   `parse_args(argv)`, `config_to_check(args)` (`None` = rien à valider),
   `main(argv) -> int`.
2. `main` est **le seul endroit qui journalise la raison** :
   `outcome.report(log).exit_code`.
3. Purger `ANTHROPIC_API_KEY` et `ANTHROPIC_AUTH_TOKEN` avant tout import —
   une clé sortirait le run de l'abonnement et le mettrait sur un compte facturé.
4. Un épilogue `--help` qui nomme **toutes** les variables lues et les codes de
   sortie.
5. `launcher/routes.py`, `launcher/validation.py`, `scripts/<nom>`.

### 3.8 Faire un appel externe (`gh`, `git`, le PATH)

1. Ajouter la méthode à `core/adapters/shell/github.py`, `git.py` ou
   `binaries.py`.
2. La lire depuis la porte ou le workflow, via `hub.gh(cfg.workspace)` /
   `hub.repo(cfg.workspace)` — `core/adapters/hub.py` est le seul endroit qui
   **construit** un client, et la seule couture de test.
3. Une lecture qui décide rend un `Result`. L'adaptateur ne décide de rien :
   il ne sait pas ce qu'une étiquette signifie.

### 3.9 Ajouter une variable d'environnement

1. La lire dans le `settings.py` du workflow, via `env_number` si elle est
   numérique (le vide vaut absent ; une valeur illisible nomme la variable).
2. L'épilogue `--help` de la commande.
3. `.env.example`, à la racine du dépôt — committé, jamais de vraie valeur.

Deux tests balayent ces trois points.

### 3.10 Toucher à un format de registre

`.llocal/agent-loop/costs.tsv` et le registre des revues sont **gelés
caractère pour caractère**. Une colonne s'ajoute **en fin**, jamais ailleurs :
les anciennes lignes doivent rester lisibles.

---

## 4. Style

- **Docstrings et commentaires en français sans accents** dans les `.py`. Les
  accents sont réservés aux chaînes destinées à un humain (aide CLI, prompts,
  texte publié sur une PR). Les `.md` gardent leurs accents.
- Lignes ≤ **79 colonnes**.
- `from __future__ import annotations` en tête de tout module qui annote
  (les `__init__.py` et les hooks s'en passent).
- `@dataclass(frozen=True)` pour une valeur du domaine ;
  `@dataclass(kw_only=True)` dès qu'un champ sans défaut suit un champ défauté.
- `Protocol` quand une couche basse doit nommer un type qu'elle n'a pas le
  droit d'importer (`StagePolicy`, `Checked`, `Step`, `Workflow`).
- Les arrêts sont des valeurs :

  | Constructeur | Exit | Sens |
  | --- | --- | --- |
  | `Result.of(v)` | 0 | abouti |
  | `Result.halt(r)` | 1 | arrêt volontaire, un humain agit |
  | `Result.unreadable(r)` | 1 | un magasin n'a pas répondu |
  | `Result.fail(r)` | 2 | rien d'exploitable |
  | `Result.quota(r)` | 3 | fenêtre épuisée, revenir plus tard |

  `.recast()` garde l'échec en changeant le type, `.map(f)` transforme un
  succès, `.but("contexte")` ajoute la raison englobante.
- Une raison d'arrêt **nomme le geste qui débloque**. « spec manquant » est
  une constatation ; « le corps de l'issue #42 ne contient pas de SPEC —
  lance /business-analyst » est une consigne.

---

## 5. Tests

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests            # tout
pipeline/.venv/bin/python -m pytest pipeline/tests/workflows  # un dossier
pipeline/.venv/bin/python -m pytest pipeline/tests -k tasks   # un motif
```

- `pipeline/tests/` **miroite** `src/pipeline/` : un module de
  `workflows/agentic_dev_loop/internals/` se teste dans
  `tests/workflows/agentic_dev_loop/`.
- Nom de test : une phrase anglaise qui dit ce qu'il empêche
  (`test_a_task_without_the_ready_label_is_never_picked`). Docstring française
  facultative, une ligne.
- **Aucun réseau, aucune vraie session payante.** Trois coutures, et trois
  seulement :

  | Couture | Remplace |
  | --- | --- |
  | fixture `hub` (`FakeGitHub`) | GitHub, pour le round, la revue, le préflight et `--status` |
  | fixture `fake_sdk` | `claude_agent_sdk`, pour les sessions payantes |
  | `binaries.shutil` | le PATH ; résolu à l'appel |

- Le métier pur (`internals/tasks.py`, `domain/`) se teste en lui passant des
  objets construits à la main. Pas de double.
- **Tout scan de l'AST porte un garde-fou** : une assertion qui prouve que le
  scan lit encore quelque chose. Un scan devenu vide passerait partout. Si tu
  ajoutes une règle scannée, ajoute son garde-fou dans le même test.
- Les tests oracle (`tests/oracle/`) comparent une sortie au caractère près :
  prompts, rapport de coûts, notes de revue, cas de `branch-guard`.

---

## 6. Vérifier

Dans cet ordre, sortie affichée. « Ça a l'air fait » n'est pas une
vérification.

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests     # 1. la suite entière
scripts/agent-loop --dry-run                           # 2. écrit les prompts, n'appelle rien
scripts/agent-loop --status                            # 3. le chemin rapide répond (~130 ms)
scripts/agent-loop --costs                             # 4. idem, registre lisible
```

- Étape 2 ne coûte rien et ne contacte personne : c'est la vérification de
  bout en bout la moins chère du paquet.
- Si tu as touché à `core/design/`, `shapes/` ou à un import de `workflow.py`,
  mesure le chemin rapide :

```bash
time pipeline/.venv/bin/python -m pipeline.launcher loop --status
```

- `npm test` **ne couvre pas** `pipeline/`. Les deux suites sont séparées ;
  la CI lance les deux dans le même job.

---

## 7. Livrer

- Branche `<type>/<slug>`, type parmi `feat` `fix` `docs` `style` `refactor`
  `test` `chore` `AIchore`. Ce qui touche à `pipeline/` ou à l'outillage
  agentique est `AIchore`.
- **Ne pousse jamais sur `main`.** Un hook `PreToolUse` bloque la commande ;
  le bypass admin fonctionnerait, c'est bien pour ça que le hook existe.
- Message de commit : `<type>(<scope>): <description>`, scope `pipeline` pour
  ce paquet, description en français à l'impératif ou au présent, sans accent
  obligatoire mais cohérente avec l'historique.
- Une PR est obligatoire, une approbation ne l'est pas. `ci` vert →
  `gh pr merge --rebase` (seule méthode activée).
- Une PR qui doit fermer une issue porte `Closes #N` **sur sa propre ligne** :
  le round lit exactement cette forme, plus stricte que GitHub.
- **Les issues de ce dépôt sont publiques.** Nomme un identifiant, jamais sa
  valeur ; garde les URL de dashboard dehors.
- Toute PR ouverte contre `main_agent` déclenche une revue consultative
  détachée. Elle ne bloque rien et peut arriver après le merge.

---

## 8. Pièges qui coûtent de l'argent

- **Ne supprime pas `.llocal/agent-loop/state`.** C'est ce qui empêche de
  repayer des stages déjà faits. `--status` dit ce qu'il porte.
- **`--restart` oublie les stages faits pour la task en cours** et la rejoue
  entièrement, y compris un `/code` dont la PR a déjà mergé.
- **Une lecture dégradée arrête le run exprès.** Si tu vois « cannot read »,
  ne contourne pas : lire un magasin illisible comme « rien n'a tourné » est
  précisément ce qui fait repayer un stage.
- **Une task non prête n'est pas un rollover.** Confondre les deux dépense un
  run opus pour ouvrir un item de roadmap que personne n'a demandé.
- **`pipeline:ready` n'est posé que par l'humain.** Aucun skill, aucun code,
  aucun agent ne le pose.
- **Un exit 1 n'est pas un échec** : c'est un arrêt volontaire, et la phrase
  nomme le geste qui débloque.
- Une étiquette mal orthographiée rend le tableau vide, et vide déclenche un
  `/planner`.

---

## 9. Pointeurs

| Document | Répond à |
| --- | --- |
| `README.md` | ce que le runner fait, et comment s'en servir |
| `ARCHITECTURE.md` | la carte des trois paquets, les invariants |
| `src/pipeline/core/ARCHITECTURE.md` | le framework, couche par couche |
| `src/pipeline/workflows/ARCHITECTURE.md` | ce qu'est un workflow |
| `src/pipeline/launcher/ARCHITECTURE.md` | routage, protocoles, codes de sortie |
| `CONTRIBUTION.md` | ce fichier : où écrire, ce qui est interdit, ce qui le prouve |
| `../CLAUDE.md` | les règles du dépôt entier, produit compris |
| `../ONBOARDING.md` | la prise en main humaine du dépôt |

Le détail est dans le code. Ces documents ne le paraphrasent pas.
