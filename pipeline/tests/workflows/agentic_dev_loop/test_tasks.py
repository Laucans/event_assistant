"""Les quatre regles de choix, exercees sur des `Issue` construites a la main.

Elles decidaient autrefois d'un markdown, et se testaient en lui passant un
milestone en chaine de caracteres. Elles decident maintenant d'un graphe
d'issues, et se testent en lui passant le graphe : aucun reseau, aucun
double, juste des objets.

Le cas qui compte le plus est le dernier de ce fichier — une erreur de
lecture ne doit jamais ressembler a « plus rien a faire », parce que c'est
l'entree qui declenche un `/planner` a plusieurs dollars.
"""

import pytest

from pipeline.core.domain.issues import Issue
from pipeline.workflows.agentic_dev_loop.internals import tasks


def task(number, *labels, state="open", blocked_by=(), title="Une task"):
    return Issue(number=number, title=title, state=state,
                 labels=tuple(labels), blocked_by=tuple(blocked_by))


def test_the_current_milestone_is_the_lowest_open_one():
    """Regle 1. Un ordre total, pour que l'ordre de l'API ne decide pas."""
    issues = [task(12, tasks.MILESTONE), task(4, tasks.MILESTONE),
              task(9, tasks.MILESTONE)]
    assert tasks.current_milestone(issues).number == 4


def test_a_closed_milestone_is_not_the_current_one():
    issues = [task(4, tasks.MILESTONE, state="closed"),
              task(9, tasks.MILESTONE)]
    assert tasks.current_milestone(issues).number == 9


def test_no_open_milestone_answers_none_rather_than_guessing():
    assert tasks.current_milestone([task(4, tasks.AGENT)]) is None


def test_the_next_task_is_the_lowest_ready_unblocked_one():
    """Regle 2, le cas nominal."""
    board = [task(11, tasks.AGENT, tasks.READY),
             task(10, tasks.AGENT, tasks.READY)]
    assert tasks.next_task(board).number == 10


def test_a_task_without_the_ready_label_is_never_picked():
    """Regle 4 : `pipeline:ready` commande tout."""
    assert tasks.next_task([task(10, tasks.AGENT)]) is None


def test_a_task_whose_blockers_are_all_closed_is_picked():
    """Un vrai parcours de graphe : ce sont les etats qui decident."""
    done = task(9, tasks.AGENT, state="closed")
    assert tasks.next_task(
        [task(10, tasks.AGENT, tasks.READY, blocked_by=[done])]).number == 10


def test_one_open_blocker_is_enough_to_hold_a_task_back():
    open_one = task(9, tasks.AGENT)
    closed_one = task(8, tasks.AGENT, state="closed")
    held = task(10, tasks.AGENT, tasks.READY, blocked_by=[closed_one, open_one])
    assert tasks.next_task([held]) is None


def test_a_human_issue_blocks_exactly_like_any_other_dependency():
    """Regle 3 : la porte humaine n'est plus un mecanisme a part."""
    human = task(9, tasks.HUMAN, title="Creer le projet Vercel")
    held = task(10, tasks.AGENT, tasks.READY, blocked_by=[human])
    assert tasks.next_task([held]) is None
    assert "human action" in tasks.why_not(held)
    assert "#9" in tasks.why_not(held)


def test_a_dependency_graph_is_not_a_chain_of_numbers():
    """#12 ne depend pas de #11 : elle depend de ce qu'elle declare.

    Le parallelisme est prevu, et il ne doit pas demander une migration de
    donnees pour arriver — d'ou un `blocked_by` reel plutot qu'un
    « l'issue precedente est-elle fermee ».
    """
    board = [task(11, tasks.AGENT, tasks.READY),
             task(12, tasks.AGENT, tasks.READY)]
    assert tasks.next_task(board).number == 11
    board[0] = task(11, tasks.AGENT, tasks.READY,
                    blocked_by=[task(3, tasks.AGENT)])
    assert tasks.next_task(board).number == 12


def test_only_agent_issues_are_candidates():
    """Une action humaine prete et debloquee n'est pas une task a faire tourner."""
    assert tasks.next_task([task(10, tasks.HUMAN, tasks.READY)]) is None


def test_a_closed_task_is_not_a_candidate():
    assert tasks.next_task(
        [task(10, tasks.AGENT, tasks.READY, state="closed")]) is None


def test_open_agent_tasks_ignores_the_milestone_and_the_human_items():
    board = [task(1, tasks.MILESTONE), task(2, tasks.HUMAN),
             task(3, tasks.AGENT), task(4, tasks.AGENT, state="closed")]
    assert [t.number for t in tasks.open_agent_tasks(board)] == [3]


def test_the_stuck_report_names_a_gesture_for_every_open_task():
    """« aucune task prete » ne nomme aucun geste ; ceci en nomme un."""
    blocked = task(11, tasks.AGENT, tasks.READY, title="Vercel",
                   blocked_by=[task(9, tasks.HUMAN)])
    said = tasks.stuck_report([task(10, tasks.AGENT, title="Schema"), blocked])
    assert f"no {tasks.READY} label" in said
    assert "blocked by #9" in said
    assert said.count("\n") == 1


def test_the_task_key_is_the_issue_number():
    """L'etat de reprise pointe un numero, plus un titre de markdown.

    Un titre reecrit changeait la cle et faisait repayer la task ; un numero
    d'issue ne bouge pas.
    """
    assert task(17, tasks.AGENT).key == "17"
    assert task(17, tasks.AGENT).ref == "#17"


