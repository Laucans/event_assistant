"""Le tableau lu par-dessus le double : ce que le round recoit avant de payer.

Quatre lecteurs partagent ce module — le round, la boucle, le preflight et
`--status` — donc une erreur ici se paie quatre fois. Les deux cas qui
comptent sont ceux qu'on peut confondre : « plus aucune task ouverte », qui
autorise un `/planner`, et « des tasks ouvertes mais aucune jouable », qui ne
l'autorise pas.
"""

from pathlib import Path

from conftest import milestone

from pipeline.workflows.agentic_dev_loop.internals import tasks
from pipeline.domain.outcomes.result import Status
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.workflows.agentic_dev_loop.internals import board
from pipeline.workflows.common.utils import hub as adapters

WS = Workspace(Path("/un/depot"))


def read():
    """Le tableau, lu par-dessus le double que la fixture `hub` a pose.

    Rend la valeur : les tests qui exercent une lecture ratee appellent
    `read_result()` pour voir le `Result` lui-meme.
    """
    return read_result().value


def read_result():
    """Le meme, sans deballer — pour les cas ou la lecture n'aboutit pas."""
    return board.read(adapters.gh(WS))


def test_the_board_is_the_lowest_open_milestone_and_its_children(hub):
    hub.add("Un vieux milestone", tasks.MILESTONE, state="closed")
    number, numbers = milestone(hub, ready=(0,),
                                tasks=("Schema", "Vercel", "Docs"))
    here = read()
    assert here.milestone.number == number
    assert [t.number for t in here.tasks] == numbers
    assert here.next.title == "Schema"


def test_a_second_open_milestone_does_not_make_the_choice_ambiguous(hub):
    first, _ = milestone(hub, ready=(0,), tasks=("Schema",), title="Le premier")
    milestone(hub, ready=(0,), tasks=("Autre",), title="Le second")
    assert read().milestone.number == first


def test_no_open_milestone_stops_the_run_with_the_gesture_to_make(hub):
    got = read_result()
    assert got.status is Status.HALTED
    assert "no open pipeline:milestone issue" in got.reason


def test_every_task_closed_is_the_rollover_case(hub):
    number, numbers = milestone(hub, ready=(0,), tasks=("Schema",))
    hub.close(numbers[0])
    here = read()
    assert here.open_agents == []
    assert here.next is None


def test_open_but_not_ready_is_not_the_rollover_case(hub):
    """La confusion que ce test existe pour empecher coute un run opus."""
    milestone(hub, tasks=("Schema",))
    here = read()
    assert here.open_agents, "une task ouverte s'est lue comme un rollover"
    assert here.next is None
    assert "none can run" in here.stuck()
    assert f"Add {tasks.READY}" in here.stuck()


def test_the_stuck_message_names_the_human_issue_that_blocks(hub):
    number, numbers = milestone(hub, ready=(0,), tasks=("Vercel",))
    human = hub.add("Creer le compte Vercel", tasks.HUMAN)
    hub.link(number, human)
    hub.block(numbers[0], human)
    said = read().stuck()
    assert f"#{human}" in said and "human action" in said


def test_a_human_sub_issue_is_never_offered_as_the_next_task(hub):
    number, _ = milestone(hub, tasks=())
    human = hub.add("Creer le compte", tasks.HUMAN, tasks.READY)
    hub.link(number, human)
    here = read()
    assert here.next is None
    assert here.open_agents == []


def test_an_api_that_will_not_answer_stops_rather_than_reads_as_empty(hub):
    """La lecture degradee qui coute de l'argent, prise a la source."""
    milestone(hub, ready=(0,), tasks=("Schema",))
    hub.fails_on = "sub_issues"
    got = read_result()
    assert got.status is Status.UNREADABLE and "sub-issues" in got.reason
    assert got.value is None, "une lecture ratee ne rend jamais de tableau"


def test_the_board_keeps_the_client_that_read_it(hub):
    """Les stages reetiquettent l'issue : ils ne rouvrent pas de connexion."""
    milestone(hub, ready=(0,), tasks=("Schema",))
    here = read()
    assert here.gh.repo.value == "o/r"


def test_every_task_delivered_is_not_a_rollover_and_says_what_to_merge(hub):
    """Tout livre sur la branche d'integration n'est pas « milestone fini ».

    Basculer en rollover ici ferait ouvrir le milestone suivant alors que le
    precedent n'est pas dans `main` — et paierait un run opus pour le faire.
    """
    number, numbers = milestone(hub, ready=(0,), tasks=("Schema", "Page"))
    for n in numbers:
        hub.issues[n]["labels"].append({"name": tasks.WAITING_MERGE})
    here = read()
    assert here.open_agents, "une task livree s'est lue comme un rollover"
    assert here.next is None
    message = here.stuck()
    assert "waiting for" in message and "merge" in message
    assert f"Add {tasks.READY}" not in message, (
        "cocher pipeline:ready ne debloque rien ici — le geste est une fusion")


def test_a_delivered_task_no_longer_blocks_the_next_one(hub):
    """La chaine avance sans attendre une fusion dans `main`."""
    number, numbers = milestone(hub, ready=(1,), tasks=("Schema", "Page"))
    hub.issues[numbers[0]]["labels"].append({"name": tasks.WAITING_MERGE})
    assert read().next.number == numbers[1]
