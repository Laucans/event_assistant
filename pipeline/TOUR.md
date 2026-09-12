# Tour du paquet — à lire avant de naviguer

Ce fichier est une **carte**, pas un manuel. Il te dit où sont les choses,
qui dépend de qui, et par où lire. Le détail est dans le code ; `README.md`
dit ce que le produit fait, `INTERNALS.md` dit comment on s'en sert.

5 500 lignes de source, 538 tests, ~5 s.

---

## 1. Le raccourci : trois faits qui expliquent la moitié des décisions

Avant tout le reste, ces trois contraintes reviennent partout. Si un choix te
paraît bizarre, c'est presque toujours l'une des trois.

1. **crewai coûte 1,4 à 1,8 s d'import** (selon le cache) et tire chromadb,
   openai, opentelemetry.
   D'où : il n'existe que dans un fichier, et `--status`/`--costs` répondent
   en 25 ms parce qu'ils ne le croisent jamais.
2. **Les hooks tournent sous le python du système, hors venv, à chaque appel
   d'outil** (~41 ms, dont 21 de démarrage d'interpréteur). D'où :
   `launcher/hooks/**` et le routeur n'importent que la stdlib, et les 7 ms
   d'`import dataclasses` y sont un sujet.
3. **Chaque stage est une session Claude payante.** D'où : tout ce qui peut
   éviter une dépense se fait avant elle, et une lecture ratée ne se rend
   jamais en « rien à faire ».

---

## 2. Les couches, et le sens des dépendances

**Trois dossiers au sommet**, et ils disent qui sert qui :

```
launcher/    le déclenchement : flags, JSON stdin, codes de sortie
workflows/   la définition : un dossier par workflow, tous de la même forme
core/        le framework : ce qui ne sait rien d'aucun workflow
```

`core/` porte les quatre couches, et la flèche va toujours vers le bas :

```
   launcher/    ─┐
   workflows/   ─┴─→ core/
                      ↓
   core/execution/    la mécanique générique : lancer un stage, le sauter
                      ↓
   core/adapters/     l'extérieur, emballé : gh, git, le SDK, crewai, le disque
                      ↓
   core/domain/  core/runtime/    deux feuilles : le vocabulaire, et le support
```

Une flèche = « a le droit d'importer ». **Rien ne remonte**, et surtout :
**rien sous `core/` n'importe `workflows/` ni `launcher/`**. C'est la règle
qui justifie le dossier — dite une fois
(`test_nothing_under_core_knows_a_workflow_or_the_launcher`) là où il fallait
sinon la lire dans quatre lignes de la table `ALLOWED`. C'est aussi ce qui
rend un troisième workflow facile : il se branche sur le framework, le
framework ne se branche sur rien.

Et ce ne sont pas des conventions : `tests/test_layering.py` parcourt l'AST
de chaque fichier et l'assère, imports tardifs compris. Quatorze règles y
vivent :

| Règle | Ce qu'elle empêche |
| --- | --- |
| chaque couche n'importe que celles du dessous | le premier pas vers un cycle |
| rien sous `core/` ne connaît `workflows/` ni `launcher/` | que le framework se branche sur son utilisateur |
| toute couche de `core/` est nommée dans `ALLOWED` | qu'un sous-paquet oublié échappe à toute règle |
| `execution` n'importe **aucun** `workflows` | que la mécanique se lie à un workflow |
| crewai et le SDK dans **un seul** fichier chacun | 1,8 s sur le chemin rapide |
| le launcher : stdlib seule au niveau module | que tous les hooks du dépôt cassent |
| `core/domain/` ne touche ni disque ni subprocess | que le métier cesse d'être testable avec des chaînes |
| `core/domain/` ne nomme aucun workflow | qu'une instance se range dans le vocabulaire |
| aucune étiquette `pipeline:` sous `core/` | que le framework sache ce qu'un workflow appelle une task |
| seul `core/runtime/filesystem/` nomme `paths` | que le global de chemins repousse |
| tout workflow porte les **mêmes** modules à sa racine | que deux workflows cessent de se lire pareil |
| rien d'autre que le contrat à cette racine | que le code propre remonte et recrée la situation d'avant |
| un workflow n'importe **jamais** un autre workflow | qu'ils se relient par un détail (ce que `legacy` faisait) |
| `common/` n'importe **aucun** workflow | que le contrat devienne le premier workflow, les autres accrochés dessus |
| le scan lit bien le paquet | qu'un scan vide fasse passer tout le reste |

