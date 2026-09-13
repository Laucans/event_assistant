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

Le contrat vit dans `core/execution/contract/workflow.py`. Il tient en quatre
attributs et deux méthodes :

```python
class Workflow(Protocol):
    config: WorkflowConfig
    log: Logbook
    preconditions: Preconditions
    postconditions: Postconditions

    async def run(self) -> WorkflowOutcome: ...      # délègue à sequence()
    async def execute(self) -> WorkflowOutcome: ...  # ton travail
```

C'est un `Protocol`, donc **tu n'hérites de rien** : tu exposes ces six
membres et tu es un workflow. `isinstance(x, contract.Workflow)` répond sur la
forme.

Ce qui impose l'ordre, c'est `sequence()` — quinze lignes que personne ne
réécrit :

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

Deux garanties en découlent, et elles sont testées
(`tests/workflows/common/test_contract.py`) :

- **une précondition qui échoue n'atteint jamais `execute()`** — c'est toute
  la raison d'être du préflight : ne rien dépenser pour rien ;
- **les postconditions ne tournent pas sur un travail qui a échoué** — elles
  disent ce qu'un travail *fait* doit avoir obtenu ; les lancer sur un
  workflow arrêté en chemin ne produirait qu'un second message, moins juste
  que le premier.

---

## 2. La checklist

```
workflows/<ton_workflow>/
├── __init__.py          ce que le workflow fait, en trois lignes
├── workflow.py          la classe : config, log, les 2 gardes, run(), execute()
├── settings.py          ce qui varie d'un run à l'autre
├── preconditions.py     ce qui doit tenir avant de payer
├── postconditions.py    ce qu'il doit avoir obtenu (vide est valable)
├── stages/              LA DÉFINITION : quels agents, quel modèle, quel texte
│   └── __init__.py
└── internals/           TOUT le reste
    └── __init__.py
```

**Les quatre modules de la racine sont obligatoires et suffisants.** Un
cinquième fichier `.py` à la racine fait échouer
`test_every_workflow_keeps_its_own_code_in_internals`. Un manquant fait
échouer `test_every_workflow_carries_the_same_modules_at_its_root`. C'est
volontairement rigide : c'est ce qui fait qu'on lit deux workflows de la même
façon, et qu'un troisième se lit sans mode d'emploi.

**Et deux sous-dossiers, pas trois.** `stages/` et `internals/`, nommés dans
`WORKFLOW_DIRS` ; un troisième fait échouer
`test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones`. La règle
existe parce que le test de la racine fait un `glob("*.py")` qui ne descend
dans aucun dossier : sans elle, créer un sous-paquet ferait passer n'importe
quoi.