@pytest.mark.parametrize("labels, kind", [
    ((tasks.AGENT,), "auto"), ((tasks.HUMAN,), "human")])
def test_the_kind_is_read_from_the_label(labels, kind):
    assert tasks.kind(task(1, *labels)) == kind


def test_the_spec_written_label_is_what_says_the_spec_exists():
    """Ce que `docs/current/SPEC.md` disait par sa presence."""
    assert not tasks.spec_written(task(1, tasks.AGENT))
    assert tasks.spec_written(task(1, tasks.AGENT, tasks.SPEC_WRITTEN))


def test_every_label_the_model_uses_is_declared_once():
    """Le preflight verifie cette liste sur le depot : elle doit etre complete."""
    assert set(tasks.LABELS) == {
        tasks.ROADMAP, tasks.MILESTONE, tasks.AGENT, tasks.HUMAN, tasks.READY,
        tasks.SPEC_WRITTEN, tasks.WAITING_MERGE}
    assert all(l.startswith("pipeline:") for l in tasks.LABELS)


# --- ce qu'une PR declare fermer -----------------------------------------

def test_a_closing_line_on_its_own_names_the_issue():
    assert tasks.closes("Ajoute le client.\n\nCloses #12\n", 12)


def test_the_keyword_is_read_case_insensitively_with_its_synonyms():
    for word in ("Closes", "closes", "Fixes", "FIXES", "Resolves"):
        assert tasks.closes(f"{word} #7", 7), word


def test_another_issue_number_is_not_this_one():
    assert not tasks.closes("Closes #120", 12)
    assert not tasks.closes("Closes #12", 120)


def test_the_keyword_buried_in_prose_does_not_count():
    """`/code` a pour consigne de la mettre sur sa propre ligne.

    Lire plus large ferait passer « ne ferme pas #12 » pour une fermeture,
    et la boucle fermerait une issue que personne n'a livree.
    """
    assert not tasks.closes("Cette PR ne closes #12 pas du tout.", 12)


def test_an_empty_body_closes_nothing():
    assert not tasks.closes("", 12)
    assert not tasks.closes(None, 12)


# --- pipeline:waiting-merge : livree, pas encore integree ----------------

def test_a_waiting_merge_task_is_never_picked_again():
    """Sans ca, le round suivant la rejouerait et repayerait trois stages."""
    board = [task(10, tasks.AGENT, tasks.READY, tasks.WAITING_MERGE)]
    assert tasks.next_task(board) is None


def test_a_waiting_merge_blocker_does_not_block_its_dependent():
    """Son code est sur la branche d'integration : la suivante peut batir
    dessus. C'est la seule lecture ou la chaine avance sans attendre une
    fusion dans `main`."""
    done = task(10, tasks.AGENT, tasks.WAITING_MERGE)
    nxt = task(11, tasks.AGENT, tasks.READY, blocked_by=[done])
    assert tasks.next_task([done, nxt]).number == 11


def test_an_open_blocker_still_blocks():
    """La contrepartie : seule l'etiquette libere, pas le simple fait d'exister."""
    todo = task(10, tasks.AGENT)
    nxt = task(11, tasks.AGENT, tasks.READY, blocked_by=[todo])
    assert tasks.next_task([todo, nxt]) is None


def test_a_human_blocker_is_unaffected_by_the_new_label():
    """Une action humaine ne se livre pas sur une branche : elle se ferme."""
    gate = task(10, tasks.HUMAN)
    nxt = task(11, tasks.AGENT, tasks.READY, blocked_by=[gate])
    assert tasks.next_task([gate, nxt]) is None
    assert tasks.next_task([task(10, tasks.HUMAN, state="closed"),
                            task(11, tasks.AGENT, tasks.READY,
                                 blocked_by=[task(10, tasks.HUMAN,
                                                  state="closed")])]) is not None


def test_why_not_names_the_merge_rather_than_a_missing_label():
    """Le geste qui debloque n'est pas le meme : ici c'est une fusion."""
    waiting = task(10, tasks.AGENT, tasks.READY, tasks.WAITING_MERGE)
    said = tasks.why_not(waiting)
    assert "waiting" in said and "merge" in said


def test_the_label_is_part_of_the_set_preflight_checks():
    assert tasks.WAITING_MERGE in tasks.LABELS


# --- laquelle des PR mergees vaut preuve de livraison ----------------------
#
# La regle a quitte `adapters.shell.github`, qui l'appliquait en listant les
# PR. L'adaptateur rend maintenant les PR mergees sur une base et rien de
# plus ; ce qui suit est la moitie qui decide, et elle se teste sans reseau.

def pr(number, body, title="une PR"):
    return Issue(number=number, title=title, body=body)


def test_the_first_merged_pr_that_closes_the_issue_is_the_proof():
    prs = [pr(3, "rien a voir"), pr(2, "Closes #12"), pr(1, "Closes #12")]
    assert tasks.first_closing(prs, 12).number == 2


def test_a_merged_pr_naming_another_issue_is_not_the_proof():
    assert tasks.first_closing([pr(2, "Closes #999")], 12) is None


def test_no_merged_pr_at_all_is_not_a_failure_it_is_an_absence():
    """« rien n'a ete livre » est une reponse, pas une panne : c'est
    l'adaptateur qui distingue l'API muette de l'API cassee."""
    assert tasks.first_closing([], 12) is None