**Commence ta revue par ce fichier.** C'est le contrat, et il est exécutable.
Casse une règle volontairement pour voir le message : c'est le meilleur moyen
de savoir ce qui est vraiment tenu.

---

## 3. Les modules, un par un

Pour chaque dossier : ce qu'il contient, **ce dont il dépend**, et **ce qu'il
ne doit jamais toucher**. La colonne « interdit » est celle qui porte le
design — le §2 donne la règle grossière, ceci est le détail réel extrait de
l'AST.

### `core/domain/` — le **vocabulaire** : ce qu'une chose *est*

| Fichier | Rôle |
| --- | --- |
| `issues.py` | ce qu'est une issue : numéro, titre, état, étiquettes, corps, bloqueurs |
| `stage_spec.py` | `StageSpec` : un stage, son modèle, son effort, son texte. Plus `spec_of`/`names`, la lecture d'une table quelconque |
| `prompts/prompt_builder.py` | le préambule, le bloc de portée, l'assemblage. **Aucune prose de stage** |
| `outcomes/stage_result.py` | ce qu'un stage rend + les marqueurs `AGENT_LOOP_OK/STOP` |
| `outcomes/result.py` | `Result[T]` : une valeur ou la raison de son absence, et ce que chaque statut vaut dehors |
| `outcomes/exit_codes.py` | **les codes de sortie** (contrat public) |

**Dépend de** : lui-même, et de rien d'autre. `issues.py` et `stage_spec.py`
ne dépendent de rien du tout.
**Interdit** : `runtime`, `adapters`, tout le reste — et par-dessus tout
`subprocess`, `sqlite3`, `urllib`, le disque.
**Interdit aussi, et c'est la règle qui porte le découpage : nommer un
workflow.** Pas d'import, et pas même une mention dans un commentaire —
`test_no_module_of_the_domain_names_a_workflow` lit le texte des modules.
Quels stages tournent, ce que `pipeline:ready` veut dire, quel texte reçoit
/code : rien de tout ça n'est du vocabulaire, et tout ça vit sous
`workflows/<nom>/`.
**Pourquoi** : c'est ce qui permet à `execution/` de faire tourner n'importe
quel stage sans connaître aucun workflow, et à `adapters/` de rendre des
`Issue` sans savoir ce qu'une étiquette signifie.

### `core/runtime/` — le support qui ne décide de rien

`monitoring/{logbook,metrics}.py` · `filesystem/{paths,workspace}.py`.
`Workspace` porte une racine et les chemins qu'on en dérive ; `paths.py` ne
fait plus que **résoudre** la racine.

**Dépend de** : lui-même seulement. `workspace` → `paths`, et c'est le seul
arc interne.
**Interdit** : tout, `domain` compris. C'est une **feuille au même titre que
le domaine**.
**Le piège historique** : `RunConfig` a vécu ici. Ses méthodes parcourent la
table du pipeline — c'était donc une politique déguisée en réglage. Elle est
partie dans `workflows/`, et c'est ce qui a rendu `runtime/` réellement
feuille.

### `core/adapters/` — l'extérieur emballé

Un sous-dossier par composant externe : le moteur d'agent, le moteur de
graphe, les binaires, le disque.

| Fichier | Rôle |
| --- | --- |
| `agent/base.py` | `AgentRunner` (le port) et `AgentResult` (le résultat neutre) |
| `agent/claude_sdk.py` | **le seul importeur du SDK** |
| `agent/progress.py` | le flux de messages rendu lisible : battement, trace |
| `engine/crewai_engine.py` | **le seul importeur de crewai** : `Flow`, `listen`, `router` |
| `shell/github.py` | `gh`. Le plus gros fichier du paquet |
| `shell/binaries.py` | ce qui est sur le PATH — `claude`, `gh` |
| `shell/{git,notify}.py` | `git`, `osascript` |
| `store/{ledger,resume,envelope}.py` | ce que la boucle écrit et relit sur ce disque |

