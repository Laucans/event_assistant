"""The command line: the rounds, the state, and the fast path."""

import asyncio
import subprocess
import sys
import types

import pytest
from conftest import milestone

from pipeline.core.adapters.store import resume
from pipeline.core.execution import session
from pipeline.workflows.agentic_dev_loop.internals import loop as workflow_loop
from pipeline.core.execution.contract.outcome import WorkflowOutcome
from pipeline.launcher.cli import agentic_dev_loop as loop
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.workflows.agentic_dev_loop.settings import RunConfig
from pipeline.core.domain.outcomes.result import Result

ROOT = Workspace.here().root


@pytest.fixture
def env(tmp_path, hub):
    """Un milestone avec une task prete, et un disque a nous.

    Le milestone etait un fichier markdown ecrit dans `tmp_path` ; c'est
    maintenant une issue dans le double de GitHub. Ce qui reste sur le
    disque — le pointeur de reprise, la base du moteur, le registre — vit
    dans le workspace que la config porte.
    """
    number, numbers = milestone(hub, ready=(0,), tasks=("La task en cours",))
    return types.SimpleNamespace(hub=hub, milestone=number, task=numbers[0],
                                 dir=tmp_path, ws=Workspace(tmp_path))


def config(env, **kw):
    """La config d'un round de test : son workspace est celui de `env`."""
    kw.setdefault("max_rounds", 1)
    kw.setdefault("run_id", "test")
    return RunConfig(workspace=env.ws, **kw)


