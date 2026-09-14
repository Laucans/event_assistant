"""Ce qu'un round ecrit : le corps, le commentaire, les etiquettes.

L'etape ou tout ce que le round a paye devient durable. Ce que ce fichier
protege : une section qu'aucun stage n'a rejouee ne doit pas disparaitre du
corps, et un `--dry-run` ne doit rien poser du tout.
"""

import asyncio
import types

import pytest

from pipeline.core.adapters.agent.base import AgentResult
from pipeline.core.adapters.shell import binaries
from pipeline.core.domain.outcomes.result import Status
from pipeline.core.domain.outcomes.stage_result import StageResult
from pipeline.core.execution import session as session_mod
from pipeline.core.execution.context import Ctx
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.launcher.cli import refinement as cli
from pipeline.workflows.common import labels
from pipeline.workflows.refinement.internals import publish, refine
from pipeline.workflows.refinement.settings import RefinementConfig

RAW = "je voudrais un bouton bleu"
ROUND_ONE_BODY = ("## Business Goal\n\nLe but.\n\n"
                  "## Technical\n\nLa technique.\n\n"
                  "## Acceptance Criteria\n\n- un critere\n")


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path)


def answered(text: str) -> StageResult:
    return StageResult(text=text, cost=0.0, session_id="s", ok_line=None,
                       stop_line=None)


def staged(cfg, issue, *, round_no, found, wanted, results):
    """L'etat et le contexte tels que la sequence les tient a la publication."""
    state = refine.RefinementState()
    state.issue = issue
    state.round_no = round_no
    state.found = dict(found)
    state.wanted = list(wanted)
    ctx = Ctx(cfg=cfg, log=logbook.null(),
              log_dir=cfg.workspace.refinement_dir, round_no=round_no,
              results={key: answered(text) for key, text in results.items()},
              workspace=cfg.workspace)
    return ctx, state


def issue_of(hub, ws, number):
    from pipeline.core.adapters import hub as adapters
    return adapters.gh(ws).issue(number).value


def write(hub, ws, number, *, round_no=1, found=None, wanted=(), results=None,
          **kw):
    cfg = RefinementConfig(issue=number, workspace=ws, **kw)
    ctx, state = staged(cfg, issue_of(hub, ws, number), round_no=round_no,
                        found=found or {}, wanted=wanted,
                        results=results or {})
    return publish.write(ctx, state), state


def task(hub, *extra, body=RAW, title="Une task"):
    return hub.add(title, labels.AGENT, labels.REFINEMENT, *extra, body=body)


# --- le corps assemble -----------------------------------------------------


def test_the_body_becomes_the_sections_the_round_produced(hub, ws):
    number = task(hub)
    got, _ = write(hub, ws, number,
                   wanted=("business-goal", "technical",
                           "acceptance-criteria"),
                   results={"business-goal": "Le but.",
                            "technical": "La technique.",
                            "acceptance-criteria": "- un critere"})
    assert got.ok
    assert hub.body_of(number) == ROUND_ONE_BODY


