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
  lui passant des chaines ;
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

# Qui a le droit d'importer quoi. La cle est un prefixe de chemin dans le
# paquet, la valeur les prefixes de `pipeline.*` qu'il peut importer.
ALLOWED: dict[str, set[str]] = {
    "domain": {"domain"},
    # `runtime` est une feuille, au meme titre que `domain` : chemins, journal
    # et mesures ne decident de rien et n'ont besoin de personne. `RunConfig`
    # y a vecu un temps et etait le seul a importer le domaine — ses methodes
    # parcourent PIPELINE, donc c'etait une politique deguisee en reglage. Elle
    # est dans `workflows/agentic_dev_loop/settings.py`.
    "runtime": {"runtime"},
    "adapters": {"adapters", "domain", "runtime"},
    "execution": {"adapters", "domain", "runtime", "execution"},  # pas workflows
    "workflows": {"adapters", "domain", "execution", "runtime", "workflows"},
    "launcher": {"adapters", "domain", "execution", "launcher", "runtime",
                 "workflows"},
}

# Ce qui doit rester chargeable par le python du systeme, hors du venv : les
# hooks, et le routeur par lequel ils passent.
STDLIB_ONLY = ("launcher/__init__.py", "launcher/main.py", "launcher/routes.py")
STDLIB_ONLY_DIR = "launcher/hooks/"

# Les bibliotheques qui n'ont le droit d'apparaitre qu'a un seul endroit.
CONFINED = {
    "claude_agent_sdk": "adapters/agent/claude_sdk.py",
    "crewai": "adapters/engine/crewai_engine.py",
    "crewai_core": "adapters/engine/crewai_engine.py",
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
    return path.relative_to(SRC).parts[0].removesuffix(".py")


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
            target = module.split(".")[1]
            if target not in allowed:
                faults.append(f"{path.relative_to(SRC)} -> {module}")
    assert not faults, "imports qui remontent une couche : %s" % faults


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
    for path in sorted((SRC / "domain").rglob("*.py")):
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


HOME_OF_PATHS = "runtime/filesystem/"


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
    assert names_paths(SRC / "runtime/filesystem/workspace.py")


def test_the_scan_actually_reads_the_package():
    """Un scan qui ne trouve rien ferait passer tout ce qui precede."""
    files = modules()
    assert len(files) > 30, files
    assert any(imports(p) for p in files)
    # et la regle de confinement porte bien sur du code qui existe
    assert (SRC / "adapters/agent/claude_sdk.py").exists()
    assert (SRC / "adapters/engine/crewai_engine.py").exists()


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
