"""The round graph: the order of the stages, the skips, and where it stops.

These tests never talk to Claude and never talk to GitHub: `session.run` is
replaced by a recorder, and the issue store is the double from
`fake_github`. They defend the sequence — business-analyst, code, create-test
— and the conditions that cut it short.

Two of those conditions used to be files and are now issues, and the tests
that covered them were ported rather than dropped: the human gate is a
dependency in `blocked_by`, and the archive stage is GitHub closing the issue
when `/code`'s PR merges with `Closes #N`.
"""

import asyncio
import re
import io
import types

import pytest
from conftest import milestone

from pipeline.workflows.agentic_dev_loop import stages as table
from pipeline.workflows.agentic_dev_loop.internals import tasks
from pipeline.core.execution import session
from pipeline.workflows.agentic_dev_loop.internals import board
from pipeline.workflows.common.utils import hub as adapters
from pipeline.workflows.agentic_dev_loop.internals import flow as flow_mod
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.core.domain.outcomes.result import Result


@pytest.fixture
def repo(hub):
    """Un milestone, une task prete, et un SPEC deja dans le corps de l'issue."""
    number, numbers = milestone(hub, ready=(0,), tasks=("La task en cours",),
                                title="Le milestone en cours")
    return types.SimpleNamespace(hub=hub, milestone=number, task=numbers[0])


