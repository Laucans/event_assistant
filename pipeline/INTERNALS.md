# pipeline — internals

Le runner de la boucle documentaire. Remplace `scripts/agent-loop.sh` et
`scripts/pr-review.sh` (~610 lignes de bash utile), supprimés dans le même
lot.

## Installer

CrewAI plafonne à `python < 3.14` et la machine tourne en 3.14 : le venv est
donc épinglé sur un 3.13.

```bash
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv pipeline/.venv
pipeline/.venv/bin/pip install -e 'pipeline[dev]'
```

## Utiliser

```bash
scripts/agent-loop                 # dépense le budget de rounds
scripts/agent-loop --rounds 1      # une task
scripts/agent-loop --status        # d'où repartirait un re-run
scripts/agent-loop --costs         # ce que la boucle a dépensé, par stage
scripts/agent-loop --dry-run       # écrit les prompts, n'appelle rien
scripts/agent-loop --restart       # oublie les stages déjà faits
scripts/agent-loop --costs-by task # ce que chaque task a coûté
scripts/agent-loop -v / -q         # tous les appels d'outil / le silence
scripts/agent-loop migrate --dry-run  # le markdown -> des issues, à blanc
scripts/pr-review <pr>             # la revue consultative d'une PR

pipeline/.venv/bin/python -m pytest pipeline/tests    # 514 tests, ~5 s
```

## Où vit l'état du projet

Dans les **issues GitHub**, plus dans `docs/`. Un item de roadmap porte
`pipeline:roadmap` ; un milestone `pipeline:milestone`, en sous-issue de
l'item dont il descend ; une task `pipeline:agent` et une action humaine
`pipeline:human`, toutes deux en sous-issues du milestone.

```
[pipeline:roadmap]
  └─ [pipeline:milestone]      corps = Problem / Goals / Approach / Out of scope
       ├─ [pipeline:human]     ce que l'humain doit faire
       └─ [pipeline:agent]     corps = le SPEC, écrit par /business-analyst
```

Quatre règles, et `domain/tasks.py` les porte seul :

1. le **milestone en cours** est le `pipeline:milestone` ouvert de plus petit
   numéro ;
2. la **task suivante** est une `pipeline:agent` ouverte, sous-issue de ce
   milestone, portant `pipeline:ready`, et dont **tous** les `blocked_by` sont
   fermés — un vrai parcours de graphe, pas « l'issue N-1 est-elle fermée » :
   le parallélisme ne doit pas demander une migration de données pour
   arriver ;
3. une action humaine n'est **pas** un mécanisme à part : elle bloque parce
   qu'elle est dans les `blocked_by` ;
4. **`pipeline:ready` commande tout.** Une task ouverte mais pas prête arrête
   le run — et surtout ne le fait pas basculer en rollover, qui dépenserait un
   run opus pour ouvrir un item que personne n'a demandé.

Une task est **finie quand son issue se ferme**, et c'est GitHub qui la ferme,
au merge d'une PR portant `Closes #N`. Le runner ne ferme rien : il constate,
et s'arrête si rien ne l'a fait.

Un **milestone terminé doit être fermé**, et c'est `/planner` qui le fait en
ouvrant le suivant. La règle 1 lit le milestone ouvert de plus petit numéro :
en laisser un fini ouvert ferait rouler tous les rounds suivants à vide sur
lui, sans jamais voir ce qui vient d'être planifié. Le round le dit avec ces
mots-là si ça arrive.

`gh` n'a de flag natif ni pour les sous-issues ni pour les dépendances : tout
passe par `gh api`, dans `adapters/shell/github.py`.

### La bascule

