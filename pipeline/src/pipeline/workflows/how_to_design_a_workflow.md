# Ajouter un workflow

Ce dossier porte un sous-paquet par workflow, et **tous ont exactement la
même forme**. Ce fichier dit laquelle, pourquoi, et ce qui casse si tu t'en
écartes. Il s'adresse autant à un humain qu'à un agent : les règles
ci-dessous ne sont pas des conseils, ce sont des tests.

Un workflow, ici, c'est **une chose qu'on lance et qui dépense de l'argent** :
la boucle de développement agentique (`agentic_dev_loop/`), la revue
consultative d'une PR (`pr_review/`). Si ton ajout ne dépense rien et ne se
lance pas tout seul, ce n'est probablement pas un workflow — c'est un
adaptateur, une politique de domaine, ou un rouage de l'un des deux.

---

## 1. Ce que tu signes

Un workflow est une **declaration**. Tu remplis un `Blueprint`, et
`core/design/build.py` en monte l'objet que le lanceur appelle :

```python
WORKFLOW = Blueprint(
    name="mon-workflow",          # le premier argument de la commande
    config=MaConfig,              # ce qui varie d'un run a l'autre
    gates=(*checks.TOOLING,),     # ce qui doit tenir avant de payer
    shape=once(...),              # comment le milieu tourne
    artifacts=lambda cfg: ...,    # ou tombent ses fichiers
    obtained=None,                # ce qu'il doit avoir obtenu — None est valable
)
```

Ce que ca monte satisfait `core/execution/contract/workflow.py`, qui n'a pas
bouge : quatre attributs, deux methodes, un `Protocol`. **Tu n'herites de
rien, et tu n'ecris plus les emballages** — la classe du workflow, les deux
classes de gardes et leur `__post_init__` etaient identiques d'un workflow a
l'autre, et sont ecrites une fois dans `design/`.

Ce qui impose l'ordre reste `sequence()` — quinze lignes que personne ne
reecrit :

```python
before = workflow.preconditions.verify()
if before.failed:
    return WorkflowOutcome.of_result(before)

outcome = await workflow.execute()
if outcome.failed:
    return outcome

after = workflow.postconditions.verify(outcome)
...
```

Deux garanties en decoulent, et elles sont testees
(`tests/core/execution/test_contract.py`) :

- **une precondition qui echoue n'atteint jamais `execute()`** — c'est toute
  la raison d'etre du preflight : ne rien depenser pour rien ;
- **les postconditions ne tournent pas sur un travail qui a echoue** — elles
  disent ce qu'un travail *fait* doit avoir obtenu ; les lancer sur un
  workflow arrete en chemin ne produirait qu'un second message, moins juste
  que le premier.

**L'echappatoire est gratuite.** `contract.Workflow` est un `Protocol` : un
workflow qui ne rentre dans aucune forme expose les six membres a la main, et
rien en aval ne fait la difference. C'est ce qui separe une facilite d'un
carcan — et la limite a surveiller : si `core/execution/shapes/` se met a
grossir pour faire rentrer un client, c'est qu'on refabrique un moteur.

---

## 2. La checklist

```
workflows/<ton_workflow>/
├── __init__.py          ce que le workflow fait, en trois lignes
├── workflow.py          LA DÉCLARATION : le Blueprint, et rien d'autre
├── settings.py          ce qui varie d'un run à l'autre + sa politique de session
├── preconditions.py     les portes qu'il exige, et l'annonce qui suit
├── stages/              LA DÉFINITION : quelles étapes, quel modèle, quel texte
│   └── __init__.py
└── internals/           TOUT le reste
    └── __init__.py
```

**Les trois modules de la racine sont obligatoires et suffisants.** Un
quatrieme fichier `.py` a la racine fait echouer
`test_every_workflow_keeps_its_own_code_in_internals`. Un manquant fait
echouer `test_every_workflow_carries_the_same_modules_at_its_root`. C'est
volontairement rigide : c'est ce qui fait qu'on lit deux workflows de la meme
facon, et qu'un troisieme se lit sans mode d'emploi.

Il n'y a plus de `postconditions.py`. Les deux workflows n'y avaient qu'une
classe vide et un paragraphe expliquant le vide ; ce qu'un workflow doit
avoir obtenu se dit dans le champ `obtained`, absent quand il n'y a rien.