**Dépend de** : `domain` et `runtime`.
**Interdit** : `execution`, `workflows`, `launcher`.
**Les deux confinements**, assertés : `crewai` n'existe que dans
`engine/crewai_engine.py`, `claude_agent_sdk` que dans `agent/claude_sdk.py`.
**Ce qu'il ne fait pas** : `shell/github.py` rend des `Issue` et ne sait pas
ce qu'une étiquette signifie. `merged_prs(base)` rend les PR mergées ; quelle
PR *vaut preuve de livraison* est la convention donnée à /code, et se décide
dans `agentic_dev_loop/internals/tasks.py`. `test_only_its_own_workflow_names
_the_pipeline_labels` l'assère : aucune étiquette `pipeline:` sous
`workflows/`.

### `core/execution/` — la mécanique, générique par construction

| Fichier | Rôle |
| --- | --- |
| `context.py` | `Ctx` + le `Protocol` `StagePolicy` — **ce que l'exécution exige d'un workflow** |
| `stage_runner.py` | filtrer, marquer fait, compter, **rendre** un arrêt |
| `session.py` | un stage = une session, un résultat, une ligne de registre |

**Dépend de** : `adapters`, `domain`, `runtime`.
**INTERDIT : `workflows`.** C'est la règle ajoutée par ce refactoring, et la
plus importante du paquet pour la suite. Si `execution` importait un
workflow, un second workflow ne pourrait pas réutiliser le lanceur sans
traîner le premier.
**Comment il s'en passe** : il ne connaît pas `RunConfig`, il connaît le
`Protocol` `StagePolicy` (voir §3 bis). C'est du typage **structurel** :
aucun import ne relie `execution` à `workflows`, dans aucun sens.

### `workflows/` — un dossier par workflow, tous de la même forme

> **Tu en ajoutes un ?** `src/pipeline/workflows/how_to_design_a_workflow.md`
> est le mode d'emploi : la checklist, le squelette, le branchement sur une
> commande, et les pièges qui coûtent de l'argent.

**La racine d'un workflow est son contrat, et elle est identique partout** :

```
<workflow>/
├── workflow.py        la classe : config, journal, les 2 gardes, run()
├── settings.py        ce qui varie d'un run à l'autre
├── preconditions.py   ce qui doit tenir avant de payer
├── postconditions.py  ce qu'il doit avoir obtenu
├── stages/            LA DÉFINITION — quels stages, quel modèle, quel texte
└── internals/         la mécanique — propre à ce workflow
```

Deux sous-dossiers, pas un de plus : `test_a_workflow_carries_no_subpackage_
beyond_the_two_named_ones` l'assère, parce que `glob("*.py")` ne descend dans
aucun dossier et qu'un troisième échapperait donc à toute règle de forme.

**`stages/` est le fichier qu'on ouvre pour changer ce que le workflow
fait.** `agentic_dev_loop/stages/` porte `PIPELINE` — une entrée par stage,
avec son modèle, son effort et sa prose — plus `INJECTOR`, le nom que le
préambule cite. `pr_review/stages/` ne porte que la prose : ses deux passes
tirent leur modèle de `ReviewConfig`, parce qu'ils sont réglables à l'appel.

`agentic_dev_loop/internals/` : `flow` (**le graphe : la séquence se lit
ici**) · `gates` (ce qu'un **nœud** exige et doit obtenir) · `board` (le côté
lecture des issues) · `loop` (le budget de rounds) · `state` (l'état
persisté).

`pr_review/internals/` : `review` (l'orchestration) · `passes` (les deux
passes payantes) · `publish` (le commentaire) · `skip_rules` (quelles PR on
ne revoit pas) · `pr` (ce qu'on lit d'une PR).

`common/` porte ce qui n'appartient à aucun : `contract/` (le `Protocol`
`Workflow`, `sequence()`, `WorkflowOutcome`, `WorkflowConfig`) et `utils/`
(`hub` — le seul endroit qui **construit** un adaptateur — et `checks`, les
portes communes).

`legacy/migrate.py` : la bascule, une fois. **Ce n'est pas un workflow** —
elle meurt entière, et le scan de forme l'exempte nommément.