`scripts/agent-loop migrate` traduit `docs/ROADMAP.md` et `docs/current/` en
issues, une fois, puis les supprime. Elle est **idempotente** (chaque issue est
cherchée par titre et étiquette avant d'être créée) et `--dry-run` imprime
exactement ce qu'elle créerait sans rien écrire. Rien n'en sort avec
`pipeline:ready` : le robinet, c'est l'humain qui l'ouvre.

Variables d'environnement de la boucle : `INTEGRATION_BRANCH`,
`PERMISSION_MODE`, `MAX_ROUNDS`, `STAGES`, `MODEL`, `EFFORT`, `ALLOW_DIRTY`,
`HEARTBEAT_SECONDS`, `PIPELINE_CREWAI_PANELS`.

Celles de la revue : `INTEGRATION_BRANCH`, `PR_REVIEW_LEVEL`,
`PR_REVIEW_MODEL`, `PR_REVIEW_INLINE_MODEL`, `PR_REVIEW_INLINE_EFFORT`,
`PR_REVIEW_BRIEF_MODEL`, `PR_REVIEW_BRIEF_EFFORT`.

Les deux listes sont dans l'épilogue de `--help` — un bouton que personne ne
trouve est un bouton que personne ne tourne — et un test vérifie qu'aucune
variable lue par le code n'en manque. Les codes de sortie y sont aussi, et
plus bas.

## Comment c'est organisé

Le paquet est rangé en couches, et le sens des dépendances ne remonte jamais.
`tests/test_layering.py` en fait une assertion : chaque règle ci-dessous est
vérifiée en parcourant l'AST de chaque fichier, imports tardifs compris.

```
launcher/   les points d'entrée : un routeur, les commandes, les hooks
workflows/  un sous-paquet par workflow, tous de la même forme
            (common/ porte le contrat et ce qu'ils réutilisent)
execution/  faire tourner un stage, sans rien savoir du workflow
adapters/   tout composant externe, emballé derrière une interface à nous
runtime/    chemins, journal, mesures — une feuille, comme domain/
domain/     le métier pur : la table, les textes, les règles, les arrêts
```

`domain/` et `runtime/` sont rangés en sous-paquets — `domain/stages/`,
`domain/prompts/`, `domain/outcomes/`, `domain/pr_review/`,
`domain/legacy/` ; `runtime/monitoring/`, `runtime/filesystem/`. Les
`__init__.py` de ces sous-paquets ne ré-exportent rien : un appelant écrit
le chemin complet (`from pipeline.domain.outcomes.result import Result`).
L'exception est `domain/prompts/definitions/__init__.py`, qui *est* le
registre.

### `domain/` — ce que la boucle *est*

Aucun I/O, aucun subprocess, aucune bibliothèque externe. C'est ce qui rend
ces décisions testables en leur passant des chaînes de caractères.

| Module | Rôle |
| --- | --- |
| `tasks.py` | la forme d'une issue, et les quatre règles qui choisissent la task |
| `stages/stage_spec.py` | `StageSpec` et les niveaux d'effort — générique, tout workflow s'en sert |
| `stages/agentic_dev_loop_stages.py` | la table de CE workflow, typée — **la surface de design** |
| `prompts/prompt_builder.py` | le préambule, la portée et la composition, repris au bit près du shell |
| `prompts/definitions/__init__.py` | **le registre** : le dict `{stage: consignes}`, et `NO_INSTRUCTIONS` |
| `prompts/definitions/agentic_dev_loop/*.py` | un module par stage, une constante chaîne par module |
| `prompts/definitions/pr_review/brief.py` | `BRIEF_PROMPT`, le prompt de la passe « brief » |
| `pr_review/notes.py` | ce que la revue publie : marqueur, pied de page, commentaire |
| `outcomes/stage_result.py` | ce qu'un stage rend, et les marqueurs `AGENT_LOOP_OK` / `AGENT_LOOP_STOP` |
| `outcomes/result.py` | `Result[T]` : une valeur, ou la raison de son absence — et ce que chaque statut vaut dehors |
| `outcomes/exit_codes.py` | les codes de sortie qu'un ordonnanceur extérieur lit |
| `legacy/migration.py` | le markdown traduit en plan d'issues — écrit pour être supprimé |

Les consignes d'un stage sont **des modules Python, pas des `.md`** : le
domaine ne lit pas le disque, et une constante triple-quote se relit aussi
bien qu'un fichier de prose. Le registre est **explicite** — un import nommé
par module de définition — parce qu'une découverte par nom de fichier
rendrait un stage muet sur une faute de frappe. Un stage qui n'a
légitimement aucune consigne est nommé dans `NO_INSTRUCTIONS` (`create-test`
aujourd'hui), et un test exige que toute entrée de `PIPELINE` soit dans l'un
ou dans l'autre.

### `adapters/` — l'extérieur, emballé

| Module | Rôle |
| --- | --- |
| `agent/base.py` | `AgentRunner` (l'interface) et `AgentResult` (le résultat neutre) |
| `agent/claude_sdk.py` | `ClaudeSdkRunner` — **le seul importeur de `claude-agent-sdk`** |
| `agent/progress.py` | le flux du SDK rendu lisible : battement, trace par stage, recensement |
| `engine/crewai_engine.py` | **le seul importeur de crewai** : primitives de graphe, panneaux, persistance |
| `shell/git.py`, `shell/github.py`, `shell/notify.py` | `git`, `gh`, `osascript` |
| `store/ledger.py` | `costs.tsv`, même format qu'avant — écrit et relu, pas mis en forme |
| `store/resume.py` | le point de reprise : pointeur lisible + lecture sqlite du magasin |
| `store/envelope.py` | l'enveloppe JSON qu'un stage ou une passe laisse derrière |

### `execution/` — faire tourner un stage

Générique : rien ici n'importe un workflow, et le test de couches l'assère.

| Module | Rôle |
| --- | --- |
| `context.py` | `Ctx`, et le `Protocol` `StagePolicy` qu'un workflow doit satisfaire |
| `stage_runner.py` | **l'orchestration** : filtrer, marquer, compter, arrêter |
| `session.py` | un stage = une session d'agent, un résultat, une ligne de coût |

### `workflows/` — un sous-paquet par workflow, tous de la même forme

> Pour en **ajouter** un, le mode d'emploi est
> `src/pipeline/workflows/how_to_design_a_workflow.md`. Cette section-ci
> décrit ce qui existe ; celui-là dit comment s'y conformer.

**Tout workflow porte les mêmes quatre modules à sa racine**, et son code
propre dans `internals/`. La racine est le contrat ; `internals/` n'a pas à
se ressembler d'un workflow à l'autre. Quatre tests de
`tests/test_layering.py` le gardent vrai — un module de plus à la racine, ou
un workflow qui en importe un autre, les fait échouer.

| Module (à la racine de chaque workflow) | Rôle |
| --- | --- |
| `workflow.py` | la classe du workflow : config, journal, les deux gardes, et `run()` qui délègue à la séquence commune |
| `settings.py` | ce qui varie d'un run à l'autre, par-dessus `WorkflowConfig` |
| `preconditions.py` | ce qui doit tenir **avant** que quoi que ce soit soit payé |
| `postconditions.py` | ce que le workflow doit avoir obtenu — vide est un résultat valable, et les deux le disent |

| Module commun | Rôle |
| --- | --- |
| `common/contract/workflow.py` | le `Protocol` `Workflow`, et `sequence()` — les quatre lignes qu'aucun workflow ne réécrit |
| `common/contract/outcome.py` | `WorkflowOutcome` : ce qu'un workflow rend à son lanceur |
| `common/contract/settings.py` | `WorkflowConfig` : workspace, `--dry-run`, verbosité, battement |
| `common/utils/hub.py` | `gh()` et `repo()` — le seul endroit du paquet qui **construit** un adaptateur |
| `common/utils/checks.py` | les portes qui ne sont propres à aucun workflow : `claude`/`gh` sur le PATH, `gh` authentifié, la branche d'intégration, l'arbre propre |

| Interne à un workflow | Rôle |
| --- | --- |
| `agentic_dev_loop/internals/flow.py` | **le design** du round : la séquence, nœud par nœud |
| `agentic_dev_loop/internals/gates.py` | ce qu'un **nœud** exige avant de payer, et doit avoir obtenu après |
| `agentic_dev_loop/internals/board.py` | le côté lecture du tableau d'issues : le milestone, ses tasks |
| `agentic_dev_loop/internals/loop.py` | la boucle sur les rounds |
| `agentic_dev_loop/internals/state.py` | `RoundState` : ce que le moteur persiste, l'arrêt compris |
| `pr_review/internals/review.py` | l'orchestration de la revue |
| `pr_review/internals/passes.py` | les deux passes payantes |
| `pr_review/internals/publish.py` | le commentaire de synthèse, écrit puis posté |
| `pr_review/internals/skip_rules.py` | les quatre règles qui décident qu'une PR n'a pas à être revue |
| `legacy/migrate.py` | la bascule du markdown vers les issues, une fois. **N'est pas un workflow** : elle meurt entière, et le scan de forme l'exempte explicitement |

On relit `internals/flow.py` pour comprendre le pipeline,
`execution/stage_runner.py` pour comprendre une panne. C'est pour ça qu'ils
sont séparés.

`board.py` est lu par quatre appelants — le round, la boucle, le préflight et
`--status` — et n'importe jamais le moteur : c'est ce qui laisse `--status`
répondre en quelques dizaines de millisecondes, et le préflight échouer avant
qu'un flow soit construit. Même discipline pour `workflow.py` : son import du
round est **tardif**, dans le corps d'`execute()`.

### Les arrêts sont des valeurs, pas des exceptions

`domain/outcomes/result.py` porte `Result[T]` : une valeur, ou la raison de
son absence. Une porte de préflight, une lecture d'API qui n'aboutit pas, un
stage qui répond `AGENT_LOOP_STOP` — chacun **rend** un échec que son
appelant propage (`recast()`, `map()`, `but()`). Le chemin d'arrêt est donc
visible dans les signatures au lieu de traverser dix cadres de pile.

Ce que le statut porte n'a pas changé : les mêmes codes de sortie, les mêmes
préfixes, les mêmes niveaux de journal qu'avec les exceptions d'avant. Un
ordonnanceur extérieur lit ces codes et ils sont documentés dans `--help`.

**Une seule exception subsiste dans tout le paquet** : `ConfigError`, quand
une variable d'environnement est illisible. Une config qui ne se construit
pas n'a pas d'objet à qui rendre un `Result` — c'est `RunConfig()` lui-même
qui échoue, avant qu'un journal existe.

**Le prix à payer, et il est réel** : un nœud de flow qui rend un échec
**n'arrête pas** le graphe — le moteur déclenche le suivant. Chaque nœud
s'ouvre donc sur `if self.state.stopped: return`, et le routeur a une sortie
« stop » qu'aucun nœud n'écoute. Sans ces gardes, un `/code` qui s'arrête
laisserait partir `/create-test` : une session payante de plus, sur une task
qu'on vient de renoncer à livrer. Deux tests l'asserent ; les retirer les
fait échouer.

### `runtime/` et `launcher/`

`runtime/` n'importe **rien** du paquet — c'est une feuille au même titre que
`domain/`, et le test de couches l'assère. `RunConfig` y a vécu un temps : ses
méthodes parcourent la table du pipeline, donc c'était une politique déguisée
en réglage. Cette table est désormais un champ de `RunConfig` plutôt qu'un
import : un test fait tourner un round sur la sienne sans monkeypatch, et un
second workflow aura la sienne.

La racine du dépôt se **reçoit**. `Workspace` la porte et en dérive les
chemins ; `RunConfig`, `ReviewConfig` et `Ctx` la transportent ; les points
d'entrée la résolvent une fois, et les chemins rapides dans leur branche.
`paths.py` ne publie plus que `repo_root()`, et aucun module hors
`runtime/filesystem/` ne nomme `paths` — le test de couches l'assère.

| Module | Rôle |
| --- | --- |
| `runtime/filesystem/paths.py` | la racine du dépôt, résolue à la première lecture |
| `runtime/filesystem/workspace.py` | une racine, et les chemins que la boucle en dérive |
| `runtime/monitoring/logbook.py` | le journal : niveaux, date, contexte — **le seul système de log** |
| `runtime/monitoring/metrics.py` | durées, tokens, ratio de cache, cumul par round et par run |
| `launcher/main.py` | **le routeur** : il lit argv, valide, et dispatche |
| `launcher/routes.py` | la table des routes : nom, protocole, module cible, règles |
| `launcher/validation.py` | les règles inter-arguments, par route — une fonction pure |
| `launcher/cli/agentic_dev_loop.py` | `agent-loop` : les flags, les chemins rapides, les codes de sortie |
| `launcher/cli/pr_review.py` | `pr-review` : les flags, l'environnement, le gestionnaire de crash |
| `launcher/cli/reports.py` | ce que `--costs` et `--status` impriment |
| `launcher/hooks/*.py` | les quatre hooks, bibliothèque standard seule |

#### Un routeur, deux protocoles

`scripts/agent-loop`, `scripts/pr-review` et les quatre entrées de
`scripts/hooks/` passent toutes par `pipeline.launcher.main`, avec un nom de
route. `routes.py` est la seule liste de ces routes ; `migrate` n'en est pas
une, c'est un positionnel de la boucle. Quand `argv[0]` ne nomme aucune
route, c'est `loop` — `python -m pipeline.launcher --rounds 1` reste la
boucle.

Les deux familles n'ont pas le même protocole, et le routeur ne les confond
pas :

| | protocole `cli` | protocole `hook` |
| --- | --- | --- |
| entrée | `argv`, via argparse | JSON sur stdin |
| sortie | du texte sur stdout | du JSON sur stdout, ou rien |
| code de sortie | 0/1/2/3/4/130 | **2 bloque l'appel d'outil**, 0 le laisse passer |
| validation | oui | aucune : un hook ne prend pas d'argument |

`validation.py` porte la mécanique des règles, `routes.py` dit lesquelles
s'appliquent où. La fonction est pure — une `Route` et la **config résolue**
entrent, deux listes de chaînes sortent — et elle ne reprend pas à argparse
ce qu'il fait déjà (types, `choices`, `--help`) : elle ne porte que
l'inter-argument et le par-route.

Elle porte sur la config et non sur la ligne de commande, donc une valeur
venue de l'environnement est refusée comme un flag : `STAGES=cod` et
`--stages cod` donnent le même message, qui nomme les deux sources. Les
chemins rapides (`--costs`, `--status`, `migrate`) ne construisent pas de
config — ils ne lisent aucune des valeurs validées — et `config_to_check`
rend `None` pour eux.

Refus, code 1, sur stderr :

| Règle | Ce qui se passait sans elle |
| --- | --- |
| `--stages`/`STAGES` nomme une entrée absente de la table | `RunConfig.enabled` rendait `False` en silence, le round tournait à vide |
| `--rounds`/`MAX_ROUNDS` ≤ 0 | `range(1, 1)` est vide : le run ne faisait rien, sans le dire |
| `--effort`/`EFFORT` hors de `domain.stages.stage_spec.EFFORTS` | `StageSpec.__post_init__` explosait au milieu du round, après le préflight |
| `--verbose` et `--quiet` ensemble | `verbose` gagnait en silence |
| `--level`/`PR_REVIEW_LEVEL` hors de `low\|medium\|high\|max`, ou un `PR_REVIEW_*_EFFORT` inconnu (revue) | la passe partait avec un niveau que `/code-review` ne connaît pas |
| `--heartbeat` négatif | une minuterie négative |

Avertissements, le run continue :

| Règle | Pourquoi pas un refus |
| --- | --- |
| `--stages` ne contient pas `code` | usage légitime (`--stages business-analyst` est suggéré par `preconditions.py`), mais aucun stage ne livre la task : le round finira sur « nothing marks it delivered » |
| un flag sans effet pour `migrate` | il était ignoré en silence |

### La règle qui gouverne les imports

Trois règles, et chacune a coûté quelque chose.

`crewai` coûte ~1,3 s d'import à chaud et tire `chromadb`, `openai` et
`opentelemetry` — 2331 modules. Il n'existe donc que dans
`adapters/engine/crewai_engine.py`, chargé sur le seul chemin d'un run réel.

- `--status` et `--costs` répondent en ~0,08 s, sans crewai ni SDK. Deux
  tests le vérifient : `test_the_fast_paths_never_import_crewai_or_the_sdk`
  exécute vraiment la commande, `test_layering.py` interdit l'import.
- Les **hooks** tournent sous le python du système, hors du venv, à chaque
  appel d'outil. Bibliothèque standard uniquement, pour eux comme pour le
  routeur qui y mène — `launcher/__init__.py`, `launcher/main.py` et
  `launcher/routes.py` : `main.py` importe sa cible tardivement, dans la
  branche du switch, et un test l'assère **au niveau module**. Un
  `from pipeline.x import y` remonté en tête de `main.py` casserait les
  quatre hooks du dépôt d'un coup.
- Le **SDK** n'existe que dans `adapters/agent/claude_sdk.py`. Ailleurs on
  parle à `AgentRunner` et on lit un `AgentResult` — aucun nom de champ
  d'Anthropic ne circule dans `workflows/`. C'est ce qui rendra une seconde
  implémentation possible sans toucher au round ni à la revue.
- `runtime/monitoring/logbook.py` et `adapters/agent/progress.py` sont eux
  aussi en
  bibliothèque standard : le premier est sur le chemin rapide, et le second
  classe les messages du SDK **par nom de classe** plutôt qu'en l'important —
  ce qui le garde testable sans le SDK et le laisse survivre à un type de
  message ajouté.

### La lecture du magasin de reprise, et pourquoi elle est là où elle est

crewai **écrit** `flow_states` via son `@persist`, mais c'est
`adapters/store/resume.py` qui le **relit**, en sqlite3 standard. Le schéma
est donc connu des deux côtés, et c'est assumé : `--status` doit répondre
sans payer l'import du moteur. C'est le seul couplage de ce genre dans le
paquet, et il est nommé dans la docstring du module.

### Pourquoi le stage `code` ouvre sur `/tech-analyst`

Le plan du tech-analyst n'est écrit dans aucun fichier — c'est du contexte.
Un process séparé le jetterait à la sortie. Les deux skills partagent donc une
session : `StageSpec.lead` porte la commande d'ouverture, et le stage reste
facturé, loggé et repris sous le nom `code`.

## Ce que le journal dit

Une boucle non surveillée dépense de l'argent pendant des dizaines de minutes
sans que personne regarde. Le journal existe pour répondre après coup à trois
questions qu'on ne peut pas reconstituer si elles n'ont pas été écrites : où
est passé le temps, où est passé l'argent, et est-ce que le cache travaille.

```
2026-09-10 09:00:01  INFO   [20260910-090000]  run 20260910-090000 — branch main_agent @ 4637718, 1 round(s)
2026-09-10 09:00:01  INFO   [20260910-090000]  pipeline: business-analyst(opus/high) -> code(opus/high) -> ...
2026-09-10 09:00:02  INFO   [20260910-090000 r1]  milestone #11: Initial architecture setup
2026-09-10 09:00:02  INFO   [20260910-090000 r1]  task #14: Schema, seed & first DB-backed page [auto]
2026-09-10 09:00:02  INFO   [20260910-090000 r1 business-analyst]  /business-analyst — opus, effort high ...
2026-09-10 09:01:02  INFO   [20260910-090000 r1 business-analyst]  still running — 1m00s, 6 turn(s), 14 tool call(s), last: Grep
2026-09-10 09:02:02  INFO   [20260910-090000 r1 business-analyst]  still running — 2m00s, 11 turn(s), 31 tool call(s), last: Read
...
2026-09-10 09:08:34  INFO   [20260910-090000 r1 business-analyst]  tools: Read×62 Bash×39 Edit×24 Grep×18 Write×9 Task×3 — 155 call(s), 2 error(s), 3 subagent(s)
2026-09-10 09:08:34  INFO   [20260910-090000 r1 business-analyst]  /business-analyst done — $1.8546 · 8m32s · 41 turns · 163k in (91% cache) · 14k out
2026-09-10 09:08:34  INFO   [20260910-090000 r1]  running total — $1.8546 over 1 stage(s), 8m32s (wall 8m47s)
2026-09-10 09:08:34  INFO   [20260910-090000 r1 code]  /tech-analyst -> /code — opus, effort high ...
2026-09-10 09:15:47  INFO   [20260910-090000 r1 code]  /code done — $0.9814 · 7m13s · 34 turns · 132k in (89% cache) · 12k out
...
2026-09-10 09:19:58  INFO   [20260910-090000 r1]  round 1 — $3.6357 · 19m57s (wall 21m14s) · 3 stage(s) · 383k in (89% cache) · 33k out · priciest: /business-analyst $1.8546
```

Chaque ligne porte **la date**, **un niveau** et **un contexte**. La date parce
qu'un run qui passe minuit, ou relu une semaine plus tard, est ambigu sans
elle. Le niveau parce qu'un avertissement ne doit pas ressembler à une étape
ordinaire. Le contexte — run, round, stage — parce qu'une `pr-review`
détachée écrit dans le même terminal, sous `[pr-review#12]` : sans ça une
ligne n'est attribuable à rien.

Le **battement** (`still running — …`) est sur une minuterie, pas sur
l'arrivée des messages : un stage bloqué dans un seul appel d'outil de six
minutes doit quand même dire qu'il est vivant. C'est le trou que ce journal
avait — `/business-analyst` a déjà tourné 8m32s en écrivant exactement deux
lignes, et pendant ces huit minutes la boucle était indiscernable d'un
processus pendu. `--heartbeat 0` le coupe, `HEARTBEAT_SECONDS` en change la
période.

Le **recensement d'outils** clôt chaque stage, et il est écrit *avant* qu'un
échec ne soit levé : un stage mort après quarante appels d'outil est
justement celui dont on veut la trace. Le détail complet — un appel d'outil
par ligne, avec son argument identifiant et ses erreurs — va dans
`<step>-<skill>.trace.log`, à côté du `.log` et du `.json` du stage. Le
terminal n'en reçoit rien par défaut : un mur d'appels d'outil détruirait la
lisibilité que ce journal existe pour tenir. `--verbose` le remonte dans le
terminal, `--quiet` ne laisse que les avertissements et les erreurs — le
fichier `run.log`, lui, garde toujours tout.

Un état de reprise **illisible** arrête le round au lieu de se lire comme
« aucun stage n'a encore tourné » : c'est la seule lecture dégradée du paquet
qui coûte de l'argent, puisqu'elle ferait repayer un `/code` déjà mergé. Le
message nomme le fichier et les deux sorties (le réparer, ou `--restart`).

Le **cumul** après chaque stage sert à voir la facture monter en direct ; les
résumés de round et de run sont écrits même quand le round halte — c'est
justement celui-là dont on veut le chiffre. Ils portent deux horloges, et ce
ne sont pas la même mesure : `19m57s` est la somme de ce que les sessions
elles-mêmes ont rapporté, `wall 21m14s` le temps réel. L'écart, c'est tout ce
qui n'est pas une session — kickoff du flow, écritures de persistance, appels
git, préflight — et le résumé qui n'affichait que le premier laissait cet
écart inexpliqué.

Le **ratio de cache** est la métrique à surveiller : une lecture de cache coûte
une fraction du prix plein, donc un ratio qui s'effondre est la première chose
à regarder quand la facture monte sans que le travail change. `--costs` en rend
le détail par stage, sous la table historique.

Le registre porte aussi le **run**, la **task** et, depuis peu, l'**issue** de
chaque stage. `--costs-by task|run|day|stage` le relit dans ces axes-là, et
`--costs-task`, `--costs-run`, `--costs-since` le filtrent — « ce que la task 4
m'a coûté » ne demande plus un awk. L'argent brûlé par un stage en échec y est
compté à part : il n'a rien acheté.

```
scripts/agent-loop --costs-by task
scripts/agent-loop --costs-task "Schema"
scripts/agent-loop --costs-by day --costs-since 2026-09-01
```

Les panneaux ASCII de CrewAI (un par méthode de flow) sont coupés — ils
répétaient nos lignes et noyaient le journal. `PIPELINE_CREWAI_PANELS=1` les
remet pour déboguer le graphe lui-même.

### Comment la boucle s'arrête

Un run s'arrête soit parce qu'il a dépensé son budget de rounds, soit parce
qu'il n'y a plus rien à ouvrir. Le second cas est celui qu'on oublie : quand
le milestone n'a plus aucune issue `pipeline:agent` ouverte et qu'aucune
entrée `planner` n'est configurée, rejouer le round ne peut rien produire. Le
round le dit — il rend « rien de plus à faire » — et la boucle s'arrête là
plutôt que de payer `MAX_ROUNDS` démarrages de flow pour réimprimer deux fois
la même ligne. Avec un planner configuré qui ouvre bien une task, elle
enchaîne normalement.

Il ne faut pas confondre ce cas avec l'autre : **des tasks ouvertes mais
aucune prête** n'est pas un rollover. Le milestone n'est pas fini, il attend
une case `pipeline:ready` — le run s'arrête en nommant chaque task et ce qui
la retient, et n'appelle surtout pas `/planner`.

Un arrêt propre et un plantage se ressemblaient : les deux imprimaient
`STOP — …` et sortaient 1, alors que le code lui-même insiste qu'un `Halt`
est un résultat correct. Chacun a maintenant son mot, son niveau et son code
de sortie — ce que lit un ordonnanceur qui relance la boucle :

| Code | Mot | Ce que c'est |
| --- | --- | --- |
| 0 | — | le run est allé au bout |
| 1 | `STOP` | arrêt volontaire : il faut un humain. Un résultat correct |
| 2 | `FAILED` | un stage n'a pas rendu de résultat exploitable |
| 3 | `QUOTA` | fenêtre d'abonnement épuisée : relancer plus tard, à l'identique |
| 4 | `CRASH` | erreur inattendue — **la trace est dans `run.log`** |
| 130 | — | interrompu |

La revue de PR répond sur la même échelle : `2` quand elle n'a pas pu
produire ou poster ses notes, `3` quand la fenêtre d'abonnement est épuisée,
`4` sur une erreur inattendue — elle tourne détachée d'un hook, donc une trace
qui ne va pas dans son log ne va nulle part.

Le 4 est celui qui manquait. Le `main` de la boucle n'attrapait que `Halt` et
`KeyboardInterrupt` : une `ValidationError` pydantic, un interne crewai, une
erreur sqlite ou une `OSError` s'échappaient en trace sur stderr et
n'atteignaient jamais `run.log`. Pour une boucle non surveillée c'était le pire
cas — on revient, le terminal est fermé, et le journal s'arrête au milieu d'un
round sans donner de raison.

## L'équivalence avec le shell

`tests/oracle/` contient des artefacts produits par les scripts shell **avant**
leur suppression : les prompts d'un dry-run réel, la table des coûts, le prompt
de revue expansé par bash, et les 17 décisions du garde-fou `push`. Les tests
comparent la sortie Python à ces fichiers.

Trois divergences sont voulues et assumées :

1. le préambule cite `pipeline/launcher/cli/agentic_dev_loop.py` comme
   injecteur, plus `scripts/agent-loop.sh` ;
2. en `--dry-run`, les post-conditions d'un stage ne sont plus vérifiées — rien
   n'a tourné, donc rien ne peut les tenir. L'ancien dry-run haltait toujours
   sur l'une d'elles ;
3. les consignes du stage `code` nomment une issue et la ligne `Closes #N`
   qui la ferme — elles ne pouvaient pas ne pas bouger, puisqu'elles
   nommaient `docs/current/SPEC.md`. Ce qui les entoure ne bouge pas, et
   `prompt-code.txt` en fait toujours l'assertion, préambule compris. Les
   oracles des parseurs de markdown (`tasks.tsv`, `human-actions.txt`) sont
   partis avec les parseurs.