**Et deux sous-dossiers, pas trois.** `stages/` et `internals/`, nommes dans
`WORKFLOW_DIRS` ; un troisieme fait echouer
`test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones`. La regle
existe parce que le test de la racine fait un `glob("*.py")` qui ne descend
dans aucun dossier : sans elle, creer un sous-paquet ferait passer n'importe
quoi.

**`stages/` est ta definition, et c'est la que va tout ce qui decrit tes
etapes** — la table, `INJECTOR`, et un module par texte long. Rien de ca ne va
dans `domain/` : le domaine porte le *vocabulaire* (ce qu'est un `StageSpec`,
une `Action`, une `Issue`, un `Result`), jamais l'instance. Deux tests le
tiennent — `test_no_module_of_the_domain_names_a_workflow` et
`test_only_its_own_workflow_names_the_pipeline_labels`.

Une table est **une fonction de la config**, pas une constante — `passes(cfg)`,
`lambda cfg: cfg.pipeline`. Celle du round est fixe, celle de la revue tire
ses modeles de `--level` et des `PR_REVIEW_*` : une fonction dit les deux.

---

## 3. Le squelette

`settings.py` — herite de `WorkflowConfig`, qui porte deja `workspace`,
`dry_run`, `verbose`, `quiet`, `heartbeat_s`, `run_id`, `permission_mode` et
`stages` :

```python
from pipeline.core.execution.contract.settings import WorkflowConfig

# `kw_only` seulement si tu as des champs OBLIGATOIRES : un champ sans défaut
# ne peut pas suivre les champs défautés du parent. Sans ça, il faudrait leur
# inventer une valeur vide — et ton workflow se construirait sans sa cible.
@dataclass(kw_only=True)
class MaConfig(WorkflowConfig):
    cible: str
    niveau: str = "medium"

    def prompt_for(self, stage, extra) -> str:
        """Sans défaut, à dessein : le préambule est ce qu'un workflow a de
        plus propre, et en inventer un vide ferait partir une session sans
        son texte."""
        return prompts.build(stage.command, ..., extra)
```

C'est aussi la que vit **la politique de session** que `core/execution` te
demande, et dont tu n'as le plus souvent rien a redefinir :

| methode | defaut | quand la redefinir |
| --- | --- | --- |
| `prompt_for` | *aucun* | toujours |
| `enabled` / `runs` / `resolve` | tout tourne, rien n'est surcharge | `--stages`, `--model`, `--effort` |
| `artifact_tag` | le numero de tour, zero-padde | la revue prefixe par sa PR |
| `record` | une ligne dans `costs.tsv` | tu tiens un registre a part |

`preconditions.py` — compose ta liste a partir des portes communes. Plus de
classe : c'est `CHECKS` que le blueprint recoit dans `gates=`.

```python
from pipeline.workflows.common import checks
from pipeline.workflows.common.checks import Check

CHECKS: tuple[Check, ...] = (
    *checks.TOOLING,                     # claude, gh, gh auth
    Check("ma-porte", ma_porte),         # ce que toi seul exiges
    # *checks.BRANCH,                    # si tu travailles sur main_agent
    # Check("clean-tree", checks.working_tree_is_clean),
)
```

Une porte est une fonction `(cfg, log) -> Result[None]`. Elle **ne leve
jamais** : elle rend `Result.halt("la phrase sur laquelle un humain agit")`
ou `Result.of(None)`. La liste s'arrete a la premiere qui echoue — les
portes se supposent les unes les autres, et demander les etiquettes a `gh`
n'a pas de sens tant qu'on ne sait pas s'il est authentifie.

Ce qu'une porte **est** vit dans `core/execution/contract/gate.py` ; ce que
*ce depot* exige vit ici. Le framework porte la forme, l'usage porte
l'instance.

`stages/` — la table, une entree par etape. Deux sortes, et la sequence ne
les distingue pas :

```python
def passes(cfg) -> tuple:
    return (
        StageSpec("inline", cfg.inline_model, cfg.inline_effort, skip=...),
        StageSpec("brief", cfg.brief_model, cfg.brief_effort),
        Action("publish", publish.post, skip=...),   # ne paie rien
    )
```