**Dépend de** : `execution`, `adapters`, `domain`, `runtime`, et `common`.
**La règle est désormais écrite et assertée** : un workflow n'importe jamais
un autre workflow, et `common/` n'en importe aucun. C'est ce qui rend le
troisième workflow facile. `legacy/migrate` ne triche plus : il prend sa
fabrique de client dans `common.utils.hub` au lieu d'importer
`agentic_dev_loop.board` — l'ancien point (d) du §6.

L'arbre interne d'`agentic_dev_loop` :

```
workflow  ──►  contract.sequence  ──►  preconditions ──►  checks · board
   │                                   postconditions  (vide : voir plus bas)
   └──►  internals.loop  ──►  flow  ──►  gates  ──┐
                     │         └────►  board  ◄───┤
                     │         └────►  execution.*│
                     └───────────────►  settings ◄┘  (RunConfig : tous le lisent)
                                        state        (RoundState, l'arrêt compris)
```

`settings` est la feuille du workflow : rien dedans ne dépend de `loop` ni de
`flow`. `state` est séparé de `flow` **exprès** — `flow` importe crewai.
Mesuré : `import state` = 0,12 s sans crewai, `import flow` = 1,43 s avec.
Lire l'état persisté ne doit pas payer le moteur. `workflow.py` tient la même
discipline : son import du round est **tardif**, dans le corps d'`execute()`.

**Les `postconditions` des deux workflows sont vides**, et c'est un constat,
pas un oubli — chaque fichier explique lequel. Le round garantit par round
(dans `internals/gates`), la revue garantit en chemin. La classe existe quand
même : c'est le prix de « tous les workflows ont les mêmes classes », et le
jour où il y aura quelque chose à y mettre, l'endroit est déjà nommé.

### Les arrêts sont des valeurs

`core/domain/outcomes/result.py` porte `Result[T]` — une valeur, ou la raison de
son absence. Plus d'exceptions : une porte, une lecture d'API, un stage qui
répond `AGENT_LOOP_STOP` **rendent** un échec que l'appelant propage
(`recast()`, `map()`, `but()`). Les codes de sortie, préfixes et niveaux de
journal sont inchangés — ils sont portés par `Status` au lieu d'une classe
d'exception. Seule `ConfigError` subsiste : une config qui ne se construit
pas n'a personne à qui rendre un `Result`.

**Le prix, et il est réel** : un nœud de flow qui rend un échec n'arrête pas
le graphe — le moteur enchaîne. Chaque nœud s'ouvre donc sur
`if self.state.stopped: return`, et le routeur a une sortie « stop »
qu'aucun nœud n'écoute. Sans ça, un `/code` qui s'arrête laisserait partir
`/create-test`. Deux tests l'asserent ; retire une garde, ils tombent.

### `launcher/` — les deux protocoles d'entrée

`main.py` route, `routes.py` est la table, `validation.py` les règles
inter-arguments. `cli/` parle argv ; `hooks/` parle **JSON sur stdin** et
utilise le code de sortie 2 pour *bloquer* un appel d'outil. Deux protocoles,
un routeur.

**Dépend de** : tout. C'est sa raison d'être — **la seule couche qui a le
droit de tout connaître**, parce que c'est elle qui assemble.
**La contrainte dure** : `main.py`, `routes.py`, `__init__.py` et `hooks/**`
n'importent que la **stdlib au niveau module**. Le routeur fait ses imports
**dans la branche du switch**. Sans ça, un hook paierait l'import de crewai à
chaque appel d'outil — et échouerait, puisqu'il tourne sous le python du
système.
`validation.py` ne dépend que de `domain.stage_spec` et `routes` : pas
d'I/O, pas d'environnement, elle reçoit la config déjà construite — et pas
un workflow, parce qu'elle lit la table qu'on lui passe, jamais la sienne.

---

## 3 bis. L'injection : qui construit quoi, et où

C'est ce qui se reconstitue le plus mal en naviguant, parce que le point de
construction est loin du point d'usage. **Rien n'est un singleton de module.**
Tout ce qui touche l'extérieur est construit à l'appel et descend par
paramètre.

### La règle générale

> Le **launcher** résout. Les couches du dessous **reçoivent**.