@pytest.fixture
def calls(repo, monkeypatch):
    """Enregistre les stages lances, et simule ce qu'ils produisent.

    `/code` ferme l'issue : c'est ce que GitHub fait quand sa PR merge avec
    `Closes #N`, et la post-condition du round le constate.
    """
    seen = []

    async def fake_run(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        seen.append(stage.skill)
        if stage.skill == "code":
            repo.hub.close(repo.task)
        return Result.of(session.StageResult(
            text="AGENT_LOOP_OK: fait", cost=0.0, session_id="s",
            ok_line="AGENT_LOOP_OK: fait", stop_line=None))

    monkeypatch.setattr(session, "run", fake_run)
    return seen


@pytest.fixture
def prompts_seen(repo, monkeypatch):
    """Le texte `extra` que chaque stage a recu — la portee injectee."""
    seen = {}

    async def fake_run(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        seen[stage.skill] = extra
        if stage.skill == "code":
            repo.hub.close(repo.task)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", fake_run)
    return seen


def rollover(spec):
    """Une config dont la table enchaine sur ce stage de rollover."""
    return RunConfig(max_rounds=1, rollover=spec)


def halted(tmp_path, cfg=None, resuming=False):
    """L'arret qu'un round a enregistre — vide s'il est alle au bout.

    Un noeud qui s'arrete ne leve plus : il l'ecrit dans l'etat, que le
    moteur persiste, et c'est la que la boucle le relit apres le kickoff.
    """
    return kick(tmp_path, cfg, resuming).state.halt


def kick(tmp_path, cfg=None, resuming=False):
    """Un round. `resuming=True` monte la forme d'un round repris."""
    cfg = cfg or RunConfig(max_rounds=1)
    ctx = flow_mod.RoundCtx(cfg=cfg, log=logbook.null(), log_dir=tmp_path,
                        round_no=1, workspace=Workspace(tmp_path))
    if resuming:
        here = board.read(adapters.gh(ctx.workspace)).value
        here.resuming = here.next
        ctx.board = here
    flow = flow_mod.build_flow(ctx)()
    asyncio.run(flow.kickoff_async())
    return flow


def test_the_stages_run_in_the_documented_order(tmp_path, calls):
    kick(tmp_path)
    assert calls == ["business-analyst", "code", "create-test"]


def test_the_spec_written_label_skips_the_business_analyst(tmp_path, repo, calls):
    """Ce que la presence de `docs/current/SPEC.md` disait avant lui."""
    repo.hub.issues[repo.task]["labels"].append({"name": tasks.SPEC_WRITTEN})
    kick(tmp_path)
    assert calls == ["code", "create-test"]


def test_the_analyst_stage_sets_the_label_it_will_be_resumed_by(tmp_path, repo,
                                                                calls):
    kick(tmp_path)
    assert tasks.SPEC_WRITTEN in repo.hub.labels_of(repo.task)


def test_an_analyst_that_writes_no_spec_stops_the_round(tmp_path, repo,
                                                        monkeypatch):
    """Le corps de l'issue *est* le SPEC : vide, /code n'a rien a construire."""
    repo.hub.issues[repo.task]["body"] = ""

    async def writes_nothing(stage, cfg, **kw):
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", writes_nothing)
    got = halted(tmp_path)
    assert got.failed and re.search("empty body", got.reason)


def test_the_code_stage_refuses_to_start_on_an_empty_issue(tmp_path, repo,
                                                           calls):
    """Une session ne demarre jamais sans sa portee."""
    repo.hub.issues[repo.task]["body"] = ""
    repo.hub.issues[repo.task]["labels"].append({"name": tasks.SPEC_WRITTEN})
    got = halted(tmp_path)
    assert got.failed and re.search("no SPEC to build from", got.reason)
    assert calls == []


def test_an_open_human_dependency_means_the_task_is_never_picked(tmp_path, repo,
                                                                 calls):
    """La porte humaine, devenue une dependance : plus de barriere a placer.

    Elle tombait autrefois entre le business-analyst et le code — donc apres
    une session payee. Une task bloquee n'est simplement plus choisie.
    """
    human = repo.hub.add("Creer le projet", tasks.HUMAN)
    repo.hub.link(repo.milestone, human)
    repo.hub.block(repo.task, human)
    got = halted(tmp_path)
    assert got.failed and re.search("none can run", got.reason)
    assert calls == []


def test_the_dependency_check_does_not_depend_on_which_stages_run(tmp_path,
                                                                  repo, calls):
    """Revue du 2026-09-09, finding n°5, reporte.

    La barriere d'avant devait savoir s'il restait un stage de construction a
    proteger. Le choix de la task ne le demande plus : bloquee est bloquee,
    quel que soit `--stages`.
    """
    human = repo.hub.add("Creer le projet", tasks.HUMAN)
    repo.hub.block(repo.task, human)
    repo.hub.link(repo.milestone, human)
    for stages in ("business-analyst", "business-analyst code"):
        got = halted(tmp_path, RunConfig(stages=stages))
        assert got.failed and re.search("none can run", got.reason)
    assert calls == []


def test_a_closed_human_dependency_lets_the_task_through(tmp_path, repo, calls):
    human = repo.hub.add("Creer le projet", tasks.HUMAN, state="closed")
    repo.hub.link(repo.milestone, human)
    repo.hub.block(repo.task, human)
    kick(tmp_path)
    assert calls == ["business-analyst", "code", "create-test"]


def test_a_task_without_the_ready_label_stops_the_run(tmp_path, repo, calls):
    """Regle 4 : et surtout, ce n'est pas un rollover."""
    repo.hub.issues[repo.task]["labels"] = [{"name": tasks.AGENT}]
    got = halted(tmp_path)
    assert got.failed and re.search(f"Add {tasks.READY}", got.reason)
    assert calls == []


def test_an_unreadable_board_stops_rather_than_reading_as_nothing_to_do(
        tmp_path, repo, calls):
    """La lecture degradee qui declencherait un `/planner` a plusieurs dollars."""
    repo.hub.fails_on = "sub_issues"
    got = halted(tmp_path)
    assert got.failed and re.search("what is left to do is unknown", got.reason)
    assert calls == []


def test_every_task_closed_stops_by_default(tmp_path, repo, calls):
    """With no ROLLOVER configured the loop stops — it spends nothing."""
    repo.hub.close(repo.task)
    flow = kick(tmp_path)
    assert calls == []
    assert flow.state.rollover


def test_a_configured_rollover_opens_the_next_roadmap_item(tmp_path, repo,
                                                           calls, monkeypatch):
    repo.hub.close(repo.task)

    async def planner_opens_a_task(stage, cfg, **kw):
        calls.append(stage.skill)
        opened = repo.hub.add("Une nouvelle task", tasks.AGENT)
        repo.hub.link(repo.milestone, opened)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", planner_opens_a_task)
    flow = kick(tmp_path, rollover(StageSpec("planner", "opus", "high")))
    assert calls == ["planner"]
    assert flow.state.rollover


def test_the_planner_must_open_a_task(tmp_path, repo, monkeypatch):
    repo.hub.close(repo.task)

    async def noop(stage, cfg, **kw):
        return Result.of(session.StageResult("", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", noop)
    got = halted(tmp_path, rollover(StageSpec("planner", "opus", "high")))
    assert got.failed and re.search("left nothing to pick up", got.reason)


def test_a_planner_that_forgets_to_close_the_old_milestone_is_named(
        tmp_path, repo, monkeypatch):
    """Le piege du rollover : la boucle lit le milestone ouvert de plus petit
    numero, donc un ancien laisse ouvert fait rouler tous les rounds a vide.
    """
    repo.hub.close(repo.task)

    async def opens_a_second_milestone(stage, cfg, **kw):
        later = repo.hub.add("Le milestone suivant", tasks.MILESTONE)
        repo.hub.link(later, repo.hub.add("Une task", tasks.AGENT))
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", opens_a_second_milestone)
    planner = rollover(StageSpec("planner", "opus", "high"))
    got = halted(tmp_path, planner)
    assert got.failed and re.search("did not close milestone", got.reason)

    # Une fois l'ancien ferme, le tableau bascule sur le nouveau — qui
    # attend une case `pipeline:ready`, puisque le planner n'en pose aucune.
    repo.hub.close(repo.milestone)
    got = halted(tmp_path, planner)
    assert got.failed and re.search(f"Add {tasks.READY}", got.reason)


def test_a_stage_that_stops_halts_the_round(tmp_path, repo, monkeypatch):
    async def stopper(stage, cfg, **kw):
        return Result.of(session.StageResult(
            "AGENT_LOOP_STOP: ambigu", 0.0, "s", None,
            "AGENT_LOOP_STOP: ambigu"))

    monkeypatch.setattr(session, "run", stopper)
    got = halted(tmp_path)
    assert got.failed and re.search("AGENT_LOOP_STOP: ambigu", got.reason)


def test_a_stage_that_stops_pays_for_none_of_the_stages_after_it(
        tmp_path, repo, calls, monkeypatch):
    """La garde de chaque noeud, et ce qu'elle coute si on l'oublie.

    Depuis que les arrets sont des `Result`, un noeud qui rend un echec
    n'arrete rien tout seul : le moteur declenche le suivant des que le
    precedent rend la main. Sans `if self.state.stopped: return`, un `/code`
    qui s'arrete laisserait partir `/create-test` — une session payante de
    plus, sur une task qu'on vient justement de renoncer a livrer.
    """
    async def stops_on_code(stage, cfg, **kw):
        calls.append(stage.skill)
        if stage.skill == "code":
            return Result.of(session.StageResult(
                "AGENT_LOOP_STOP: le SPEC est ambigu", 0.0, "s", None,
                "AGENT_LOOP_STOP: le SPEC est ambigu"))
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    calls.clear()
    monkeypatch.setattr(session, "run", stops_on_code)
    got = halted(tmp_path)
    assert got.failed and "le SPEC est ambigu" in got.reason
    assert calls == ["business-analyst", "code"], (
        "un stage a ete paye apres l'arret")


def test_a_round_that_stops_before_choosing_runs_no_stage_at_all(
        tmp_path, repo, calls):
    """L'autre moitie de la garde : la branche « stop » du routeur.

    Un tableau qu'on ne peut pas lire arrete le round au premier noeud. Aucun
    noeud n'ecoute « stop », donc le graphe s'arrete la — au lieu d'enchainer
    sur `/business-analyst` avec un etat vide.
    """
    repo.hub.fails_on = "sub_issues"
    got = halted(tmp_path)
    assert got.failed and "what is left to do is unknown" in got.reason
    assert calls == []


def test_a_round_that_leaves_the_issue_open_stops_rather_than_looping(
        tmp_path, repo, monkeypatch):
    """Ce que la post-condition d'archivage disait : la task doit se fermer.

    Personne ici ne la ferme — c'est GitHub, au merge d'une PR portant
    `Closes #N`. Ne pas le constater ferait rejouer la meme task au round
    suivant, en repayant chaque stage.
    """
    async def merges_nothing(stage, cfg, **kw):
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", merges_nothing)
    got = halted(tmp_path)
    assert got.failed and re.search("nothing marks it delivered", got.reason)


def test_stages_without_code_report_that_nothing_can_close_the_task(
        tmp_path, repo, calls):
    """`--stages create-test` ne ferme rien : le dire, plutot que boucler."""
    got = halted(tmp_path, RunConfig(stages="create-test"))
    assert got.failed and "left /code out" in got.reason
    assert calls == ["create-test"]


def test_stage_filter_runs_only_what_was_asked(tmp_path, calls):
    kick(tmp_path, RunConfig(stages="code create-test"))
    assert calls == ["code", "create-test"]


def test_a_dry_run_marks_no_stage_as_done(tmp_path, calls):
    flow = kick(tmp_path, RunConfig(dry_run=True))
    assert flow.state.stages_done == []


def test_a_real_run_records_every_stage_for_resume(tmp_path, calls):
    flow = kick(tmp_path)
    assert flow.state.stages_done == ["business-analyst", "code", "create-test"]


def test_the_task_identity_is_carried_into_the_state(tmp_path, repo, calls):
    flow = kick(tmp_path)
    assert flow.state.task_num == str(repo.task)
    assert flow.state.task_key == str(repo.task)
    assert flow.state.task_title == "La task en cours"
    assert flow.state.milestone_num == str(repo.milestone)


def test_every_stage_is_handed_the_milestone_and_the_issue(tmp_path, repo,
                                                           prompts_seen):
    """Regle d'injection : une session ne demarre jamais sans sa portee.

    Y compris `/create-test`, qui n'a aucune consigne a lui et serait sinon
    la seule session payee du round a ignorer sur quoi elle travaille.
    """
    kick(tmp_path)
    assert set(prompts_seen) == {"business-analyst", "code", "create-test"}
    for skill, extra in prompts_seen.items():
        assert "--- SCOPE" in extra, skill
        assert f"MILESTONE #{repo.milestone} — Le milestone en cours" in extra
        assert f"ISSUE #{repo.task} — La task en cours" in extra
        assert "Le corps du milestone" in extra
        assert "le SPEC de La task en cours" in extra


def test_the_code_prompt_asks_for_the_line_that_closes_the_issue(
        tmp_path, repo, prompts_seen):
    kick(tmp_path)
    assert f"Closes #{repo.task}" in prompts_seen["code"]


def test_the_analyst_prompt_names_the_issue_it_must_write_into(
        tmp_path, repo, prompts_seen):
    kick(tmp_path)
    said = prompts_seen["business-analyst"]
    assert f"issue #{repo.task}" in said
    assert f"milestone #{repo.milestone}" in said


def test_the_crewai_panels_are_silenced(tmp_path, calls, monkeypatch):
    """One ASCII frame per method would drown the journal we re-read later."""
    import crewai_core.printer as printer
    seen = []
    monkeypatch.setattr(printer, "set_suppress_console_output",
                        lambda v: seen.append(v))
    monkeypatch.delenv("PIPELINE_CREWAI_PANELS", raising=False)
    kick(tmp_path)
    assert seen == [True]


def test_the_panels_can_be_put_back_for_debugging(tmp_path, calls, monkeypatch):
    import crewai_core.printer as printer
    seen = []
    monkeypatch.setattr(printer, "set_suppress_console_output",
                        lambda v: seen.append(v))
    monkeypatch.setenv("PIPELINE_CREWAI_PANELS", "1")
    kick(tmp_path)
    assert seen == []


def test_every_stage_is_counted_in_the_round_tally(tmp_path, repo, monkeypatch):
    async def measured(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        if stage.skill == "code":
            repo.hub.close(repo.task)
        return Result.of(session.StageResult(
            "ok", 1 / 3, "s", None, None, duration_ms=1000, turns=2,
            usage={"input_tokens": 100, "output_tokens": 10}))

    monkeypatch.setattr(session, "run", measured)
    ctx = flow_mod.RoundCtx(cfg=RunConfig(max_rounds=1), log=logbook.null(),
                        log_dir=tmp_path, round_no=1,
                        workspace=Workspace(tmp_path))
    asyncio.run(flow_mod.build_flow(ctx)().kickoff_async())
    assert ctx.tally.stages == 3
    assert ctx.tally.cost == pytest.approx(1.0)
    assert set(ctx.tally.by_stage) == {"business-analyst", "code",
                                       "create-test"}


def test_a_filtered_stage_says_so_instead_of_vanishing(tmp_path, repo, calls):
    """A5: `--stages code` said nothing about the stages it dropped."""
    said = io.StringIO()
    log = logbook.open_logbook("test.flow.skips", stream=said)
    ctx = flow_mod.RoundCtx(cfg=RunConfig(stages="code"), log=log,
                        log_dir=tmp_path, round_no=1,
                        workspace=Workspace(tmp_path))
    asyncio.run(flow_mod.build_flow(ctx)().kickoff_async())
    skipped = [l for l in said.getvalue().splitlines() if "skipped" in l]
    assert any("business-analyst" in l for l in skipped)
    assert any("create-test" in l for l in skipped)


def test_a_stage_missing_from_the_pipeline_says_which_one(tmp_path, calls,
                                                          monkeypatch):
    """D2 : `next()` sans defaut levait une `StopIteration` nue, en async."""
    without_code = tuple(s for s in table.PIPELINE if s.skill != "code")
    got = halted(tmp_path, RunConfig(max_rounds=1, pipeline=without_code))
    assert got.failed and re.search("PIPELINE has no 'code' entry", got.reason)


def test_a_merged_pr_closing_the_issue_closes_it_when_github_did_not(
        tmp_path, repo, monkeypatch):
    """Le cas reel : la PR merge dans `main_agent`, pas dans la branche par
    defaut, donc GitHub ne ferme rien malgre le `Closes #N`.

    Sans ce rattrapage la post-condition arreterait le run a la fin de
    **chaque** round, apres avoir paye les trois stages.
    """
    async def merges_a_pr(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        if stage.skill == "code":
            repo.hub.add_pr("feat: la task", body=f"Closes #{repo.task}",
                            base="main_agent", merged=True)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", merges_a_pr)
    kick(tmp_path)
    assert tasks.WAITING_MERGE in repo.hub.labels_of(repo.task)
    assert repo.hub.issues[repo.task]["state"] == "open", (
        "l'issue reste ouverte : la fermer dirait que c'est integre dans main")


def test_a_pr_merged_on_another_branch_does_not_close_the_task(
        tmp_path, repo, monkeypatch):
    """Le rattrapage suit `INTEGRATION_BRANCH`, il ne ferme pas sur parole."""
    async def merges_elsewhere(stage, cfg, *, round_no, task, extra="",
                               log_dir, log, runner=None):
        if stage.skill == "code":
            repo.hub.add_pr("feat: ailleurs", body=f"Closes #{repo.task}",
                            base="une-autre-branche", merged=True)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", merges_elsewhere)
    got = halted(tmp_path)
    assert got.failed and re.search("nothing marks it delivered", got.reason)
    assert tasks.WAITING_MERGE not in repo.hub.labels_of(repo.task)


def test_an_unmerged_pr_does_not_close_the_task(tmp_path, repo, monkeypatch):
    """Une PR ouverte ou abandonnee n'a rien livre."""
    async def opens_a_pr(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        if stage.skill == "code":
            repo.hub.add_pr("feat: pas encore", body=f"Closes #{repo.task}",
                            base="main_agent", merged=False)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", opens_a_pr)
    got = halted(tmp_path)
    assert got.failed and re.search("nothing marks it delivered", got.reason)
    assert tasks.WAITING_MERGE not in repo.hub.labels_of(repo.task)


def test_an_issue_github_already_closed_costs_no_pull_request_lookup(
        tmp_path, repo, calls):
    """Le chemin nominal si la branche d'integration devient la branche par
    defaut : rien a rattraper, donc rien a lire."""
    kick(tmp_path)
    assert not [c for c in repo.hub.calls if "pulls" in " ".join(c)]


def test_a_task_already_waiting_merge_is_left_alone(tmp_path, repo,
                                                    monkeypatch):
    """Un round repris ne repose pas l'etiquette et ne cherche pas la PR.

    L'etiquette apparait pendant le round, pas avant : c'est la forme d'une
    reprise, ou un round precedent l'avait deja posee. Posee avant, la task
    ne serait plus choisie du tout et le round s'arreterait sur `stuck()`.
    """
    async def labels_it_itself(stage, cfg, *, round_no, task, extra="",
                               log_dir, log, runner=None):
        if stage.skill == "code":
            repo.hub.issues[repo.task]["labels"].append(
                {"name": tasks.WAITING_MERGE})
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", labels_it_itself)
    kick(tmp_path)
    assert not [c for c in repo.hub.calls if "pulls" in " ".join(c)]
    assert repo.hub.labels_of(repo.task).count(tasks.WAITING_MERGE) == 1


def test_a_round_runs_the_table_it_is_given_rather_than_the_packages(
        tmp_path, repo, monkeypatch):
    """La table est une donnee de la config : aucun monkeypatch pour la changer.

    Le graphe et la table doivent nommer les memes stages — `_spec` leve
    sinon — donc ce qu'une table injectee change ici est le modele et
    l'effort avec lesquels chaque stage part.
    """
    seen: dict[str, str] = {}

    async def fake(stage, cfg, *, round_no, task, extra="", log_dir, log,
                   runner=None):
        seen[stage.skill] = f"{stage.model}/{stage.effort}"
        if stage.skill == "code":
            repo.hub.add_pr("feat: la task", body=f"Closes #{repo.task}",
                            base="main_agent", merged=True)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", fake)
    mine = tuple(StageSpec(s.skill, "haiku", "low", s.lead)
                 for s in table.PIPELINE)
    kick(tmp_path, RunConfig(max_rounds=1, pipeline=mine))

    assert seen == {"business-analyst": "haiku/low", "code": "haiku/low",
                    "create-test": "haiku/low"}
    # La table du paquet n'a pas ete touchee pour autant.
    assert [f"{s.model}/{s.effort}" for s in table.PIPELINE] == [
        "opus/high", "opus/high", "sonnet/high"]


def test_a_code_stage_whose_pr_already_merged_is_not_paid_again(
        tmp_path, repo, calls):
    """Le cas du quota : /code merge sa PR, puis la session meurt.

    `stages_done` n'est allonge qu'au retour de la session, donc rien ne
    marque le stage fait — et le run suivant repayait un opus/high pour une
    task dont la PR est deja sur la branche d'integration.
    """
    repo.hub.add_pr("feat: la task", body=f"Closes #{repo.task}",
                    base="main_agent", merged=True)
    kick(tmp_path, resuming=True)
    assert calls == ["business-analyst", "create-test"]


def test_a_fresh_round_costs_no_pull_request_lookup_before_code(
        tmp_path, repo, calls):
    """Sur un round neuf /code n'a jamais tourne : rien a verifier."""
    kick(tmp_path)
    assert calls == ["business-analyst", "code", "create-test"]
    assert not [c for c in repo.hub.calls if "pulls" in " ".join(c)]


def test_restart_replays_a_code_stage_even_once_its_pr_merged(
        tmp_path, repo, calls):
    """Sinon on ne pourrait plus rejouer une task deliberement."""
    repo.hub.add_pr("feat: la task", body=f"Closes #{repo.task}",
                    base="main_agent", merged=True)
    kick(tmp_path, RunConfig(max_rounds=1, restart=True,
                             workspace=Workspace(tmp_path)), resuming=True)
    assert "code" in calls