**`stages/` est ta définition, et c'est là que va tout ce qui décrit tes
agents** — la table `PIPELINE` (une entrée `StageSpec` par stage, avec son
modèle, son effort et sa prose), `INJECTOR`, et un module par texte long.
Rien de ça ne va dans `domain/` : le domaine porte le *vocabulaire* (ce
qu'est un `StageSpec`, une `Issue`, un `Result`), jamais l'instance. Deux
tests le tiennent — `test_no_module_of_the_domain_names_a_workflow` et
`test_only_its_own_workflow_names_the_pipeline_labels`.

Si ton workflow n'a pas de table — les deux passes de `pr_review` tirent leur
modèle de sa config, parce qu'ils sont réglables à l'appel — `stages/` ne
porte que la prose. C'est un cas normal, dis-le dans son docstring.

Les noms de **classes** ne sont pas contraints par un test, seulement les noms
de modules. La convention en place est `<Nom>Preconditions` /
`<Nom>Postconditions` (`LoopPreconditions`, `ReviewPreconditions`) — suis-la.

---

## 3. Le squelette

`settings.py` — hérite de `WorkflowConfig`, qui porte déjà `workspace`,
`dry_run`, `verbose`, `quiet`, `heartbeat_s` :

```python
from pipeline.core.execution.contract.settings import WorkflowConfig

# `kw_only` seulement si tu as des champs OBLIGATOIRES : un champ sans défaut
# ne peut pas suivre les champs défautés du parent. Sans ça, il faudrait leur
# inventer une valeur vide — et ton workflow se construirait sans sa cible.
@dataclass(kw_only=True)
class MaConfig(WorkflowConfig):
    cible: str
    niveau: str = "medium"
```

`preconditions.py` — compose ta liste à partir des portes communes :

```python
from pipeline.workflows.common import checks
from pipeline.workflows.common.checks import Check

CHECKS: tuple[Check, ...] = (
    *checks.TOOLING,                     # claude, gh, gh auth
    Check("ma-porte", ma_porte),         # ce que toi seul exiges
    # *checks.BRANCH,                    # si tu travailles sur main_agent
    # Check("clean-tree", checks.working_tree_is_clean),
)

@dataclass
class MesPreconditions:
    cfg: MaConfig
    log: Logbook

    def verify(self) -> Result[None]:
        return checks.verify_all(CHECKS, self.cfg, self.log)
```

Une porte est une fonction `(cfg, log) -> Result[None]`. Elle **ne lève
jamais** : elle rend `Result.halt("la phrase sur laquelle un humain agit")`
ou `Result.of(None)`. `verify_all` s'arrête à la première qui échoue — les
portes se supposent les unes les autres, et demander les étiquettes à `gh`
n'a pas de sens tant qu'on ne sait pas s'il est authentifié.

`postconditions.py` — **vide est un résultat valable**, mais dis pourquoi :

```python
@dataclass
class MesPostconditions:
    cfg: MaConfig
    log: Logbook

    def verify(self, outcome: WorkflowOutcome) -> Result[None]:
        return Result.of(None)
```

Les deux workflows existants ont des postconditions vides, et chaque fichier
explique laquelle : le round garantit **par round** (dans `internals/gates`),
la revue garantit **en chemin**. Un docstring qui dit « rien à vérifier ici,
et voilà où ça se vérifie vraiment » vaut infiniment mieux qu'un `pass` muet —
le lecteur suivant se demanderait si c'est un oubli.

`workflow.py` — court, et c'est le but :

```python
@dataclass
class MonWorkflow:
    config: MaConfig
    log: Logbook
    preconditions: MesPreconditions = field(init=False)
    postconditions: MesPostconditions = field(init=False)

    def __post_init__(self) -> None:
        self.preconditions = MesPreconditions(self.config, self.log)
        self.postconditions = MesPostconditions(self.config, self.log)

    async def run(self) -> WorkflowOutcome:
        return await contract.sequence(self)

    async def execute(self) -> WorkflowOutcome:
        # Import tardif si tu charges un moteur : voir §4.
        from pipeline.workflows.mon_workflow.internals import moteur

        return await moteur.run(self.config, self.log)
```

Tout le reste — la vraie logique — va dans `internals/`, découpé comme tu
veux. C'est le seul endroit où ton workflow n'a pas à ressembler aux autres.

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

le SDK d'agent est lourd à importer. Si ton workflow charge un
moteur, **importe-le tardivement, dans le corps d'`execute()`** — jamais en
tête de `workflow.py`. C'est ce qui laisse `--status` et `--costs` répondre en
80 ms, et le préflight échouer avant qu'un flow soit construit.

Même discipline pour l'état persisté : garde-le dans un module qui n'importe
pas le moteur (`internals/state.py` chez la boucle). Mesuré : `import state` =
0,12 s, `import flow` = 1,43 s.

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
outcome = asyncio.run(MonWorkflow(cfg, log).run())
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
| `test_every_workflow_carries_the_same_modules_at_its_root` | il manque un des quatre modules |
| `test_every_workflow_keeps_its_own_code_in_internals` | un `.py` de trop à la racine — il va dans `internals/` |
| `test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones` | un sous-dossier hors de `stages/` et `internals/` |
| `test_no_module_of_the_domain_names_a_workflow` | une définition de workflow rangée dans `domain/` |
| `test_only_its_own_workflow_names_the_pipeline_labels` | une étiquette `pipeline:` sortie du workflow qui la définit |
| `test_a_workflow_never_imports_another_workflow` | remonte ce que tu partages dans `common/` |
| `test_the_common_package_never_imports_a_workflow` | le contrat s'est mis à connaître un implémenteur |
| `test_every_layer_only_imports_the_layers_below_it` | un import qui remonte une couche |
| `test_a_confined_library_appears_in_exactly_one_module` | le SDK importé hors de son adaptateur |
| `test_every_environment_variable_the_code_reads_is_in_a_help_epilog` | une variable lue et non documentée |

Le scan des workflows exempte `common/` et `legacy/` (`NOT_A_WORKFLOW` dans
`tests/test_layering.py`). Si tu ajoutes sous `workflows/` un dossier qui
n'est **pas** un workflow, nomme-le là — mais demande-toi d'abord s'il n'a pas
sa place ailleurs.

Côté tests, reflète l'arborescence : `tests/workflows/<ton_workflow>/`. La
fixture `hub` de `conftest.py` te donne GitHub sur papier ; pour les portes
qui regardent le PATH, remplace `binaries.shutil` (la fonction système est
résolue **à l'appel**, justement pour que ça marche).

---

## 8. Quoi lire avant d'écrire

Dans cet ordre, une heure :

1. `core/execution/contract/workflow.py` — le contrat, et les quinze lignes de
   `sequence()`. C'est tout ce que tu dois respecter.
2. `core/domain/outcomes/result.py` — comment un arrêt voyage.
3. `pr_review/` en entier — c'est le plus petit des deux, et il montre la
   forme complète sans moteur de graphe. **Copie celui-là.**
4. `core/execution/steps.py` puis `agentic_dev_loop/stages/__init__.py` —
   comment une séquence se déclare, et à quoi ressemble une vraie.
5. `common/checks.py` — les portes que tu ne réécriras pas.

`pipeline/TOUR.md` §2 et §3 donnent les couches et le sens des dépendances ;
`pipeline/INTERNALS.md` donne le détail par module.
