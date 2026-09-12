"""Le tableau d'issues vu par l'adaptateur : les chemins d'API et les pannes.

Rien ici n'appelle `gh` : `GitHub(run=...)` prend le double de
`fake_github`, qui implemente les points d'entree que cet adaptateur
utilise — y compris la distinction entre le numero d'une issue et son
identifiant interne, que les liens exigent et qu'une implementation pressee
confondrait.
"""

import subprocess
from pathlib import Path

import pytest
from fake_github import FakeGitHub

from pipeline.adapters.shell import github
from pipeline.domain import tasks
from pipeline.domain.outcomes.result import Status


@pytest.fixture
def fake():
    return FakeGitHub()


@pytest.fixture
def hub(fake):
    return github.GitHub(Path("/un/depot"), run=fake)


def test_the_repository_is_resolved_once_and_remembered(fake, hub):
    assert hub.repo.value == "o/r"
    assert hub.repo.value == "o/r"
    assert sum(1 for c in fake.calls if c[:2] == ("repo", "view")) == 1


def test_a_repository_gh_cannot_name_stops_rather_than_guessing(fake, hub):
    fake.repo_code = 1
    got = hub.labels()
    assert got.status is Status.UNREADABLE
    assert "the repository name" in got.reason


def test_an_issue_comes_back_in_the_shape_the_domain_reads(fake, hub):
    n = fake.add("Schema", tasks.AGENT, tasks.READY, body="le SPEC")
    got = hub.issue(n).value
    assert (got.number, got.title, got.state, got.body) == (
        n, "Schema", "open", "le SPEC")
    assert got.labels == (tasks.AGENT, tasks.READY)
    assert got.ready and got.agent


def test_listing_by_label_leaves_the_pull_requests_out(fake, hub):
    """`/issues` rend aussi les PR : une PR etiquetee par megarde deviendrait
    le milestone en cours."""
    fake.add("Un milestone", tasks.MILESTONE)
    number = fake.add("Une PR", tasks.MILESTONE)
    fake.issues[number]["pull_request"] = {"url": "..."}
    assert [t.title for t in hub.issues_labelled(tasks.MILESTONE).value] == [
        "Un milestone"]


def test_listing_by_label_can_ask_for_the_closed_ones(fake, hub):
    fake.add("Ouverte", tasks.AGENT)
    fake.add("Fermee", tasks.AGENT, state="closed")
    assert [t.title for t in hub.issues_labelled(tasks.AGENT).value] == [
        "Ouverte"]
    assert [t.title
            for t in hub.issues_labelled(tasks.AGENT, state="closed").value
            ] == ["Fermee"]


def test_the_sub_issues_and_the_dependencies_come_back_as_tasks(fake, hub):
    m = fake.add("Milestone", tasks.MILESTONE)
    a = fake.add("A", tasks.AGENT)
    b = fake.add("B", tasks.AGENT)
    fake.link(m, a)
    fake.link(m, b)
    fake.block(b, a)
    assert [t.number for t in hub.sub_issues(m).value] == [a, b]
    assert [t.number for t in hub.blocked_by(b).value] == [a]
    assert [t.number for t in hub.blocking(a).value] == [b]


def test_with_blockers_carries_the_state_of_each_blocker(fake, hub):
    """Savoir qu'une task est bloquee ne suffit pas : il faut l'etat."""
    a = fake.add("A", tasks.AGENT)
    b = fake.add("B", tasks.AGENT, tasks.READY)
    fake.block(b, a)
    held = hub.with_blockers([hub.issue(b).value]).value[0]
    assert not held.runnable
    fake.close(a)
    freed = hub.with_blockers([hub.issue(b).value]).value[0]
    assert freed.runnable and freed.blocked_by[0].closed


def test_the_labels_of_the_repository_are_read_by_name(hub):
    assert set(tasks.LABELS) <= set(hub.labels().value)


def test_creating_an_issue_sends_every_label_and_returns_the_number(fake, hub):
    made = hub.create_issue("Nouvelle", "un corps",
                            (tasks.AGENT, tasks.HUMAN)).value
    assert fake.issues[made.number]["title"] == "Nouvelle"
    assert fake.body_of(made.number) == "un corps"
    assert fake.labels_of(made.number) == [tasks.AGENT, tasks.HUMAN]


def test_a_label_is_added_and_removed_without_touching_the_others(fake, hub):
    n = fake.add("Schema", tasks.AGENT)
    hub.add_label(n, tasks.SPEC_WRITTEN)
    assert fake.labels_of(n) == [tasks.AGENT, tasks.SPEC_WRITTEN]
    hub.remove_label(n, tasks.SPEC_WRITTEN)
    assert fake.labels_of(n) == [tasks.AGENT]