Une exception assumée : les chemins rapides (`--status`, `--costs`) résolvent
leur propre `Workspace` dans leur branche, parce qu'ils ne construisent pas
de `RunConfig` — ils ne lisent aucune valeur validée, et le leur faire
construire leur coûterait une lecture d'environnement.

### Les six choses injectées

| Quoi | Construit où | Voyage par | Couture de test |
| --- | --- | --- | --- |
| **`Workspace`** | `build_config`, dans les deux `launcher/cli/*` (`Workspace.here()`) | `RunConfig.workspace` / `ReviewConfig.workspace` → `Ctx.workspace` → les adaptateurs | passer `Workspace(tmp_path)` |
| **`GitHub`** | `board.hub(workspace)` → `GitHub(workspace.root)` | `Board.gh`, gardé à côté de ce qu'il a lu | `monkeypatch.setattr(board, "GitHub", …)` — **la couture unique**, cf. ci-dessous |
| **`AgentRunner`** | `default_runner(workspace)`, **à l'appel** dans `session.run` | `Ctx.runner`, ou le défaut si `None` | poser `ctx.runner`, ou remplacer `session.run` |
| **`Git`** | `preconditions._git(cfg)`, à l'appel | rien — local à la fonction | `Git(root, run=…)` prend son `run` |
| **la table du pipeline** | par défaut `PIPELINE`, champ de `RunConfig` | `cfg.pipeline` / `cfg.rollover` | `RunConfig(pipeline=…)` |
| **le moteur de graphe** | `core/adapters/engine/__init__.py` — **la seule ligne du paquet qui nomme une implémentation** | `Flow`, `listen`, `router` importés par `flow.py` | changer cet import |

### Les trois choses à comprendre absolument

**1. `StagePolicy` est le contrat qui rend `execution` générique.**
`core/execution/context.py` déclare un `Protocol` : `run_id`, `dry_run`,
`verbose`, `permission_mode`, `heartbeat_s`, `stages`, `workspace`, plus
`enabled()`, `resolve()`, `prompt_for()`. `RunConfig` le satisfait
**structurellement** — il n'en hérite pas et ne l'importe pas. C'est ce qui
fait que `execution` ne dépend d'aucun workflow.

`prompt_for()` mérite ton attention : c'est par là que la connaissance de la
branche d'intégration — un concept de l'agentic-dev-loop — est sortie de
`session.py`. Le workflow compose son texte, l'exécution ne fait que
l'envoyer.

⚠️ Ce `Protocol` **n'est vérifié par rien** (point (b) du §6).

**2. Pourquoi les adaptateurs sont construits à l'appel, pas à l'import.**
`board.hub()`, `preconditions._git()`, `default_runner()` sont des
**fonctions**, pas des objets de module. Deux raisons, et chacune a coûté :
un objet de module figerait la racine du dépôt au moment de l'import, et un
test n'aurait plus d'endroit où glisser son double.

Le cas d'école est dans `session.run` : son argument `runner` valait
`default_runner()` **en valeur par défaut**, donc évalué une fois à l'import
du module — un singleton global impossible à remplacer. C'est aujourd'hui
`runner: AgentRunner | None = None`, résolu à l'appel. Si tu vois revenir ce
motif ailleurs, c'est un bug.

**3. La couture unique de GitHub.**
Tout le paquet passe par `common/utils/hub.py` pour obtenir un client.
Résultat : une seule ligne de `tests/conftest.py` —
`monkeypatch.setattr(adapters, "github", lambda root: github.GitHub(root, run=fake))`
— met GitHub sur papier **simultanément** pour le round, la boucle, le
préflight, la revue et `--status`. Et comme le double se branche sur le
paramètre `run` du vrai adaptateur, les tests exercent les vrais chemins
d'API construits, pas une imitation.

La revue garde en plus sa couture par argument (`gh=` sur `PrReview`), parce
qu'elle reçoit parfois un client déjà construit. Elle ne s'en sert plus pour
en **fabriquer** un : c'est `hub` qui le fait, pour tout le monde.

### Ce qui n'est PAS injecté, et pourquoi

- **Le `Logbook`** est passé en paramètre partout, mais construit par le
  launcher. `logbook.null()` sert dans les tests. Ce n'est pas de
  l'injection de dépendance, c'est un paramètre ordinaire.
