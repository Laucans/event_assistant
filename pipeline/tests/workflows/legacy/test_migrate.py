"""La bascule, exercee entierement sur papier.

Elle n'est lancee qu'une fois dans la vie du depot, et elle ecrit sur
GitHub : c'est le genre de commande dont les tests sont la seule repetition
generale. Trois proprietes sont verifiees ici, et ce sont celles qui rendent
la vraie execution sure — `--dry-run` n'ecrit rien, une seconde execution ne
double rien, et rien ne recoit `pipeline:ready`.
"""

import textwrap

import pytest

from pipeline.adapters.store import resume
from pipeline.domain import tasks
from pipeline.domain.outcomes.result import Status
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.workflows.legacy import migrate

ROADMAP = textwrap.dedent("""\
    # Roadmap

    ## Foundation

    - [ ] Architecture setup — le scaffold
    - [ ] Chat integration — le chat
    """)

MILESTONE = textwrap.dedent("""\
    # Spec: Initial architecture setup

    ## Problem

    Le probleme.

    ## Out of scope

    Rien.

    # Tasks

    **1. Fait** — ✅ DONE

    **2. Schema**

    - Un bullet.

    **3. Vercel deploy** _(needs you: le compte)_

    - Un bullet.
    """)


@pytest.fixture
def docs(tmp_path):
    """Un depot de papier : les deux documents, et un pointeur de reprise."""
    (tmp_path / "docs/current").mkdir(parents=True)
    (tmp_path / migrate.ROADMAP).write_text(ROADMAP, encoding="utf-8")
    (tmp_path / migrate.MILESTONE).write_text(MILESTONE, encoding="utf-8")
    ws = Workspace(tmp_path)
    resume.write_pointer("2|Schema", "un-flow", ws.state)
    return ws


def run(dry_run=False, workspace=None):
    got = migrate.run(dry_run=dry_run, workspace=workspace)
    assert got.ok, f"la migration a echoue : {got.reason}"
    return got.value


def titles(hub, label):
    return sorted(i["title"] for i in hub.issues.values()
                  if {"name": label} in i["labels"])


def test_a_dry_run_writes_nothing_at_all(docs, hub):
    said = run(dry_run=True, workspace=docs)
    assert hub.issues == {}
    assert hub.wrote() == []
    assert (docs.root / migrate.ROADMAP).exists()
    assert (docs.root / migrate.CURRENT_DIR).exists()
    assert docs.state.exists()
    assert "dry run: nothing is written" in said


def test_a_dry_run_prints_every_issue_it_would_open(docs, hub):
    said = run(dry_run=True, workspace=docs)
    assert said.count("would create") == 6
    assert "[pipeline:roadmap] Architecture setup" in said
    assert "[pipeline:milestone] Initial architecture setup (sub-issue of [r1])" in said
    assert "[pipeline:human] Vercel deploy: le compte (sub-issue of [m])" in said
    assert "blocked by [t2], [h3]" in said
    # Le corps aussi : c'est ce qui sera ecrit, donc c'est ce qui se relit.
    assert "  | Le probleme." in said


def test_a_dry_run_over_a_half_migrated_repo_still_writes_nothing(docs, hub):
    """Le chemin qui ecrivait sans qu'on le demande : les liens d'une issue
    qui existe deja. Une issue creee n'est pas la seule facon d'ecrire."""
    hub.add("Architecture setup", tasks.ROADMAP)
    hub.add("Initial architecture setup", tasks.MILESTONE)
    said = run(dry_run=True, workspace=docs)
    assert hub.wrote() == []
    assert hub.subs == {}
    assert "would link: sub-issue of #1" in said


