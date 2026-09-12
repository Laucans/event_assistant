"""L'architecture, en assertions plutot qu'en convention.

Un README qui dit « seul ce module importe crewai » est vrai le jour ou il
est ecrit. Ces tests le gardent vrai : ils parcourent l'AST de chaque fichier
du paquet et verifient qui importe quoi.

Quatre regles paient leur place, et chacune a coute quelque chose :

- **crewai coute ~1,3 s d'import a chaud** et tire chromadb, openai et
  opentelemetry — 2331 modules. Un import qui remonterait sur le chemin
  rapide ferait repondre `--status` en 2,5 s au lieu de 0,08 s ;
- **les hooks tournent sous le python du systeme**, hors du venv, a chaque
  appel d'outil : un hook qui importerait le paquet rendrait la session
  inutilisable ;
- **le domaine ne parle a personne**, ce qui est ce qui le rend testable en
  lui passant des chaines — et **il ne nomme aucun workflow** : il porte le
  vocabulaire (ce qu'est un stage, une issue, un resultat), jamais la
  definition d'un workflow, qui vit sous `workflows/<nom>/` ;
- **rien sous `core/` ne connait `workflows/` ni `launcher/`.** C'est la
  frontiere framework/usage, et elle tient en une assertion la ou il fallait
  sinon la lire dans quatre lignes de la table `ALLOWED` ;
- **tout workflow a la meme forme.** Les memes modules a sa racine, les memes
  classes dedans, et son code propre dans `internals/`. Un README qui le dit
  est vrai le jour ou il est ecrit ; le test plus bas le garde vrai.

Les sens de dependance completent le tableau : une couche basse qui importe
une couche haute est le premier pas vers un cycle.
"""

import ast
import pathlib
import sys

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "pipeline"

# Le dossier du framework. Ses sous-paquets sont des couches a part entiere,
# d'ou les cles a deux segments plus bas : sans ca, `core` serait une seule
# couche et `domain` pourrait importer `execution` sans que rien ne bronche.
CORE = "core"

# Qui a le droit d'importer quoi. La cle est une couche — un dossier du
# sommet, ou un sous-dossier de `core/` —, la valeur les couches qu'elle peut
# importer.
ALLOWED: dict[str, set[str]] = {
    "core/domain": {"core/domain"},
    # `runtime` est une feuille, au meme titre que `domain` : chemins, journal
    # et mesures ne decident de rien et n'ont besoin de personne. `RunConfig`
    # y a vecu un temps et etait le seul a importer le domaine — ses methodes
    # parcourent PIPELINE, donc c'etait une politique deguisee en reglage. Elle
    # est dans `workflows/agentic_dev_loop/settings.py`.
    "core/runtime": {"core/runtime"},
    "core/adapters": {"core/adapters", "core/domain", "core/runtime"},
    # pas workflows : c'est ce que le `Protocol` StagePolicy existe pour eviter
    "core/execution": {"core/adapters", "core/domain", "core/runtime",
                       "core/execution"},
    "workflows": {"core/adapters", "core/domain", "core/execution",
                  "core/runtime", "workflows"},
    "launcher": {"core/adapters", "core/domain", "core/execution",
                 "core/runtime", "launcher", "workflows"},
}

# Ce qui doit rester chargeable par le python du systeme, hors du venv : les
# hooks, et le routeur par lequel ils passent.
STDLIB_ONLY = ("launcher/__init__.py", "launcher/main.py", "launcher/routes.py")
STDLIB_ONLY_DIR = "launcher/hooks/"

# Les bibliotheques qui n'ont le droit d'apparaitre qu'a un seul endroit.
CONFINED = {
    "claude_agent_sdk": "core/adapters/agent/claude_sdk.py",
    "crewai": "core/adapters/engine/crewai_engine.py",
    "crewai_core": "core/adapters/engine/crewai_engine.py",
}


def modules() -> list[pathlib.Path]:
    return sorted(p for p in SRC.rglob("*.py"))


