"""La traduction du markdown en plan d'issues, verifiee sur des chaines.

Le plan est ce que `--dry-run` imprime : le tester ici, c'est savoir ce que
la commande fera avant de la laisser ecrire quoi que ce soit sur GitHub.

Le dernier test lit les vrais documents du depot, tant qu'ils existent — la
migration les supprime. C'est le seul endroit qui verifie que le plan
annonce (10 items de roadmap, 4 tasks ouvertes, une action humaine) est bien
celui que ces fichiers-la produisent.
"""

import textwrap

from pipeline.workflows.legacy import migration
from pipeline.workflows.agentic_dev_loop.internals import tasks
from pipeline.runtime.filesystem.workspace import Workspace

ROADMAP = textwrap.dedent("""\
    # Roadmap

    Du blabla d'introduction.

    ## Foundation

    - [x] Deja fait — ne doit pas etre migre
    - [ ] Architecture setup — Next.js scaffold, tooling, CI
          et une suite indentee

    ## Core experience

    - [ ] Full data model — les tables
    """)

MILESTONE = textwrap.dedent("""\
    # Spec: Initial architecture setup

    ## Problem

    Le probleme.

    ## Goals / Non-goals

    Les buts.

    ## Approach

    La demarche.

    # Tasks

    **1. Fait** — ✅ DONE

    - Un detail.

    **2. La task en cours**

    - Un bullet.
    - Un autre.

    **3. Vercel deploy** _(needs you: creation du compte en ligne —
    human-only)_

    - Encore un bullet.

    ## Files & interfaces touched

    - Rien de tout ca ne doit finir dans l'issue.

    ## Edge cases

    - Ni ca.

    ## Out of scope

    - Ce qui n'est pas fait.

    ## Verification

    - Ni ca non plus.
    """)


def plan():
    return migration.plan(ROADMAP, MILESTONE)


def by_key(issues):
    return {i.key: i for i in issues}


def test_only_the_unchecked_roadmap_items_become_issues():
    items = migration.roadmap_items(ROADMAP)
    assert [i.title for i in items] == ["Architecture setup",
                                        "Full data model"]
    assert all(i.labels == (tasks.ROADMAP,) for i in items)


def test_an_item_that_runs_over_several_lines_keeps_one_body():
    body = migration.roadmap_items(ROADMAP)[0].body
    assert "Next.js scaffold, tooling, CI et une suite indentee" in body
    assert "under \"Foundation\"" in body


def test_the_title_stops_at_the_dash_and_the_rest_is_the_body():
    """Un titre d'issue se lit dans une liste ; la description vit dessous."""
    item = migration.roadmap_items(ROADMAP)[0]
    assert item.title == "Architecture setup"
    assert "Next.js scaffold" in item.body


def test_a_very_long_title_is_cut_on_a_word():
    long = "- [ ] " + "mot " * 40 + "\n"
    title = migration.roadmap_items(long)[0].title
    assert len(title) <= migration.TITLE_MAX + 1
    assert title.endswith("…")


def test_the_milestone_body_carries_four_sections_and_no_more():
    """Files & interfaces, Edge cases et Verification decrivent un depot
    dont les trois premieres tasks sont deja archivees."""
    head = migration.milestone_issue(MILESTONE)
    assert head.title == "Initial architecture setup"
    assert [l for l in head.body.splitlines() if l.startswith("## ")] == [
        "## Problem", "## Goals / Non-goals", "## Approach", "## Out of scope"]
    assert "Rien de tout ca" not in head.body
    assert "Ni ca" not in head.body


def test_the_done_tasks_are_not_migrated():
    """Elles sont archivees sous docs/archives/ : une issue fermee ouverte
    pour l'occasion ne raconterait rien de plus."""
    keys = by_key(migration.task_issues(MILESTONE))
    assert "t1" not in keys
    assert set(keys) == {"t2", "t3", "h3"}


def test_each_open_task_is_a_sub_issue_of_the_milestone():
    for issue in migration.task_issues(MILESTONE):
        assert issue.parent == "m"


def test_the_tasks_are_chained_in_order():
    keys = by_key(migration.task_issues(MILESTONE))
    assert keys["t2"].blocked_by == ()
    assert "t2" in keys["t3"].blocked_by


def test_a_needs_you_annotation_becomes_its_own_human_issue():
    """Tout ce qui reste de la porte humaine : une dependance comme une autre."""
    keys = by_key(migration.task_issues(MILESTONE))
    human = keys["h3"]
    assert human.labels == (tasks.HUMAN,)
    assert human.title == ("Vercel deploy: creation du compte en ligne —"
                           " human-only")
    assert "h3" in keys["t3"].blocked_by
    assert "will not pick that task up" in human.body


def test_the_milestone_hangs_off_the_first_roadmap_item():
    keys = by_key(plan())
    assert keys["m"].parent == "r1"
    assert keys["r1"].parent == ""


def test_nothing_in_the_plan_is_marked_ready():
    """Le robinet, c'est l'humain qui l'ouvre."""
    assert not any(tasks.READY in i.labels for i in plan())


def test_the_plan_never_links_forward():
    """Poser un lien demande que les deux issues existent : l'ordre de la
    liste est aussi celui des appels."""
    seen = set()
    for issue in plan():
        assert issue.parent in ("", *seen), issue.key
        assert set(issue.blocked_by) <= seen, issue.key
        seen.add(issue.key)


def test_the_real_documents_produce_the_migration_that_was_agreed():
    """Les vrais fichiers, tant qu'ils existent — la migration les supprime."""
    root = Workspace.here().root
    roadmap = root / "docs/ROADMAP.md"
    milestone = root / "docs/current/CURRENT_MILESTONE.md"
    if not (roadmap.exists() and milestone.exists()):
        return
    issues = migration.plan(roadmap.read_text(encoding="utf-8"),
                            milestone.read_text(encoding="utf-8"))
    kinds = [i.labels[0] for i in issues]
    assert kinds.count(tasks.ROADMAP) == 10
    assert kinds.count(tasks.MILESTONE) == 1
    assert kinds.count(tasks.AGENT) == 4
    assert kinds.count(tasks.HUMAN) == 1
    keys = by_key(issues)
    assert set(k for k in keys if k.startswith("t")) == {"t4", "t5", "t6", "t7"}
    assert keys["t5"].blocked_by == ("t4", "h5")
    assert keys["t6"].blocked_by == ("t5",)
    assert keys["t7"].blocked_by == ("t6",)