- **Le `Board`** est passé dans le `Ctx` plutôt que relu par le round :
  pas pour la testabilité, mais pour éviter une seconde salve d'appels
  d'API par round — et surtout pour éviter que deux lectures ne répondent
  pas la même chose.
- **crewai** n'est pas injecté : il est *confiné*. Un seul fichier le nomme,
  et changer de moteur veut dire changer cet import. C'est un choix — pas
  d'abstraction pour un besoin qui n'existe pas encore.

---

## 4. Les flux de données

### Le flux long : un round

```
GitHub (issues)                      .llocal/ (cache local, jamais autoritaire)
      │                                    │
      ▼                                    ▼
 board.read() ──► Board ──► tasks.next_task() ──► la task
                                │
                                ▼
      RoundState  ◄──── persisté par crewai après chaque nœud
                                │
       business-analyst ──► code ──► create-test
                                │
                                ▼
                    postcondition : une PR mergée porte `Closes #N` ?
                                │
                   oui → label `waiting-merge`   non → Halt
```

Deux choses à retenir en lisant :

- **GitHub est la source de vérité.** `.llocal/` ne porte que le point de
  reprise et le registre de coûts — un cache. Si les deux se contredisent,
  GitHub gagne.
- **Aucun stage n'est cru sur parole.** La preuve qu'une task est livrée est
  une PR mergée, pas un stage qui l'affirme. C'est ce que fait
  `internals/gates.py`, et c'est la clé du design.

### Le flux court : un stage

```
RunConfig.prompt_for(stage, extra)          ← le workflow compose le texte
        │
        ▼
session.run ──► AgentRunner.run ──► ClaudeSdkRunner ──► `claude -p`
        │                                   │
        │                            progress ──► battement, trace
        ▼
AgentResult (vocabulaire neutre) ──► StageResult ──► ledger + enveloppe JSON
        │
        ▼
marqueurs lus : AGENT_LOOP_OK / AGENT_LOOP_STOP ──► Halt éventuel
```

Le point à vérifier en lisant : **aucun nom de champ d'Anthropic ne circule
hors de `claude_sdk.py`.** `AgentResult` est là pour ça.

### Le flux des règles (le workflow humain)

```
issue pipeline:roadmap
  └─ pipeline:milestone
       ├─ pipeline:human      ← la porte humaine EST une dépendance blocked_by
       └─ pipeline:agent      ← le corps de l'issue est le SPEC
            + pipeline:ready       ← toi seul le poses. Rien ne tourne sans
            + pipeline:spec-written
            + pipeline:waiting-merge  ← livrée, pas fermée
