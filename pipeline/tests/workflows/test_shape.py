"""Le contrat, verifie sur les workflows qui existent vraiment.

`tests/core/execution/test_contract.py` tient ce que `sequence()` promet,
avec des doubles. Ici c'est l'autre moitie : ce que chaque workflow declare
monte bien un objet qui expose les quatre attributs et les deux methodes, ce
que `isinstance(w, contract.Workflow)` sait dire puisque le `Protocol` est
`runtime_checkable`.

Les workflows sont **decouverts**, pas listes : un troisieme est verifie sans
que personne y pense. Ce qu'on ne peut pas deviner est sa config — `pr` et
`base` n'ont pas de defaut, et leur en inventer un ferait construire une
revue sans PR. Elle vient donc d'une table, et un workflow absent de cette
table fait echouer le test au lieu d'etre saute en silence.
"""

import importlib

import pytest

from pipeline.core import design
from pipeline.core.execution.contract import workflow as contract
from pipeline.core.execution.contract.gate import Check
from pipeline.core.execution.shapes import Shape
from pipeline.core.runtime.monitoring import logbook
from test_layering import workflow_packages


# La config minimale de chaque workflow : ce qu'un run ne peut pas deviner.
CONFIGS = {
    "agentic_dev_loop": lambda cls: cls(),
    "pr_review": lambda cls: cls(pr="12", base="main_agent"),
}


def blueprints():
    """`(nom, blueprint)` pour chaque workflow du dossier."""
    found = []
    for package in workflow_packages():
        module = importlib.import_module(
            f"pipeline.workflows.{package.name}.workflow")
        found.append((package.name, module.WORKFLOW))
    return found


NAMES = [name for name, _ in blueprints()]


def test_the_scan_finds_a_blueprint_for_every_workflow():
    """Un scan qui ne trouve rien ferait passer tout ce qui suit."""
    assert len(NAMES) >= 2, NAMES


def test_every_workflow_has_a_config_in_the_table():
    """Sinon un troisieme workflow serait saute au lieu d'etre verifie."""
    assert sorted(NAMES) == sorted(CONFIGS), (
        "ajoute la config minimale du nouveau workflow a CONFIGS")


@pytest.mark.parametrize("name", NAMES)
def test_every_workflow_declares_a_blueprint(name):
    """La forme promise par `workflows/ARCHITECTURE.md`, en assertion."""
    blueprint = dict(blueprints())[name]
    assert isinstance(blueprint, design.Blueprint)
    assert blueprint.name, "un workflow sans nom n'a pas de commande"
    assert isinstance(blueprint.shape, Shape)
    assert all(isinstance(gate, Check) for gate in blueprint.gates)


@pytest.mark.parametrize("name", NAMES)
def test_what_every_workflow_builds_satisfies_the_contract(name):
    blueprint = dict(blueprints())[name]
    cfg = CONFIGS[name](blueprint.config)
    built = design.workflow(blueprint, cfg, logbook.open_logbook("test"))
    assert isinstance(built, contract.Workflow)


@pytest.mark.parametrize("name", NAMES)
def test_every_workflow_carries_both_guards(name):
    """`sequence()` les appelle sans les construire : elles sont deja la."""
    blueprint = dict(blueprints())[name]
    cfg = CONFIGS[name](blueprint.config)
    built = design.workflow(blueprint, cfg, logbook.open_logbook("test"))
    assert isinstance(built.preconditions, contract.Preconditions)
    assert isinstance(built.postconditions, contract.Postconditions)