def test_the_raw_request_of_round_one_is_not_kept_around_the_sections(hub, ws):
    number = task(hub)
    write(hub, ws, number, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    assert RAW not in hub.body_of(number)


def test_a_section_this_round_does_not_replay_survives_untouched(hub, ws):
    """Le round 2 n'achete pas les trois sections du round 1 : il les garde."""
    number = task(hub, body=ROUND_ONE_BODY)
    write(hub, ws, number, round_no=2,
          found={"business-goal": "Le but.", "technical": "La technique.",
                 "acceptance-criteria": "- un critere"},
          wanted=("business-rules", "technical-plan"),
          results={"business-rules": "1. une regle",
                   "technical-plan": "1. une etape"})
    assert hub.body_of(number) == (
        ROUND_ONE_BODY + "\n## Business Rules\n\n1. une regle\n"
        "\n## Technical Implementation Plan\n\n1. une etape\n")


def test_a_stage_that_produced_nothing_does_not_erase_its_section(hub, ws):
    """Une session muette effacerait ce que la precedente avait paye."""
    number = task(hub, body=ROUND_ONE_BODY)
    write(hub, ws, number, round_no=2,
          found={"business-goal": "Le but."},
          wanted=("business-goal",), results={"business-goal": "   \n "})
    assert hub.body_of(number) == "## Business Goal\n\nLe but.\n"


def test_a_stage_the_sequence_never_ran_does_not_erase_its_section_either(
        hub, ws):
    number = task(hub, body=ROUND_ONE_BODY)
    write(hub, ws, number, round_no=2, found={"business-goal": "Le but."},
          wanted=("business-goal",), results={})
    assert hub.body_of(number) == "## Business Goal\n\nLe but.\n"


# --- la coherence retouche le corps, ou est ignoree en bloc -----------------


def test_a_coherent_retouch_replaces_the_plain_merge(hub, ws):
    """Ce qu'elle rend, quand elle garde tout, devient le corps publie."""
    number = task(hub)
    got, _ = write(hub, ws, number,
                   wanted=("business-goal", "technical",
                           "acceptance-criteria"),
                   results={"business-goal": "Le but.",
                            "technical": "La technique.",
                            "acceptance-criteria": "- un critere",
                            "coherence": "## Business Goal\n\nLe but retouche.\n\n"
                                        "## Technical\n\nLa technique.\n\n"
                                        "## Acceptance Criteria\n\n- un critere\n"})
    assert got.ok
    assert hub.body_of(number) == (
        "## Business Goal\n\nLe but retouche.\n\n"
        "## Technical\n\nLa technique.\n\n"
        "## Acceptance Criteria\n\n- un critere\n")


def test_a_retouch_that_drops_a_section_is_ignored_in_block(hub, ws):
    """Perdre une section en corrigeant les autres serait une incoherence de
    plus, pas une de moins : le round publie le simple merge a la place."""
    number = task(hub)
    got, _ = write(hub, ws, number,
                   wanted=("business-goal", "technical"),
                   results={"business-goal": "Le but.",
                            "technical": "La technique.",
                            "coherence": "## Business Goal\n\nLe but retouche.\n"})
    assert got.ok
    assert hub.body_of(number) == (
        "## Business Goal\n\nLe but.\n\n## Technical\n\nLa technique.\n")


def test_a_coherence_output_with_no_recognised_heading_is_ignored(hub, ws):
    number = task(hub)
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": "Le but.",
                            "coherence": "n'importe quoi, sans titres"})
    assert got.ok
    assert hub.body_of(number) == "## Business Goal\n\nLe but.\n"


def test_no_coherence_result_leaves_the_plain_merge_untouched(hub, ws):
    """Le dry-run et toute reprise qui a saute la coherence : le contrat par
    defaut, deja couvert implicitement par le reste de cette suite."""
    number = task(hub)
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": "Le but."})
    assert got.ok
    assert hub.body_of(number) == "## Business Goal\n\nLe but.\n"


def test_a_round_with_nothing_to_write_fails_instead_of_emptying_the_issue(
        hub, ws):
    """Un corps vide efface la demande et ne laisse rien a sa place."""
    number = task(hub)
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": ""})
    assert got.status is Status.FAILED
    assert hub.body_of(number) == RAW


# --- le texte est garde avant d'etre envoye --------------------------------