@pytest.fixture
def stages(env, monkeypatch):
    """Les stages, sur papier. `/code` ferme l'issue, comme un merge le fait."""
    seen = []

    async def fake(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        seen.append((round_no, stage.skill))
        if stage.skill == "code":
            env.hub.close(env.task)
        return Result.of(session.StageResult(
            "AGENT_LOOP_OK: ok", 0.0, "s", "AGENT_LOOP_OK: ok", None))

    monkeypatch.setattr(session, "run", fake)
    return seen


def test_a_round_closes_the_task_and_clears_the_resume_point(env, stages):
    cfg = config(env)
    asyncio.run(workflow_loop.one_round(cfg, 1, logbook.null(), env.dir))
    assert [s for _, s in stages] == ["business-analyst", "code",
                                      "create-test"]
    assert resume.read_pointer(env.ws.state) == (None, None)
    assert env.hub.issues[env.task]["state"] == "closed"


def test_a_halt_leaves_a_resume_point_behind(env, monkeypatch):
    async def stops(stage, cfg, **kw):
        return Result.of(session.StageResult(
            "AGENT_LOOP_STOP: ambigu", 0.0, "s", None,
            "AGENT_LOOP_STOP: ambigu"))

    monkeypatch.setattr(session, "run", stops)
    cfg = config(env)
    assert asyncio.run(
        workflow_loop.one_round(cfg, 1, logbook.null(), env.dir)).failed
    task, flow_id = resume.read_pointer(env.ws.state)
    assert task == str(env.task) and flow_id


def test_the_round_number_becomes_the_ledger_step(env, stages):
    cfg = config(env)
    asyncio.run(workflow_loop.one_round(cfg, 3, logbook.null(), env.dir))
    assert {round_no for round_no, _ in stages} == {3}


def test_a_dry_run_never_writes_the_resume_point(env, stages):
    cfg = config(env, dry_run=True)
    asyncio.run(workflow_loop.one_round(cfg, 1, logbook.null(), env.dir))
    assert not env.ws.state.exists()


# --- la commande de bascule ------------------------------------------------


@pytest.fixture
def migrate_calls(monkeypatch):
    """`migrate.run` sur papier : la commande ne doit rien ecrire ici."""
    from pipeline.workflows.legacy import migrate

    seen = []

    def fake(*, dry_run, workspace):
        seen.append(dry_run)
        return Result.of("ce que la migration dirait")

    monkeypatch.setattr(migrate, "run", fake)
    return seen


def test_migrate_is_a_command_of_its_own_and_prints_what_it_did(
        migrate_calls, capsys):
    assert loop.main(["migrate"]) == 0
    assert migrate_calls == [False]
    assert "ce que la migration dirait" in capsys.readouterr().out


def test_migrate_passes_the_dry_run_flag_through(migrate_calls):
    assert loop.main(["migrate", "--dry-run"]) == 0
    assert migrate_calls == [True]


def test_a_migration_that_stops_says_so_on_stderr_with_its_own_code(
        monkeypatch, capsys):
    """Avant le journal : il n'y a pas de run.log ou ecrire."""
    from pipeline.workflows.legacy import migrate

    def refuses(*, dry_run, workspace):
        return Result.halt("docs/ROADMAP.md is missing")

    monkeypatch.setattr(migrate, "run", refuses)
    assert loop.main(["migrate", "--dry-run"]) == 1
    assert "STOP — docs/ROADMAP.md is missing" in capsys.readouterr().err


def test_the_help_names_the_migrate_command(capsys):
    with pytest.raises(SystemExit):
        loop.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "migrate" in out and "--dry-run first" in out


def test_build_config_reads_the_flags():
    cfg = loop.build_config(loop.parse_args(
        ["--rounds", "7", "--stages", "code", "--branch", "b",
         "--model", "sonnet", "--effort", "low", "--dry-run", "--restart"]))
    assert (cfg.max_rounds, cfg.stages, cfg.integration_branch) == (7, "code", "b")
    assert (cfg.model, cfg.effort, cfg.dry_run, cfg.restart) == (
        "sonnet", "low", True, True)
    assert cfg.run_id


def test_defaults_match_the_shell():
    cfg = loop.build_config(loop.parse_args([]))
    assert cfg.max_rounds == 3
    assert cfg.integration_branch == "main_agent"
    assert cfg.permission_mode == "bypassPermissions"
    assert not cfg.allow_dirty


def test_both_entry_points_resolve_the_workspace_the_run_works_against():
    """Le point d'entree resout la racine ; la config la porte pour la suite."""
    from pipeline.launcher.cli import pr_review as review

    cfg = loop.build_config(loop.parse_args([]))
    assert cfg.workspace.root == ROOT
    assert cfg.workspace.ledger == ROOT / ".llocal/agent-loop/costs.tsv"
    assert cfg.workspace.skills == ROOT / ".claude/skills"

    rcfg = review.build_config(review.parse_args(["12"]))
    assert rcfg.workspace.root == ROOT
    assert rcfg.workspace.review_ledger == ROOT / ".llocal/pr-review/costs.tsv"


FAST_PATH = """
import sys
sys.argv = ["agent-loop", "%s"]
from pipeline.launcher.cli import agentic_dev_loop as loop
loop.main()
assert "claude_agent_sdk" not in sys.modules, "le chemin rapide a importe le SDK"
print("FAST-OK")
"""


@pytest.mark.parametrize("flag", ["--status", "--costs"])
def test_the_fast_paths_never_import_the_sdk(flag):
    r = subprocess.run([sys.executable, "-c", FAST_PATH % flag],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert "FAST-OK" in r.stdout, r.stderr


def test_the_api_key_is_dropped_at_import():
    r = subprocess.run(
        [sys.executable, "-c",
         "import os; from pipeline.launcher.cli import agentic_dev_loop;"
         " print(os.environ.get('ANTHROPIC_API_KEY'))"],
        capture_output=True, text=True, cwd=str(ROOT),
        env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "sk-ne-doit-pas-survivre",
             "PYTHONPATH": str(ROOT / "pipeline" / "src")})
    assert r.stdout.strip() == "None", r.stderr


def test_a_resumed_round_skips_the_stages_already_done(env, monkeypatch):
    """The invariant the whole state exists for: never re-pay a merged /code.

    Le round s'interrompt apres `/code`, donc **apres** que l'issue s'est
    fermee : plus rien sur le tableau ne l'offrirait, et c'est le pointeur
    de reprise qui la ramene. Sans ca, `/create-test` serait perdu et le
    round suivant repartirait sur une autre task.
    """
    seen = []
    fail_at = {"stage": "create-test"}

    async def fake(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        seen.append(stage.skill)
        if stage.skill == "code":
            env.hub.close(env.task)
        if stage.skill == fail_at["stage"]:
            return Result.halt("panne simulee sur /%s" % stage.skill)
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", fake)
    cfg = config(env)

    # Round 1: everything passes up to the last stage, which breaks.
    stopped = asyncio.run(
        workflow_loop.one_round(cfg, 1, logbook.null(), env.dir))
    assert stopped.failed and "panne simulee" in stopped.reason
    assert seen == ["business-analyst", "code", "create-test"]

    # The @persist store did remember what had been done.
    task, flow_id = resume.read_pointer(env.ws.state)
    assert task == str(env.task)
    assert resume.stages_done(flow_id, env.ws.flow_db).value == [
        "business-analyst", "code"]

    # Round 2: unblock, and nothing already done is run again.
    seen.clear()
    fail_at["stage"] = "jamais"
    asyncio.run(workflow_loop.one_round(cfg, 2, logbook.null(), env.dir))
    assert seen == ["create-test"]
    assert resume.read_pointer(env.ws.state) == (None, None)


def test_a_stale_pointer_to_a_closed_task_is_not_a_round_to_finish(env,
                                                                   stages):
    """Un pointeur survivant sans aucun stage enregistre repayerait tout."""
    env.hub.close(env.task)
    resume.write_pointer(str(env.task), "un-flow-inconnu", env.ws.state)
    cfg = config(env)
    more = asyncio.run(workflow_loop.one_round(cfg, 1, logbook.null(), env.dir))
    assert stages == [], "les trois stages d'une task livree ont ete repayes"
    assert more.ok and more.value is False


def test_restart_replays_the_stages_the_resume_point_had(env, monkeypatch):
    seen = []

    async def fake(stage, cfg, *, round_no, task, extra="", log_dir, log, runner=None):
        seen.append(stage.skill)
        if stage.skill == "create-test":
            return Result.halt("panne")
        return Result.of(session.StageResult("ok", 0.0, "s", None, None))

    monkeypatch.setattr(session, "run", fake)
    assert asyncio.run(workflow_loop.one_round(
        config(env, run_id="t"), 1, logbook.null(), env.dir)).failed
    assert resume.read_pointer(env.ws.state)[0] == str(env.task)

    seen.clear()
    # --restart jette le point de reprise : tout repart, et l'etiquette
    # `pipeline:spec-written` reste le seul motif de sauter l'analyste.
    env.hub.issues[env.task]["labels"] = [
        l for l in env.hub.issues[env.task]["labels"]
        if l["name"] != "pipeline:spec-written"]
    assert asyncio.run(workflow_loop.one_round(
        config(env, run_id="t", restart=True), 2, logbook.null(),
        env.dir)).failed
    assert seen == ["business-analyst", "code", "create-test"]


# --- A2/A3: a clean stop, a failure and a crash no longer look alike ---

@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    """La racine que `main` resout : le repertoire du run tombe dedans.

    Le preflight est neutralise ici : ces tests-la portent sur la traduction
    d'une fin de run en code de sortie, et une porte qui interrogerait le vrai
    `gh` ferait echouer le run avant d'y arriver.
    """
    from pipeline.workflows.agentic_dev_loop import preconditions

    ws = Workspace(tmp_path)
    monkeypatch.setattr(loop, "Workspace",
                        types.SimpleNamespace(here=lambda: ws))
    monkeypatch.setattr(loop, "notify", lambda msg: None)
    monkeypatch.setattr(preconditions.LoopPreconditions, "verify",
                        lambda self: Result.of(None))
    return ws


def raise_in_loop(monkeypatch, exc):
    """Le workflow explose vraiment — le chemin du crash inattendu."""
    async def boom(cfg, log, log_dir):
        raise exc
    monkeypatch.setattr(workflow_loop, "run_rounds", boom)


def stop_in_loop(monkeypatch, outcome):
    """Le workflow s'arrete proprement, et rend pourquoi."""
    async def stops(cfg, log, log_dir):
        return outcome
    monkeypatch.setattr(workflow_loop, "run_rounds", stops)


def only_run_log(run_dir):
    return next(run_dir.loop_dir.glob("*/run.log")).read_text(encoding="utf-8")


@pytest.mark.parametrize("outcome, code, prefix", [
    (WorkflowOutcome.of_result(Result.halt("task 4 needs you first")),
     1, "STOP"),
    (WorkflowOutcome.of_result(Result.fail("/code a echoue")), 2, "FAILED"),
    (WorkflowOutcome.of_result(Result.quota("quota atteint")), 3, "QUOTA"),
])
def test_each_way_of_stopping_has_its_own_code_and_its_own_word(
        run_dir, monkeypatch, outcome, code, prefix):
    """`StageFailed` heritait de `Halt` : les trois sortaient `STOP` et 1.

    Les trois statuts portent desormais le code et le mot, et `main` les lit
    sur le resultat au lieu de les deduire d'un type d'exception.
    """
    stop_in_loop(monkeypatch, outcome)
    assert loop.main(["--rounds", "1"]) == code
    assert prefix in only_run_log(run_dir)


@pytest.mark.parametrize("exc", [
    OSError(28, "No space left on device"),
    ValueError("un interne du SDK"),
    RuntimeError("sqlite3 est parti"),
])
def test_an_unexpected_error_reaches_the_run_log_instead_of_stderr(
        run_dir, monkeypatch, exc):
    """The worst case: the terminal is gone and run.log just stopped."""
    raise_in_loop(monkeypatch, exc)
    assert loop.main(["--rounds", "1"]) == 4
    written = only_run_log(run_dir)
    assert "CRASH" in written
    assert "Traceback (most recent call last):" in written
    assert type(exc).__name__ in written


def test_an_interruption_keeps_its_own_code(run_dir, monkeypatch):
    raise_in_loop(monkeypatch, KeyboardInterrupt())
    assert loop.main(["--rounds", "1"]) == 130


def test_the_help_documents_the_exit_codes(capsys):
    with pytest.raises(SystemExit):
        loop.parse_args(["--help"])
    out = capsys.readouterr().out
    for code in ("0", "1", "2", "3", "4", "130"):
        assert "\n  %s " % code in out or "\n  %-4s" % code in out


def test_the_verbosity_flags_are_read():
    assert loop.build_config(loop.parse_args(["--verbose"])).verbose
    assert loop.build_config(loop.parse_args(["--heartbeat", "5"])).heartbeat_s == 5
    assert not loop.build_config(loop.parse_args([])).verbose


def test_a_resumed_round_stops_rather_than_re_paying_when_the_state_is_unreadable(
        env, stages):
    """D1: an unreadable store used to read as "no stage has run yet"."""
    resume.write_pointer(str(env.task), "f1", env.ws.state)
    env.ws.flow_db.parent.mkdir(parents=True, exist_ok=True)
    env.ws.flow_db.write_text("ce n'est pas une base sqlite", encoding="utf-8")
    cfg = config(env)
    got = asyncio.run(workflow_loop.one_round(cfg, 1, logbook.null(), env.dir))
    assert got.failed and "cannot read the resume state" in got.reason
    assert stages == [], "un stage a ete relance sur un etat illisible"


# --- the knobs nobody finds -----------------------------------------------

SRC = ROOT / "pipeline/src/pipeline"
# Read, but not settings: the loop *clears* them, or sets them for a
# sous-processus.
NOT_A_KNOB = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"}


def env_knobs() -> set[str]:
    """Chaque `os.environ.get("X")` du paquet, hors hooks.

    `rglob`, pas `glob` : le paquet est en sous-dossiers, et un scan plat
    cesserait silencieusement de voir les modules deplaces — un test qui ne
    trouve plus rien passe toujours. `test_the_knob_scan_actually_finds_something`
    est le garde-fou de ce garde-fou.
    """
    import re
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        if "hooks" in path.relative_to(SRC).parts:  # pas des reglages du run
            continue
        # Les deux facons dont le paquet lit l'environnement. En ajouter une
        # troisieme sans l'ajouter ici ferait echouer
        # `test_the_knob_scan_actually_finds_something`, qui nomme MAX_ROUNDS.
        found |= set(re.findall(
            r"(?:os\.environ\.get|_number)\(\"([A-Z][A-Z0-9_]+)\"",
            path.read_text(encoding="utf-8")))
    return found - NOT_A_KNOB


def test_every_environment_variable_the_code_reads_is_in_a_help_epilog(capsys):
    """D6 : six `PR_REVIEW_*` etaient lues et documentees nulle part."""
    from pipeline.launcher.cli import pr_review as review

    documented = ""
    for parse in (loop.parse_args, review.parse_args):
        with pytest.raises(SystemExit):
            parse(["--help"])
        documented += capsys.readouterr().out
    missing = sorted(var for var in env_knobs() if var not in documented)
    assert not missing, "variables lues nulle part documentees : %s" % missing


def test_the_knob_scan_actually_finds_something():
    """A scan that finds nothing would make the test above vacuous."""
    assert {"MAX_ROUNDS", "STAGES", "PR_REVIEW_BRIEF_EFFORT"} <= env_knobs()


def test_a_broken_environment_variable_is_named_instead_of_traced(
        monkeypatch, capsys):
    """La config est construite avant le journal : stderr est le seul canal.

    Un `MAX_ROUNDS=n_importe_quoi` sortait en `ValueError` nue sur un stderr
    que personne ne garde, avec un code 1 indistinguable d'un `STOP` voulu,
    et `run.log` jamais meme ouvert.
    """
    monkeypatch.setenv("MAX_ROUNDS", "n_importe_quoi")
    assert loop.main([]) == 1
    said = capsys.readouterr().err
    assert "MAX_ROUNDS" in said and "n_importe_quoi" in said


def test_every_environment_variable_the_code_reads_is_in_env_example():
    """CLAUDE.md : « document any new variable in the committed .env.example ».

    Le fichier le repete lui-meme, et rien ne le verifiait : les neuf
    reglages de la boucle et les six de la revue n'y etaient pas.
    """
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    missing = sorted(var for var in env_knobs() if var not in example)
    assert not missing, "absentes de .env.example : %s" % missing