def imports(path: pathlib.Path) -> list[str]:
    """Chaque module importe par ce fichier, au niveau du module ou dans un corps.

    Les imports tardifs comptent autant que les autres : c'est justement par
    un import tardif qu'on ferait rentrer crewai la ou il n'a rien a faire.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
    return found


def layer(path: pathlib.Path) -> str:
    """La couche d'un fichier : `core/domain`, `workflows`, `launcher`…

    Les sous-paquets de `core/` sont des couches ; `core/__init__.py` n'en
    est pas une, et rend `core` — une cle absente d'`ALLOWED`, donc ignoree,
    comme l'`__init__.py` de la racine.
    """
    parts = path.relative_to(SRC).parts
    if parts[0] == CORE and len(parts) > 1 and not parts[1].endswith(".py"):
        return f"{CORE}/{parts[1]}"
    return parts[0].removesuffix(".py")


def target(module: str) -> str:
    """La couche que nomme un import `pipeline.…`, dans les memes termes."""
    parts = module.split(".")
    if len(parts) > 2 and parts[1] == CORE:
        return f"{CORE}/{parts[2]}"
    return parts[1]


@pytest.mark.parametrize("library, home", sorted(CONFINED.items()))
def test_a_confined_library_appears_in_exactly_one_module(library, home):
    """Ou vit crewai, ou vit le SDK — nulle part ailleurs, imports tardifs compris."""
    importers = sorted(
        str(p.relative_to(SRC)) for p in modules()
        if any(m == library or m.startswith(library + ".") for m in imports(p)))
    assert importers == [home], (
        f"{library} ne doit etre importe que par {home}, or : {importers}")


def test_every_layer_only_imports_the_layers_below_it():
    """Une couche basse qui importe une couche haute est le debut d'un cycle."""
    faults = []
    for path in modules():
        here = layer(path)
        allowed = ALLOWED.get(here)
        if allowed is None:      # __init__.py a la racine du paquet
            continue
        for module in imports(path):
            if not module.startswith("pipeline."):
                continue
            if target(module) not in allowed:
                faults.append(f"{path.relative_to(SRC)} -> {module}")
    assert not faults, "imports qui remontent une couche : %s" % faults


def test_every_layer_of_core_is_named_by_the_allowed_table():
    """Une couche absente de la table est une couche sans aucune regle.

    `ALLOWED.get(here)` rend None pour une cle inconnue, et le test ci-dessus
    passe alors le fichier sans rien verifier. Ajouter `core/quelque_chose/`
    sans l'y declarer ferait donc taire la regle au lieu de l'appliquer.
    """
    found = {f"{CORE}/{d.name}" for d in (SRC / CORE).iterdir()
             if d.is_dir() and not d.name.startswith("__")}
    missing = found - set(ALLOWED)
    assert not missing, f"couches de core/ hors de la table : {missing}"


def test_nothing_under_core_knows_a_workflow_or_the_launcher():
    """La frontiere framework/usage, en une assertion plutot qu'en quatre.

    C'est la regle qui justifie le dossier `core/` : ce qui est dedans se
    branche sous n'importe quel workflow, donc un troisieme workflow ne
    demande de toucher a rien. Dite ici directement, elle se lit d'un coup —
    et elle mord meme sur un sous-paquet de `core/` qu'on aurait oublie de
    declarer dans `ALLOWED`.
    """
    faults = []
    for path in modules():
        if not str(path.relative_to(SRC)).startswith(CORE + "/"):
            continue
        faults += [f"{path.relative_to(SRC)} -> {m}" for m in imports(path)
                   if m.startswith(("pipeline.workflows", "pipeline.launcher"))]
    assert not faults, "le framework connait son utilisateur : %s" % faults