```

---

## 5. Un ordre de lecture

Quatre heures, dans cet ordre, et tu as le paquet :

1. `tests/test_layering.py` — le contrat. 15 min.
2. `workflows/agentic_dev_loop/internals/tasks.py` — les étiquettes et les
   4 règles. **Le fichier le plus dense
   en décisions du paquet.** 30 min.
3. `workflows/agentic_dev_loop/stages/__init__.py` — la table. 5 min.
4. `core/domain/outcomes/result.py` — comment un arrêt voyage. 10 min.
5. `workflows/common/contract/workflow.py` — la forme que tout workflow a,
   et les quinze lignes de `sequence()`. 15 min.
6. `workflows/agentic_dev_loop/internals/flow.py` — la séquence. 30 min.
7. `workflows/agentic_dev_loop/internals/gates.py` — ce qui prouve. 20 min.
8. `core/execution/{context,stage_runner,session}.py` — la mécanique. 40 min.
9. `core/adapters/agent/base.py` puis `claude_sdk.py` — le port et son unique
   implémentation. 20 min.
10. `launcher/{routes,main,validation}.py` — l'entrée. 20 min.
11. `workflows/agentic_dev_loop/internals/{board,loop}.py` et
    `preconditions.py` — le reste. 40 min.

À **sauter** en première lecture : `core/adapters/shell/github.py` (de la
plomberie `gh api`), `core/adapters/agent/progress.py`, `runtime/monitoring/`,
`launcher/cli/reports.py` (de la mise en forme), et tout `legacy/`.

---

## 6. Ce que je te signale — à toi de te faire un avis

Rien ci-dessous ne casse une règle assertée. Ce sont les endroits où j'ai
hésité, ou que je trouve discutables. Par ordre décroissant d'intérêt.

**a. `StagePolicy` `StagePolicy` n'est vérifié par rien.**
`core/execution/context.py` définit un `Protocol` structurel que `RunConfig` est
censé satisfaire. Il n'y a **aucun type-checker** dans le projet (ni mypy ni
pyright, ni dans `pyproject.toml` ni dans la CI). Renomme un champ de
`RunConfig` et rien ne te le dit avant l'exécution. Soit on ajoute un
type-checker, soit on assume que c'est de la documentation — mais les deux
demandent une décision.

**c. `preconditions.py` a deux vocations.**
Son docstring dit « ce qui est vérifié avant que le premier stage soit payé »,
et c'est vrai des portes de `CHECKS`. Mais `code_has_a_spec` était une porte
**d'un nœud du round**, qui tourne après qu'un stage a été payé, et vivait
dans le même fichier. **Réglé** : `preconditions.py` ne porte plus que les
portes du workflow, et les portes de nœud sont dans `internals/gates.py`
avec les post-conditions de nœud — celles qui n'ont de sens que dans le
graphe.

**d. `workflows/legacy/migrate.py` importait le workflow vivant.**
`from pipeline.workflows.agentic_dev_loop import board`, pour une fabrique de
client de trois lignes. **Réglé** : cette fabrique est dans
`common/utils/hub.py`, et un test assère qu'aucun workflow n'en importe un
autre.

**e. `gates.task_is_delivered` prend cinq arguments**, dont un `StageSpec`
qui ne sert qu'à formuler un message d'erreur. Ça sent le paramètre de trop.

**f. `core/adapters/store/resume.py` connaît le schéma sqlite de crewai.**
Il relit la table `flow_states` que le moteur écrit, en sqlite3 de la stdlib.
C'est un couplage à une bibliothèque externe **hors de son adaptateur** —
assumé et documenté, parce que `--status` ne doit pas payer 1,8 s d'import
pour afficher deux lignes. Le prix à connaître : si crewai change son schéma,
ça casse ici et nulle part ailleurs.

**g. `GitHub` n'a pas de port, contrairement à `AgentRunner`.**
Le moteur d'agent a une interface abstraite et une implémentation ; GitHub a
une classe concrète que trois modules importent directement. L'asymétrie est
délibérée — un seul tracker aujourd'hui, et une interface inventée avant son
second cas d'usage vieillit mal — mais c'est le travail à faire le jour où le
framework sort de ce dépôt.

**h. Deux docstrings mentent légèrement.**
`core/execution/session.py` dit assembler « le texte dans `domain.prompts` » : il
ne l'importe plus, c'est la config qui compose le prompt.
`adapters/agent/__init__.py:16` importe `Workspace` pour une annotation que
`from __future__ import annotations` rend paresseuse — l'import ne sert donc
qu'à un type-checker qui n'existe pas.

**i. Trois bugs connus, non corrigés** (trouvés en revue, tous antérieurs au
refactoring) : le verrou `.lock-<pr>` de la revue n'a pas de péremption et
`--force` ne le contourne pas ; `legacy/migrate.py:147` peut lever un
`KeyError` nu ; et la ligne de fin de round dit « issue #N closed » alors que
le round la laisse ouverte sous `waiting-merge`.

---

## 7. Ce qui est déjà prouvé — n'y dépense pas ton attention

538 tests, dont : les prompts assertés **au bit près** contre des fichiers
oracle produits par l'ancien shell ; les 7 règles de couches ; le fait que
`--status`/`--costs` n'importent ni crewai ni le SDK (en exécutant vraiment
la commande) ; qu'aucune variable d'environnement lue par le code ne manque
d'un épilogue `--help` ; que la table des routes et `validation.py` nomment
exactement les mêmes règles ; et que deux `Workspace` coexistent sans se
marcher dessus.

Ce qui n'est **pas** couvert et mérite ton œil : tout ce qui touche
réellement à `gh` (les tests passent par un double), le comportement réel de
crewai sur une reprise, et les prompts eux-mêmes — aucun test ne peut dire
s'ils sont *bons*, seulement s'ils n'ont pas changé.