def test_the_body_and_the_state_can_be_rewritten(fake, hub):
    n = fake.add("Schema", tasks.AGENT)
    hub.set_body(n, "le SPEC ecrit par l'analyste")
    assert fake.body_of(n) == "le SPEC ecrit par l'analyste"
    hub.close_issue(n)
    assert hub.issue(n).value.closed


def test_a_link_is_posted_with_the_internal_id_not_the_number(fake, hub):
    """`sub_issue_id` et `issue_id` prennent l'id interne. Les confondre
    poserait le lien sur une autre issue, ou sur aucune."""
    m = fake.add("Milestone", tasks.MILESTONE)
    a = fake.add("A", tasks.AGENT)
    b = fake.add("B", tasks.AGENT)
    hub.add_sub_issue(m, a)
    hub.add_dependency(b, a)
    assert fake.subs[m] == [a]
    assert fake.blocked[b] == [a]
    posted = [c for c in fake.calls if "sub_issue_id=%d" % (1000 + a) in c]
    assert posted, "l'id interne n'a pas ete envoye"


def test_a_read_that_fails_is_a_failure_not_an_empty_answer(fake, hub):
    """La regle qui coute de l'argent : `[]` se lirait « milestone termine »."""
    fake.fails_on = "issues"
    got = hub.issues_labelled(tasks.AGENT)
    assert got.status is Status.UNREADABLE
    assert got.value is None, "un echec ne porte jamais de valeur lisible"
    said = got.reason
    assert "unknown" in said and "roadmap item nobody asked for" in said
    assert "gh auth status" in said


def test_an_answer_that_is_not_json_is_a_failure_too(hub, monkeypatch):
    def garbage(*args, check=True):
        if args[:2] == ("repo", "view"):
            return subprocess.CompletedProcess(args, 0, "o/r\n", "")
        return subprocess.CompletedProcess(args, 0, "<html>502</html>", "")

    monkeypatch.setattr(hub, "_run", garbage)
    got = hub.issue(4)
    assert got.status is Status.UNREADABLE and "JSONDecodeError" in got.reason


def test_a_write_that_fails_says_nothing_was_rolled_back(fake, hub):
    fake.fails_on = "issues"
    got = hub.create_issue("Nouvelle", "corps", (tasks.AGENT,))
    assert got.status is Status.HALTED
    assert "GitHub refused to" in got.reason


def test_reading_an_issue_that_does_not_exist_is_a_read_failure(hub):
    got = hub.issue(404)
    assert got.status is Status.UNREADABLE and "issue #404" in got.reason


# --- la PR qui a ferme la task -------------------------------------------

def test_the_merged_pr_that_declares_closing_the_issue_is_found(fake, hub):
    n = fake.add("Brancher le client", tasks.AGENT)
    fake.add_pr("feat(db): le client", body=f"Closes #{n}", base="main_agent",
                merged=True)
    got = hub.merged_pr_closing(n, "main_agent")
    assert got.ok and got.value.title == "feat(db): le client"


def test_a_pr_that_is_closed_but_never_merged_does_not_count(fake, hub):
    """Une PR refermee sans merge n'a rien livre."""
    n = fake.add("Brancher le client", tasks.AGENT)
    fake.add_pr("abandonnee", body=f"Closes #{n}", base="main_agent",
                merged=False)
    assert hub.merged_pr_closing(n, "main_agent").value is None


def test_a_merged_pr_naming_another_issue_does_not_count(fake, hub):
    n = fake.add("Brancher le client", tasks.AGENT)
    fake.add_pr("autre chose", body="Closes #999", base="main_agent",
                merged=True)
    assert hub.merged_pr_closing(n, "main_agent").value is None


def test_the_base_branch_is_the_one_asked_for(fake, hub):
    n = fake.add("Brancher le client", tasks.AGENT)
    fake.add_pr("ailleurs", body=f"Closes #{n}", base="main", merged=True)
    assert hub.merged_pr_closing(n, "main_agent").value is None
    assert hub.merged_pr_closing(n, "main").value is not None


def test_an_unreadable_pr_list_fails_rather_than_reading_as_none(fake, hub):
    """Sans ca, une panne d'API se lirait « rien n'a ete livre »."""
    n = fake.add("Brancher le client", tasks.AGENT)
    fake.fails_on = "pulls"
    got = hub.merged_pr_closing(n, "main_agent")
    assert got.status is Status.UNREADABLE
    assert got.value is None
