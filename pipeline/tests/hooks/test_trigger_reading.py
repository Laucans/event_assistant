"""Ce que le hook lit d'un evenement, sans rien lancer.

`reviewable` etait enfouie dans `main` : la tester demandait un sous-processus
et un faux `scripts/pr-review`. Sortie, elle prend un dictionnaire et rend un
numero — et c'est la seule chose qui decide si deux passes payantes partent.
"""

import pytest

from pipeline.launcher.hooks.pr_review_trigger import reviewable

URL = "https://github.com/o/r/pull/42"


def event(command="gh pr create --fill", stdout=URL, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": ""}}


def test_a_pr_that_was_just_opened_is_reviewable():
    assert reviewable(event()) == "42"


@pytest.mark.parametrize("command", [
    "gh pr create --fill",
    "gh pr create --base main_agent --title t --body b",
    "gh --repo o/r pr create",
    "git add -A && gh pr create --fill",
    "gh pr create --body-file - <<'EOF'\nun corps\nEOF",
])
def test_every_spelling_of_gh_pr_create_is_seen(command):
    """Des flags entre les mots, un heredoc apres, une commande devant."""
    assert reviewable(event(command)) == "42"


@pytest.mark.parametrize("command", [
    "gh pr merge --rebase", "gh pr view 42", "gh issue create",
    "git commit -m 'create a pr'",
])
def test_what_does_not_open_a_pr_launches_nothing(command):
    """Un faux positif ici depense deux passes payantes sur une PR au hasard."""
    assert reviewable(event(command)) is None


def test_the_url_is_what_decides_more_than_the_command():
    """Le motif de commande est permissif a dessein, l'URL fait la decision.

    `echo gh pr create` porte les trois mots mais n'ouvre rien — et n'imprime
    aucune URL, donc rien ne part. Vouloir resserrer le motif ferait rater les
    formes que la consigne du module dit d'accepter (un heredoc apres, une
    commande devant).
    """
    assert reviewable(event("echo gh pr create", stdout="gh pr create")) is None


def test_a_tool_that_is_not_bash_is_ignored():
    assert reviewable(event(tool="Write")) is None


def test_a_create_that_printed_no_url_launches_nothing():
    """`gh` a pu echouer : sans URL, il n'y a pas de PR a revoir."""
    assert reviewable(event(stdout="")) is None
    assert reviewable(event(stdout="error: pull request already exists")) is None


def test_the_url_is_read_from_stderr_too():
    """`gh` ecrit parfois la, et le hook ne doit pas rater la PR pour ca."""
    data = event(stdout="")
    data["tool_response"]["stderr"] = URL
    assert reviewable(data) == "42"


def test_a_plain_string_response_is_read_as_well():
    assert reviewable({"tool_name": "Bash",
                       "tool_input": {"command": "gh pr create"},
                       "tool_response": URL}) == "42"


@pytest.mark.parametrize("data", [
    {}, {"tool_name": "Bash"},
    {"tool_name": "Bash", "tool_input": None, "tool_response": None},
    {"tool_name": None, "tool_input": {"command": "gh pr create"}},
])
def test_a_shape_it_does_not_expect_never_raises(data):
    """Un hook casse ne doit jamais etre ce qui empeche d'ouvrir une PR."""
    assert reviewable(data) is None