def test_the_issues_are_created_with_their_labels_and_their_links(docs, hub):
    run(workspace=docs)
    assert titles(hub, tasks.ROADMAP) == ["Architecture setup",
                                          "Chat integration"]
    assert titles(hub, tasks.MILESTONE) == ["Initial architecture setup"]
    assert titles(hub, tasks.AGENT) == ["Schema", "Vercel deploy"]
    assert titles(hub, tasks.HUMAN) == ["Vercel deploy: le compte"]

    numbers = {i["title"]: n for n, i in hub.issues.items()}
    milestone = numbers["Initial architecture setup"]
    assert hub.subs[numbers["Architecture setup"]] == [milestone]
    assert sorted(hub.subs[milestone]) == sorted(
        [numbers["Schema"], numbers["Vercel deploy: le compte"],
         numbers["Vercel deploy"]])
    assert sorted(hub.blocked[numbers["Vercel deploy"]]) == sorted(
        [numbers["Schema"], numbers["Vercel deploy: le compte"]])


def test_the_done_tasks_are_left_where_they_are(docs, hub):
    run(workspace=docs)
    assert "Fait" not in [i["title"] for i in hub.issues.values()]


def test_nothing_comes_out_ready(docs, hub):
    run(workspace=docs)
    assert all(tasks.READY not in hub.labels_of(n) for n in hub.issues)


def test_running_it_twice_creates_nothing_the_second_time(docs, hub):
    run(workspace=docs)
    (docs.root / "docs/current").mkdir(parents=True, exist_ok=True)
    (docs.root / migrate.ROADMAP).write_text(ROADMAP, encoding="utf-8")
    (docs.root / migrate.MILESTONE).write_text(MILESTONE, encoding="utf-8")
    before = dict(hub.issues)
    said = run(workspace=docs)
    assert hub.issues.keys() == before.keys()
    assert said.count("exists already") == 6


def test_an_interrupted_migration_finishes_on_the_second_run(docs, hub):
    """Le cas que l'idempotence existe pour : moitie ecrit, on relance."""
    hub.add("Architecture setup", tasks.ROADMAP)
    run(workspace=docs)
    assert titles(hub, tasks.ROADMAP) == ["Architecture setup",
                                          "Chat integration"]
    assert len(hub.issues) == 6


def test_a_link_missing_from_an_issue_that_exists_is_posed_on_the_rerun(docs,
                                                                       hub):
    """Interrompue entre la creation et le lien : c'est ce qu'on retrouve."""
    roadmap = hub.add("Architecture setup", tasks.ROADMAP)
    orphan = hub.add("Initial architecture setup", tasks.MILESTONE)
    run(workspace=docs)
    assert hub.subs[roadmap] == [orphan]
    assert len(hub.subs[orphan]) == 3


def test_a_link_already_there_is_not_posed_twice(docs, hub):
    run(workspace=docs)
    (docs.root / "docs/current").mkdir(parents=True, exist_ok=True)
    (docs.root / migrate.ROADMAP).write_text(ROADMAP, encoding="utf-8")
    (docs.root / migrate.MILESTONE).write_text(MILESTONE, encoding="utf-8")
    before = {n: list(v) for n, v in hub.subs.items()}
    run(workspace=docs)
    assert hub.subs == before


def test_the_documents_and_the_resume_pointer_are_cleared_at_the_end(docs, hub):
    """La cle du pointeur est un titre de markdown : elle ne designe plus rien."""
    said = run(workspace=docs)
    assert not (docs.root / migrate.ROADMAP).exists()
    assert not (docs.root / migrate.CURRENT_DIR).exists()
    assert not docs.state.exists()
    assert "deleted:" in said and "cleared:" in said


def test_a_missing_roadmap_says_the_migration_may_already_be_done(docs, hub):
    (docs.root / migrate.ROADMAP).unlink()
    got = migrate.run(dry_run=False, workspace=docs)
    assert got.status is Status.HALTED
    assert "nothing to migrate from" in got.reason
    assert hub.issues == {}


def test_a_github_that_refuses_a_write_says_nothing_was_rolled_back(docs, hub):
    hub.refuses_writes = True
    got = migrate.run(dry_run=False, workspace=docs)
    assert got.status is Status.HALTED
    assert "refused to create the issue" in got.reason
    assert (docs.root / migrate.ROADMAP).exists(), "les documents ont ete effaces"