def module_level_imports(path: pathlib.Path) -> list[str]:
    """Ce qu'un simple `import <ce module>` executerait, corps de fonction exclus."""
    found: list[str] = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Import):
                found.extend(alias.name for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                found.append("." * child.level + (child.module or ""))
            else:
                walk(child)

    walk(ast.parse(path.read_text(encoding="utf-8"), str(path)))
    return found


def stdlib_only() -> list[pathlib.Path]:
    return [p for p in modules()
            if str(p.relative_to(SRC)) in STDLIB_ONLY
            or str(p.relative_to(SRC)).startswith(STDLIB_ONLY_DIR)]


def test_the_launcher_entry_points_import_only_the_standard_library():
    """Ils tournent hors du venv : un import du paquet les casserait tous.

    Seuls les imports du niveau module comptent — les imports tardifs de
    `main.py` sont le mecanisme du routeur. Un import relatif compte : il
    nomme le paquet sans l'ecrire.
    """
    faults = []
    for path in stdlib_only():
        for module in module_level_imports(path):
            top = module.split(".")[0]
            if not top or top not in sys.stdlib_module_names:
                faults.append(f"{path.relative_to(SRC)} -> {module}")
    assert not faults, "imports hors stdlib au niveau module : %s" % faults


def test_the_stdlib_only_scan_covers_the_router_and_every_hook():
    """Un scan qui ne trouve rien ferait passer la regle ci-dessus."""
    found = {str(p.relative_to(SRC)) for p in stdlib_only()}
    assert set(STDLIB_ONLY) <= found
    assert sorted(n for n in found if n.startswith(STDLIB_ONLY_DIR)) == [
        "launcher/hooks/__init__.py", "launcher/hooks/branch_guard.py",
        "launcher/hooks/no_secret_paths.py",
        "launcher/hooks/pr_review_trigger.py",
        "launcher/hooks/scratchpad_notice.py"]


def test_the_domain_touches_neither_the_disk_nor_a_subprocess():
    """Ce qui rend le metier testable en lui passant des chaines."""
    banned = {"subprocess", "sqlite3", "shutil", "socket", "urllib", "requests"}
    for path in sorted((SRC / CORE / "domain").rglob("*.py")):
        offenders = sorted(banned & set(imports(path)))
        assert not offenders, f"{path.relative_to(SRC)} importe {offenders}"


def names_paths(path: pathlib.Path) -> list[str]:
    """Toute mention du module `paths` : un import, ou un `paths.X`."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names
                      if a.name.split(".")[-1] == "paths" or a.asname == "paths"]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[-1] == "paths":
                found.append(node.module)
            found += [f"{node.module}.{a.name}" for a in node.names
                      if a.name == "paths" or a.asname == "paths"]
        elif (isinstance(node, ast.Attribute)
              and isinstance(node.value, ast.Name) and node.value.id == "paths"):
            found.append(f"paths.{node.attr}")
    return found


HOME_OF_PATHS = "core/runtime/filesystem/"


def test_only_runtime_filesystem_names_the_paths_module():
    """La racine se recoit, elle ne se lit pas dans un global."""
    faults = []
    for path in modules():
        here = str(path.relative_to(SRC))
        if here.startswith(HOME_OF_PATHS):
            continue
        faults += [f"{here} -> {name}" for name in names_paths(path)]
    assert not faults, "le global est revenu : %s" % faults
    # Le garde-fou du garde-fou : un scan qui ne trouve rien passerait partout.
    assert names_paths(SRC / "core/runtime/filesystem/workspace.py")


def test_the_scan_actually_reads_the_package():
    """Un scan qui ne trouve rien ferait passer tout ce qui precede."""
    files = modules()
    assert len(files) > 30, files
    assert any(imports(p) for p in files)
    # et la regle de confinement porte bien sur du code qui existe
    assert (SRC / "core/adapters/agent/claude_sdk.py").exists()
    assert (SRC / "core/adapters/engine/crewai_engine.py").exists()


# --- la forme d'un workflow ------------------------------------------------
#
# Ce que `workflows/common/contract` promet, verifie sur les workflows qui
# existent. Ces quatre tests sont la difference entre une convention et une
# regle : le troisieme workflow ne peut pas deriver sans les faire echouer.

WORKFLOWS = "workflows/"
# `common` est le contrat lui-meme, `legacy` la bascule a usage unique qui
# meurt entiere — ni l'un ni l'autre n'est un workflow.
NOT_A_WORKFLOW = {"common", "legacy"}

# Les modules que tout workflow porte a sa racine, et la classe attendue dans
# chacun. `internals/` porte le reste, et n'a pas a se ressembler d'un
# workflow a l'autre.
ROOT_MODULES = ("workflow.py", "settings.py", "preconditions.py",
                "postconditions.py")

# Les sous-dossiers qu'un workflow a le droit de porter, et ce que chacun
# veut dire. Nommes plutot que libres : `glob("*.py")` ne regarde pas dans
# les dossiers, donc sans cette liste un nouveau sous-paquet echapperait en
# silence a toute regle de forme — ce qui est exactement ce qui venait
# d'arriver a `stages/`.
#
# `stages/` : la definition du workflow — quels stages il fait tourner, avec
# quel modele et quel texte. C'est ce qu'on ouvre pour le changer.
# `internals/` : sa mecanique, qui n'a pas a se ressembler d'un workflow a
# l'autre.
WORKFLOW_DIRS = {"stages", "internals"}

def workflow_packages() -> list[pathlib.Path]:
    """Les dossiers de `workflows/` qui sont des workflows."""
    return sorted(d for d in (SRC / "workflows").iterdir()
                  if d.is_dir() and not d.name.startswith("__")
                  and d.name not in NOT_A_WORKFLOW)


def test_the_workflow_scan_actually_finds_the_workflows():
    """Un scan qui ne trouve rien ferait passer les trois tests suivants."""
    found = {d.name for d in workflow_packages()}
    assert found == {"agentic_dev_loop", "pr_review"}, found


@pytest.mark.parametrize("module", ROOT_MODULES)
def test_every_workflow_carries_the_same_modules_at_its_root(module):
    """La forme commune : les memes fichiers, au meme endroit, partout."""
    missing = [d.name for d in workflow_packages() if not (d / module).exists()]
    assert not missing, f"{module} manque dans : {missing}"


def test_every_workflow_keeps_its_own_code_in_internals():
    """La racine est le contrat ; ce qui est propre au workflow est dessous.

    Sans cette regle, un module de plus a la racine redevient la situation
    d'avant : deux workflows qu'on ne peut pas lire de la meme facon.
    """
    allowed = {*ROOT_MODULES, "__init__.py"}
    faults = []
    for package in workflow_packages():
        extra = sorted(p.name for p in package.glob("*.py")
                       if p.name not in allowed)
        faults += [f"{package.name}/{name}" for name in extra]
    assert not faults, (
        "a la racine d'un workflow, mais ni contrat ni __init__ — "
        f"ils vont dans internals/ : {faults}")


def test_a_workflow_carries_no_subpackage_beyond_the_two_named_ones():
    """Un sous-dossier de plus echapperait a toute regle de forme.

    `test_every_workflow_keeps_its_own_code_in_internals` fait un
    `glob("*.py")` qui ne descend dans aucun dossier : sans ce test, creer
    `workflows/<nom>/quelque_chose/` ferait passer n'importe quoi.
    """
    faults = []
    for package in workflow_packages():
        for child in sorted(package.iterdir()):
            if (child.is_dir() and not child.name.startswith("__")
                    and child.name not in WORKFLOW_DIRS):
                faults.append(f"{package.name}/{child.name}/")
    assert not faults, (
        f"sous-dossier de workflow hors de {sorted(WORKFLOW_DIRS)} — "
        f"nomme-le dans WORKFLOW_DIRS et dis ce qu'il veut dire : {faults}")


# --- le domaine est du vocabulaire, pas une definition ---------------------
#
# Les deux tests qui portent la regle : `domain/` dit ce qu'un stage, une
# issue et un resultat *sont* ; quels stages tournent, sous quelles
# etiquettes et avec quel texte est la definition d'un workflow, et vit chez
# lui. Ce sont des tests sur le **texte** des modules et non sur leurs
# imports, parce que c'est le nommage qui trahit une instance qui remonte :
# un module du domaine peut parfaitement citer "agentic_dev_loop" sans
# l'importer, et il n'aurait deja plus rien a y faire.

def workflow_names() -> list[str]:
    return sorted(d.name for d in workflow_packages())


def test_no_module_of_the_domain_names_a_workflow():
    """Le vocabulaire ne connait aucun de ceux qui l'emploient.

    Ce que ce test empeche de revenir : `domain/stages/`
    `agentic_dev_loop_stages.py`, `domain/prompts/definitions/<workflow>/` et
    `domain/pr_review/` — des instances rangees dans le vocabulaire, qui
    faisaient du domaine le premier workflow avec les autres accroches
    dessus.
    """
    faults = []
    for path in sorted((SRC / CORE / "domain").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        faults += [f"{path.relative_to(SRC)} nomme {name!r}"
                   for name in workflow_names() if name in text]
    assert not faults, "le domaine nomme un workflow : %s" % faults


def test_only_its_own_workflow_names_the_pipeline_labels():
    """`pipeline:ready` ne veut rien dire pour une issue en general.

    Les sept etiquettes sont la definition du round : elles vivent dans
    `workflows/agentic_dev_loop/internals/tasks.py` et nulle part ailleurs.
    L'adaptateur, en particulier, n'a jamais a savoir ce qu'une etiquette
    signifie — il lit des issues, il ne decide pas.

    La regle porte sur `core/` : le framework n'a pas a savoir ce qu'un
    workflow appelle une task. Le launcher est l'autre bord et en est exclu —
    c'est la couche d'usage, son `--help` explique la boucle a un humain et
    doit pouvoir nommer `pipeline:ready`. `workflows/legacy` ecrit ces
    etiquettes — c'est son travail — et les importe du workflow.
    """
    scanned = 0
    faults = []
    for path in modules():
        here = str(path.relative_to(SRC))
        if not here.startswith(CORE + "/"):
            continue
        scanned += 1
        if "pipeline:" in path.read_text(encoding="utf-8"):
            faults.append(here)
    assert not faults, (
        f"les etiquettes pipeline: sont la definition du round, pas du"
        f" vocabulaire — vues dans : {faults}")
    # Les deux garde-fous du garde-fou. Le premier a deja servi : le passage a
    # `core/` a change ce que `layer()` rend, et la regle a cesse de scanner
    # quoi que ce soit tout en restant verte.
    assert scanned > 10, f"la regle ne scanne plus rien ({scanned} fichiers)"
    assert "pipeline:" in (
        SRC / "workflows/agentic_dev_loop/internals/tasks.py"
    ).read_text(encoding="utf-8")


def test_a_workflow_never_imports_another_workflow():
    """Ce qui rend le troisieme workflow facile, et le dit en assertion.

    Le commun passe par `workflows.common`. Un workflow qui en importerait un
    autre les relierait par un detail — c'est exactement ce que
    `legacy.migrate` faisait en important `agentic_dev_loop.board` pour une
    fabrique de trois lignes.
    """
    faults = []
    for package in workflow_packages():
        for path in sorted(package.rglob("*.py")):
            for module in imports(path):
                parts = module.split(".")
                if (len(parts) > 2 and parts[1] == "workflows"
                        and parts[2] not in (package.name, "common")):
                    faults.append(f"{path.relative_to(SRC)} -> {module}")
    assert not faults, "un workflow en importe un autre : %s" % faults


def test_the_common_package_never_imports_a_workflow():
    """Le contrat ne connait aucun de ses implementeurs.

    Sinon il ne serait pas un contrat : il serait le premier workflow, avec
    les autres accroches dessus.
    """
    faults = []
    for path in sorted((SRC / "workflows" / "common").rglob("*.py")):
        for module in imports(path):
            parts = module.split(".")
            if (len(parts) > 2 and parts[1] == "workflows"
                    and parts[2] != "common"):
                faults.append(f"{path.relative_to(SRC)} -> {module}")
    assert not faults, "le contrat connait un workflow : %s" % faults