Une etape porte ses trois moments — `skip` (« c'est deja fait »), `before`
(« ce que j'exige pour partir »), `after` (« ce que je dois avoir obtenu ») —
et une passe lit ce que la precedente a rendu dans `ctx.results[<nom>]`.

`workflow.py` — la declaration, et rien d'autre :

```python
WORKFLOW = Blueprint(
    name="mon-workflow",
    config=MaConfig,
    gates=preconditions.CHECKS,
    artifacts=lambda cfg: cfg.workspace.llocal / "mon-workflow",
    shape=Once(plan=stages.etapes, state=MonEtat, extra=stages.prompt_of),
    obtained=None,
)
```

### Les deux formes

| | `Once` | `Repeat` |
| --- | --- | --- |
| pour | une cible, puis on s'arrete | un budget a consommer, sans personne devant |
| exemple | `pr_review` | `agentic_dev_loop` |
| tu donnes | `plan`, `state`, `extra` | `unit`, `budget` |
| en option | `precheck`, `guard`, `held`, `tolerate`, `summary` | `label`, `exhausted`, `summary` |

- **`precheck(cfg, log, state)`** — « y a-t-il seulement quelque chose a
  faire ? ». Rend la raison de n'en rien faire, ou la chaine vide. **Un run
  qui n'a rien a faire est un succes** : une PR en brouillon n'a rien a
  obtenir, et l'echouer ferait echouer exactement les cas que les regles de
  saut existent pour laisser passer. C'est aussi la que l'etat se remplit.
- **`guard(cfg, state)`** — au plus un a la fois. Deux hooks partis sur la
  meme PR la commenteraient deux fois.
- **`tolerate(step, failed)`** — l'echec de cette etape-la n'arrete pas la
  sequence. Rend la ligne a journaliser, ou None pour s'arreter comme
  d'habitude. Ce n'est pas un booleen a dessein : la passe ligne a ligne
  d'une revue peut ne rien rendre sans que les notes perdent leur valeur,
  alors qu'un quota epuise doit bien arreter la suite.

Tout le reste — la vraie logique — va dans `internals/`, decoupe comme tu
veux. C'est le seul endroit ou ton workflow n'a pas a ressembler aux autres.

---

## 4. Les décisions déjà prises

Elles ne se rouvrent pas au cas par cas. Chacune a un test derrière.

### Les arrêts sont des valeurs, pas des exceptions

`core/domain/outcomes/result.py` porte `Result[T]` : une valeur, ou la raison de
son absence. Rien dans ce paquet ne lève pour s'arrêter.

```python
Result.of(valeur)        # ça a abouti
Result.halt(raison)      # arrêt volontaire — exit 1, "STOP", niveau info
Result.unreadable(r)     # un magasin n'a pas répondu — exit 1, "STOP", info
Result.fail(raison)      # rien d'utilisable — exit 2, "FAILED", error
Result.quota(raison)     # fenêtre épuisée — exit 3, "QUOTA", warn
```

et pour propager sans réécrire :

```python
lu = gh.issue(12)
if lu.failed:
    return lu.recast()          # même échec, autre type de valeur
...
return gh.labels().map(lambda rows: [r["name"] for r in rows])   # ok → transforme
return lu.but("impossible de lire le tableau")                   # ajoute le contexte
```

**L'écart entre les quatre statuts est ce qui dit quoi faire ensuite** : un
ordonnanceur extérieur lit ces codes de sortie, et ils sont documentés dans
`--help`. Ne rends pas `fail` là où tu veux dire `quota` : « reviens plus
tard » et « c'est cassé » n'appellent pas la même réponse.

**La seule exception qui subsiste** est `ConfigError`, quand une variable
d'environnement est illisible : une config qui ne se construit pas n'a pas
d'objet à qui rendre un `Result`.

### Les appels externes vivent dans `adapters/`

Ton workflow **décide** ; il n'appelle jamais `subprocess`, `shutil.which`,
ni un binaire lui-même. Si `adapters/shell/` n'a pas la méthode qu'il te
faut, ajoute-la là-bas et lis-la depuis ta porte.

Et ne **construis** pas tes clients toi-même : `core/adapters/hub.py` est le
seul endroit du paquet qui le fait.

```python
from pipeline.core.adapters import hub

hub.gh(cfg.workspace)      # l'adaptateur gh
hub.repo(cfg.workspace)    # l'adaptateur git
```

C'est ce qui donne **une seule couture de test** : une ligne de
`tests/conftest.py` met GitHub sur papier pour tous les workflows à la fois.

### Un workflow n'importe jamais un autre workflow

Le commun passe par `workflows/common/`. `test_a_workflow_never_imports_another_workflow`
l'assère, et `test_the_common_package_never_imports_a_workflow` garde l'autre
sens — sinon les portes communes deviendraient celles du premier workflow,
avec les autres accrochés dessus.

Si tu as besoin de quelque chose que `agentic_dev_loop` possède, la réponse
est de le remonter — dans `workflows/common/` si c'est une **politique** (ce
qu'un run doit exiger), dans `core/` si c'est une **forme** ou un outil qui
ne décide rien. C'est la ligne qui a fait monter le contrat dans
`core/execution/contract/` et laissé les portes ici.

### Le chemin rapide ne paie pas le moteur

Le SDK d'agent est lourd à importer, et `workflow.py` est lu par tout le
monde : `--status` et `--costs` importent le module pour atteindre sa
déclaration. **Ce que la déclaration nomme est donc chargé pour imprimer deux
lignes.** Si ton unité de travail charge quoi que ce soit de lourd,
**importe-le dans le corps de la fonction**, jamais en tête :

```python
async def _round(cfg, turn, log, log_dir, tally):
    from pipeline.workflows.agentic_dev_loop.internals import loop

    return await loop.one_round(cfg, turn, log, log_dir, tally)
```

`test_declaring_a_workflow_does_not_load_the_engine` tient la règle côté
framework, et pour un type qui ne sert qu'à l'annotation, `if TYPE_CHECKING:`
suffit — le scan ne compte pas ce qui ne s'exécute pas.

Même discipline pour l'état persisté : garde-le dans un module qui n'importe
pas le moteur (`internals/state.py` chez la boucle).

---

## 5. Le brancher sur une commande

Un workflow que personne ne peut lancer n'existe pas. Quatre endroits, dans
cet ordre :

**a. `launcher/cli/<ton_workflow>.py`** — trois fonctions, c'est l'interface
qu'attend le routeur :

```python
def parse_args(argv) -> argparse.Namespace       # argparse, avec un epilog
def config_to_check(args) -> MaConfig | None     # la config que la validation examine
def main(argv) -> int                            # construit, lance, rend le code
```

`main` traduit le résultat en code de sortie, et c'est **le seul endroit qui
journalise la raison** :

```python
outcome = asyncio.run(build.workflow(WORKFLOW, cfg, log).run())
return outcome.report(log).exit_code
```

`report()` dit la fin au niveau que son statut mérite (un arrêt volontaire ne
se lit pas comme un avertissement) et se rend pour être chaîné. **Ne logge
pas ta raison à l'intérieur du workflow en plus** : elle sortirait deux fois.

**b. `launcher/routes.py`** — ajoute la `Route`. Le nom devient le premier
argument de la commande :

```python
Route("mon-workflow", "cli", "pipeline.launcher.cli.mon_workflow",
      rules=("verbose-xor-quiet", "heartbeat-positive")),
```

**c. `launcher/validation.py`** — les règles inter-arguments qu'argparse ne
sait pas dire. Réutilise celles qui existent (`RULES` les liste) ; une règle
nommée dans une route mais absente de la table, ou l'inverse, ne passe pas
inaperçue.

**d. `scripts/<mon-workflow>`** — le shim bash, copié sur `scripts/pr-review`.
Sa dernière ligne :

```bash
exec "$py" -m "pipeline.launcher" mon-workflow "$@"
```

**Et une chose qu'on oublie** : toute variable d'environnement que ton code
lit doit apparaître dans un épilogue `--help`.
`test_every_environment_variable_the_code_reads_is_in_a_help_epilog` scanne
tout le paquet et tombe sinon — pense à ajouter ton `parse_args` à la boucle
de ce test.

---

## 6. Les pièges qui coûtent de l'argent

Ceux-là ont déjà coûté quelque chose. Ils sont ici pour que ça n'arrive
qu'une fois.

**N'exprime pas ta séquence en graphe.** Celle du round l'a été, et ça a
coûté trois choses : un moteur à 1,6 s d'import que tout le reste du paquet
devait ensuite éviter ; un `if state.stopped: return` en tête de **chaque**
nœud, parce qu'un moteur déclenche le suivant quelle que soit la valeur de
retour du précédent ; et six membres de l'état qui n'existaient que pour
porter cet arrêt d'un nœud à l'autre.

Une séquence d'étapes se déclare — `core/execution/steps.py` la fait
tourner, et elle rend au premier échec :

```python
ROUND = (
    StageSpec("business-analyst", …, after=gates.spec_is_in_the_issue),
    StageSpec("code", …, before=gates.code_has_a_spec),
)
```

Un graphe ne se paie que si tu as de vraies branches — plusieurs, et qui se
rejoignent. Le round n'en avait qu'une (`rollover`), et c'est un `if`.

**Une lecture ratée ne se rend jamais en vide.** `[]` se lit « il n'y a plus
rien à faire », qui est exactement l'entrée qui déclenche un `/planner` — un
run opus, dépensé parce qu'un jeton avait expiré. C'est pour ça que
`Result.unreadable` existe séparément de `Result.halt`.

**Vérifie avant de payer, pas après.** Une porte coûte un appel local ; la
même erreur découverte au milieu d'un run coûte un stage déjà facturé. Si
quelque chose peut être su avant, mets-le dans `preconditions.py`.

**Les portes ne sont pas les conditions de tes étapes.** `preconditions.py`
porte celles du **workflow**, vérifiées une fois avant tout. Ce qu'une étape
interne exige avant de payer sa session vit avec elle, dans `internals/`
(chez la boucle : `internals/gates.py`). Mélanger les deux a déjà rendu un
nom de module menteur.

---
## 7. Ce que les tests te diront

`pipeline/.venv/bin/python -m pytest pipeline/tests`

| Le test qui tombe | Ce que tu as fait |
| --- | --- |
| `test_every_workflow_carries_the_same_modules_at_its_root` | il manque un des trois modules |
| `test_every_workflow_keeps_its_own_code_in_internals` | un `.py` de trop à la racine — il va dans `internals/` |
| `test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones` | un sous-dossier hors de `stages/` et `internals/` |
| `test_every_workflow_declares_a_blueprint` | `workflow.py` n'exporte pas de `WORKFLOW`, ou sa forme n'en est pas une |
| `test_every_workflow_has_a_config_in_the_table` | ajoute la config minimale du nouveau workflow à `CONFIGS` |
| `test_declaring_a_workflow_does_not_load_the_engine` | un import qui fait payer le moteur à `--status` — voir §4 |
| `test_no_module_of_the_domain_names_a_workflow` | une définition de workflow rangée dans `domain/` |
| `test_only_its_own_workflow_names_the_pipeline_labels` | une étiquette `pipeline:` sortie du workflow qui la définit |
| `test_a_workflow_never_imports_another_workflow` | remonte ce que tu partages dans `common/` |
| `test_the_common_package_never_imports_a_workflow` | le contrat s'est mis à connaître un implémenteur |
| `test_every_layer_only_imports_the_layers_below_it` | un import qui remonte une couche |
| `test_every_layer_of_core_is_named_by_the_allowed_table` | un dossier de `core/` sans règle d'import |
| `test_a_confined_library_appears_in_exactly_one_module` | le SDK importé hors de son adaptateur |
| `test_every_module_a_docstring_names_still_exists` | un docstring qui renvoie à un module disparu |
| `test_every_environment_variable_the_code_reads_is_in_a_help_epilog` | une variable lue et non documentée |

Le scan des workflows exempte `common/` et `legacy/` (`NOT_A_WORKFLOW` dans
`tests/test_layering.py`). Si tu ajoutes sous `workflows/` un dossier qui
n'est **pas** un workflow, nomme-le là — mais demande-toi d'abord s'il n'a pas
sa place ailleurs.

Côté tests, reflète l'arborescence : `tests/workflows/<ton_workflow>/`. La
fixture `hub` de `conftest.py` te donne GitHub sur papier ; pour les portes
qui regardent le PATH, remplace `binaries.shutil` (la fonction système est
résolue **à l'appel**, justement pour que ça marche). Pour scripter des
sessions payantes sans en payer une, remplace
`core.execution.session.default_runner` — c'est le seul endroit où une
session se construit.

---

## 8. Quoi lire avant d'écrire

Dans cet ordre, une heure :

1. `core/design/blueprint.py` — ce que tu remplis. Six champs.
2. `core/execution/contract/workflow.py` — le contrat que ça monte, et les
   quinze lignes de `sequence()`.
3. `core/domain/outcomes/result.py` — comment un arrêt voyage.
4. `pr_review/` en entier — c'est le plus petit des deux, et il montre la
   forme complète. **Copie celui-là.**
5. `core/execution/shapes/once.py` puis `core/execution/steps.py` — comment
   une séquence tourne, et où elle s'arrête.
6. `common/checks.py` — les portes que tu ne réécriras pas.

`pipeline/TOUR.md` §2 et §3 donnent les couches et le sens des dépendances ;
`pipeline/INTERNALS.md` donne le détail par module.