def test_the_body_is_kept_on_disk_under_the_issue_and_the_round(hub, ws):
    number = task(hub)
    write(hub, ws, number, round_no=3, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    kept = ws.refinement_dir / f"{number}-r03-body.md"
    assert kept.read_text(encoding="utf-8") == "## Business Goal\n\nLe but.\n"


def test_a_body_github_refused_is_still_on_disk_and_the_message_says_where(
        hub, ws):
    """Cinq sections opus ne se perdent pas sur un appel reseau rate."""
    number = task(hub)
    hub.refuses_writes = True
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": "Le but."})
    assert got.status is Status.FAILED
    assert f"{number}-r01-body.md" in got.reason
    assert "gh issue edit" in got.reason
    assert (ws.refinement_dir / f"{number}-r01-body.md").exists()


# --- le commentaire de fin de round ----------------------------------------


def test_the_round_is_commented_and_the_comment_says_only_that(hub, ws):
    number = task(hub)
    write(hub, ws, number, round_no=2, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    assert hub.comments[number] == ["refinement round: 2"]


def test_a_comment_github_refused_is_not_swallowed(hub, ws):
    number = task(hub)
    hub.fails_on = "comments"
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": "Le but."})
    assert got.failed


# --- les etiquettes --------------------------------------------------------


def test_the_refinement_label_is_removed_once_the_round_is_written(hub, ws):
    number = task(hub)
    write(hub, ws, number, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    assert labels.REFINEMENT not in hub.labels_of(number)


def test_a_forced_round_does_not_remove_a_label_the_issue_never_had(hub, ws):
    """`gh` rend 404 en retirant une etiquette absente, et le round echouerait."""
    number = hub.add("Une task", labels.AGENT, body=RAW)
    got, _ = write(hub, ws, number, force=True, wanted=("business-goal",),
                   results={"business-goal": "Le but."})
    assert got.ok
    assert not [c for c in hub.wrote() if "DELETE" in c]


@pytest.mark.parametrize("round_no, marked", [(1, False), (2, True), (3, True)])
def test_an_agent_task_is_specified_at_the_end_of_round_two(hub, ws, round_no,
                                                            marked):
    """`pipeline:spec-written` ouvre la task a la boucle : pas avant le plan."""
    number = task(hub)
    write(hub, ws, number, round_no=round_no, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    assert (labels.SPEC_WRITTEN in hub.labels_of(number)) is marked


@pytest.mark.parametrize("round_no", [1, 2])
def test_a_human_task_is_specified_from_the_end_of_round_one(hub, ws, round_no):
    """Elle n'a pas de plan d'implementation a attendre."""
    number = hub.add("Une action humaine", labels.HUMAN, labels.REFINEMENT,
                     body=RAW)
    write(hub, ws, number, round_no=round_no, wanted=("business-goal",),
          results={"business-goal": "Le but."})
    assert labels.SPEC_WRITTEN in hub.labels_of(number)


# --- le round entier, de la CLI a l'issue ----------------------------------
#
# Rien n'appelle `gh` ni `claude` : le depot est sur papier, et le moteur
# d'agent est un double scriptable branche la ou une session se construit.

MARKS = (("You are establishing the map", "explore"),
         ("You are routing", "router"),
         ("You are the last step", "coherence"),
         ("**Technical Implementation Plan**", "technical-plan"),
         ("**Business Goal**", "business-goal"),
         ("**Technical** section", "technical"),
         ("**Acceptance Criteria**", "acceptance-criteria"),
         ("**Business Rules**", "business-rules"))


def stage_of(prompt: str) -> str:
    """Quel stage ce prompt monte. Une table qui ne reconnait rien echoue."""
    for mark, skill in MARKS:
        if mark in prompt:
            return skill
    raise AssertionError("prompt monte pour aucun stage connu")


@pytest.fixture
def engine(monkeypatch):
    """Les sessions payantes, remplacees la ou elles se construisent."""
    ran: list[str] = []
    prompts: list[str] = []
    script: dict[str, str] = {}
    state = types.SimpleNamespace(ran=ran, prompts=prompts, script=script,
                                  fails_on="")

    class Engine:
        async def run(self, prompt, *, model, effort, permission_mode,
                      progress=None):
            skill = stage_of(prompt)
            ran.append(skill)
            prompts.append(prompt)
            failed = skill == state.fails_on
            return AgentResult(text="" if failed else script.get(
                                   skill, f"le {skill}"),
                               is_error=failed, subtype="error" if failed
                               else "success",
                               session_id="sess-1", cost_usd=0.0,
                               duration_ms=1.0, turns=1,
                               usage={"input_tokens": 1, "output_tokens": 1},
                               raw={"result": "ok"})

    monkeypatch.setattr(session_mod, "default_runner", lambda ws: Engine())
    return state


@pytest.fixture
def refined(ws, hub, repo, engine, monkeypatch):
    """Un `scripts/refinement` qui n'appelle rien : ni `gh`, ni `claude`."""
    monkeypatch.setattr(binaries, "shutil",
                        types.SimpleNamespace(which=lambda n: "/usr/bin/" + n))
    monkeypatch.setattr(cli, "make_logger",
                        lambda issue, workspace, level=logbook.NORMAL:
                        logbook.null())
    monkeypatch.setattr(cli, "Workspace",
                        types.SimpleNamespace(here=lambda: ws))
    return engine


def main(*argv):
    return asyncio.run(cli._main(list(argv)))


def test_a_first_round_writes_the_three_sections_and_comments_the_round(
        hub, ws, refined):
    number = task(hub)
    assert main(str(number)) == 0
    assert refined.ran == ["explore", "business-goal", "technical",
                           "acceptance-criteria", "coherence"]
    assert hub.body_of(number) == (
        "## Business Goal\n\nle business-goal\n\n"
        "## Technical\n\nle technical\n\n"
        "## Acceptance Criteria\n\nle acceptance-criteria\n")
    assert hub.comments[number] == ["refinement round: 1"]
    assert labels.REFINEMENT not in hub.labels_of(number)
    assert labels.SPEC_WRITTEN not in hub.labels_of(number)
    # Le garde-fou du test du dry-run juste en dessous : sans ca, un `wrote()`
    # qui ne verrait jamais rien le ferait passer pour toujours.
    assert hub.wrote(), "le double ne voit plus aucune ecriture"


def test_a_second_round_buys_only_its_own_two_sections(hub, ws, refined):
    number = task(hub, body=ROUND_ONE_BODY)
    hub.comment(number, "refinement round: 1")
    assert main(str(number)) == 0
    assert refined.ran == ["explore", "business-rules", "technical-plan",
                           "coherence"]
    assert hub.body_of(number).startswith(ROUND_ONE_BODY)
    assert labels.SPEC_WRITTEN in hub.labels_of(number)


def test_a_scripted_coherence_retouch_reaches_the_published_body(hub, ws,
                                                                  refined):
    number = task(hub)
    refined.script["coherence"] = (
        "## Business Goal\n\nle business-goal, retouche.\n\n"
        "## Technical\n\nle technical\n\n"
        "## Acceptance Criteria\n\nle acceptance-criteria\n")
    assert main(str(number)) == 0
    assert hub.body_of(number) == refined.script["coherence"]


def test_a_coherence_pass_that_drops_a_section_still_publishes(hub, ws,
                                                                refined):
    """La session de coherence rate, mais les trois sections payees ne sont
    pas perdues pour autant : le round publie le simple merge."""
    number = task(hub)
    refined.script["coherence"] = "n'importe quoi, sans titres reconnus"
    assert main(str(number)) == 0
    assert hub.body_of(number) == (
        "## Business Goal\n\nle business-goal\n\n"
        "## Technical\n\nle technical\n\n"
        "## Acceptance Criteria\n\nle acceptance-criteria\n")


def test_a_dry_run_writes_nothing_on_github_and_pays_for_nothing(hub, ws,
                                                                  refined):
    """Le seul essai qu'un humain fait avant de lancer cinq sessions opus."""
    number = task(hub)
    hub.comment(number, "refinement round: 1")
    before = hub.body_of(number)
    assert main(str(number), "--dry-run") == 0
    assert refined.ran == [], "une session a ete payee en dry-run"
    assert hub.wrote() == [], "un dry-run a ecrit sur GitHub"
    assert hub.body_of(number) == before
    assert hub.comments[number] == ["refinement round: 1"]
    assert labels.REFINEMENT in hub.labels_of(number)


def test_a_dry_run_writes_the_prompt_of_each_stage_it_would_have_run(hub, ws,
                                                                     refined):
    number = task(hub)
    assert main(str(number), "--dry-run") == 0
    written = sorted(p.name for p in (ws.refinement_dir / str(number)).glob("*"))
    assert written == ["r01-acceptance-criteria.log", "r01-business-goal.log",
                       "r01-coherence.log", "r01-explore.log",
                       "r01-technical.log"]


def test_explore_gives_every_section_the_repository_back(hub, ws, refined):
    """L'echappatoire, de bout en bout : aucune session d'exploration, et les
    sections sont dites qu'elles n'ont pas de carte."""
    number = task(hub)
    assert main(str(number), "--explore") == 0
    assert refined.ran == ["business-goal", "technical", "acceptance-criteria",
                           "coherence"]


def test_the_map_reaches_every_section_that_the_round_pays_for(hub, ws,
                                                               refined):
    """Ce que l'exploration a rendu est ce que les sections lisent."""
    refined.script["explore"] = "### Constraints\njamais de push sur main"
    number = task(hub)
    assert main(str(number)) == 0
    paid = [p for p in refined.prompts if "You are establishing" not in p]
    assert len(paid) == 4
    assert all("jamais de push sur main" in p for p in paid)


def test_a_round_whose_exploration_fails_pays_for_no_section(hub, ws,
                                                             refined):
    """Les sections ont ete reglees pour travailler sur une carte."""
    refined.fails_on = "explore"
    number = task(hub)
    assert main(str(number)) == 2
    assert refined.ran == ["explore"]
    assert hub.wrote() == [], "un round sans carte a quand meme ecrit"


def test_a_second_refinement_of_the_same_issue_does_not_start(hub, ws, refined):
    number = task(hub)
    (ws.refinement_dir / f".lock-{number}").mkdir(parents=True)
    assert main(str(number)) == 0
    assert refined.ran == [] and hub.wrote() == []


def test_a_round_the_router_drives_writes_only_what_it_named(hub, ws, refined):
    number = task(hub, body=ROUND_ONE_BODY)
    for n in (1, 2):
        hub.comment(number, f"refinement round: {n}")
    refined.script["router"] = "acceptance-criteria"
    assert main(str(number), "--context", "revois les criteres") == 0
    assert refined.ran == ["explore", "router", "acceptance-criteria",
                           "coherence"]
    assert hub.body_of(number) == (
        "## Business Goal\n\nLe but.\n\n"
        "## Technical\n\nLa technique.\n\n"
        "## Acceptance Criteria\n\nle acceptance-criteria\n")


def test_a_router_that_named_no_section_stops_before_paying_for_anything(
        hub, ws, refined):
    """Un round muet coute une session et n'ecrit rien : il doit se dire."""
    number = task(hub, body=ROUND_ONE_BODY)
    for n in (1, 2):
        hub.comment(number, f"refinement round: {n}")
    refined.script["router"] = "je ne sais pas"
    assert main(str(number), "--context", "revois tout") == 2
    assert refined.ran == ["explore", "router"]
    assert hub.wrote() == []


def test_a_late_round_without_a_context_rewrites_the_five_sections(hub, ws,
                                                                   refined):
    number = task(hub, body=ROUND_ONE_BODY)
    for n in (1, 2):
        hub.comment(number, f"refinement round: {n}")
    assert main(str(number)) == 0
    assert refined.ran == ["explore", "business-goal", "technical",
                           "acceptance-criteria",
                           "business-rules", "technical-plan", "coherence"]
    assert hub.comments[number][-1] == "refinement round: 3"


def test_a_refusal_costs_nothing_and_leaves_the_issue_alone(hub, ws, refined):
    number = hub.add("Une task", labels.AGENT, body=RAW)
    assert main(str(number)) == 1
    assert refined.ran == [] and hub.wrote() == []


def test_each_session_of_a_round_books_its_cost_under_the_round(hub, ws,
                                                                refined):
    """Sans le round et l'issue sur la ligne, le registre ne se lit plus."""
    from pipeline.core.adapters.store import ledger

    number = task(hub, body=ROUND_ONE_BODY)
    hub.comment(number, "refinement round: 1")
    assert main(str(number)) == 0
    rows = [l.split("\t") for l in
            ws.refinement_ledger.read_text(encoding="utf-8").splitlines()[1:]]
    assert [r[ledger.STAGE] for r in rows] == ["explore", "business-rules",
                                               "technical-plan", "coherence"]
    assert {r[ledger.ROUND] for r in rows} == {"02"}
    assert {r[ledger.TASK] for r in rows} == {f"#{number}"}
    assert {r[ledger.OUTCOME] for r in rows} == {"ok"}


def test_a_label_that_could_not_be_written_leaves_the_counter_unposted(hub,
                                                                       ws):
    """Le compteur dit que le round a eu lieu : pose trop tot, la reprise
    repart au round suivant — cinq sessions la ou il en fallait deux."""
    number = task(hub)
    hub.fails_on = f"issues/{number}/labels"
    got, _ = write(hub, ws, number, wanted=("business-goal",),
                   results={"business-goal": "Le but."})
    assert got.failed
    assert hub.comments.get(number, []) == []
