"""La carte du depot : ce qu'on colle gratuitement, ce qu'on paie, ce qu'on sert.

Ce que ce fichier protege, et pourquoi chaque ligne a une raison d'exister :

- une carte est **lossy**, donc l'absence de carte doit se dire en toutes
  lettres a l'etape qui la recoit — sinon elle ne peut pas distinguer « ce
  detail n'existe pas » de « on ne me l'a pas donne », et elle invente ;
- la carte est du texte de modele qui **cite les fichiers du depot**, donc
  elle porte les `{body}` et `{num}` des templates qu'elle a lus : elle entre
  en une seule passe, ou la substitution suivante la mange ;
- `ctx.results` ne survit pas a une reprise et `stages_done` peut y survivre,
  donc la carte est gardee sur disque : sans ca une reprise sauterait
  l'exploration et servirait une carte vide, en silence ;
- chaque session est un processus neuf, donc la carte est reecrite dans le
  cache a **chaque** etape : au-dela de son budget elle coute plus que les
  tours qu'elle supprime.
"""

import types

from pipeline.core.domain.action import Action
from pipeline.core.domain.outcomes.result import Status
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.core.execution.context import Ctx
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import logbook
from pipeline.workflows.common import stages as explore
from pipeline.workflows.refinement.settings import RefinementConfig


class State:
    """Ce que les deux entrees lisent et remplissent."""

    def __init__(self, subject="une issue") -> None:
        self.stages_done: list[str] = []
        self.brief = ""
        self._subject = subject

    @property
    def subject(self) -> str:
        return self._subject


def answered(text: str):
    """Ce qu'une etape payante depose dans `ctx.results`."""
    return types.SimpleNamespace(text=text)


def context(tmp_path, *, results=None, **kw):
    """Le contexte d'un round, tel que la forme le monte."""
    ws = Workspace(tmp_path)
    cfg = RefinementConfig(issue=25, workspace=ws, round_no=2, **kw)
    log_dir = ws.refinement_dir / "25"
    log_dir.mkdir(parents=True, exist_ok=True)
    return Ctx(cfg=cfg, log=logbook.null(), log_dir=log_dir, round_no=2,
               results=dict(results or {}), workspace=ws)


def paper_repo(monkeypatch, files=("CLAUDE.md", "src/app.ts")):
    from pipeline.core.adapters import hub

    monkeypatch.setattr(
        hub, "git",
        lambda root, run=None: types.SimpleNamespace(
            tracked_files=lambda: list(files)))


# --- l'etape gratuite ------------------------------------------------------


def test_the_brief_carries_each_document_verbatim_and_the_tree(tmp_path,
                                                                monkeypatch):
    """Verbatim et non resume : 21 Ko, et payer un modele pour les condenser
    couterait plus que le contexte economise — en perdant la formulation
    exacte des contraintes, qui est ce qui compte."""
    paper_repo(monkeypatch)
    (tmp_path / "CLAUDE.md").write_text("la contrainte exacte", encoding="utf-8")
    state = State()
    assert explore.ground(context(tmp_path), state).ok
    assert "la contrainte exacte" in state.brief
    assert 'path="docs/ARCHITECTURE.md"' in state.brief
    assert "src/app.ts" in state.brief


def test_a_document_that_is_not_there_is_said_rather_than_left_blank(
        tmp_path, monkeypatch):
    """Une section vide et une section manquante ne se corrigent pas pareil."""
    paper_repo(monkeypatch)
    state = State()
    explore.ground(context(tmp_path), state)
    assert state.brief.count(explore.ABSENT) == len(explore.GROUNDING)


def test_a_repository_git_lists_nothing_of_stops_the_round(tmp_path,
                                                            monkeypatch):
    """Sur un depot ca ne veut pas dire « aucun fichier », ca veut dire que
    l'adaptateur n'a pas repondu — et une carte etablie sans savoir ce que le
    depot contient vaut moins que pas de carte du tout."""
    paper_repo(monkeypatch, files=())
    got = explore.ground(context(tmp_path), State())
    assert got.failed and "no tracked file" in got.reason


def test_the_tree_is_cut_at_its_budget_and_says_so():
    """Un depot de mille fichiers n'a pas besoin d'etre enumere."""
    said = explore.tree([f"f{n}.py" for n in range(explore.TREE_LINES + 50)])
    assert said.count("\n") == explore.TREE_LINES
    assert said.endswith(explore.TREE_CUT % explore.TREE_LINES)


# --- la table --------------------------------------------------------------


def test_the_two_entries_come_in_order_and_only_the_second_pays():
    """Le design en deux temps se lit dans la table, pas dans un corps."""
    free, paid = explore.entries(RefinementConfig(issue=25))
    assert isinstance(free, Action) and free.skill == explore.GROUND
    assert isinstance(paid, StageSpec) and paid.skill == explore.SKILL


def test_explore_turns_both_entries_off():
    """L'echappatoire : rendre a chaque etape son exploration."""
    on = types.SimpleNamespace(cfg=RefinementConfig(issue=25))
    off = types.SimpleNamespace(cfg=RefinementConfig(issue=25, explore=True))
    assert explore.turned_off(on, None).value == ""
    assert "--explore" in explore.turned_off(off, None).value
    assert all(step.skip is explore.turned_off
               for step in explore.entries(on.cfg))


# --- le budget et ce qui est garde -----------------------------------------


def test_a_map_within_its_budget_comes_back_untouched():
    assert explore.fits("  une carte courte  ") == "une carte courte"


def test_a_map_over_its_budget_is_cut_and_the_round_is_warned():
    """Coupee plutot que refusee : une carte trop longue reste une carte."""
    said: list[str] = []
    got = explore.fits("x" * (explore.BUDGET + 500),
                       types.SimpleNamespace(warn=said.append))
    assert got.endswith(explore.CUT)
    assert len(got) == explore.BUDGET + len(explore.CUT)
    assert said and str(explore.BUDGET) in said[0]


def test_the_map_is_kept_on_disk_for_a_resume(tmp_path):
    """`ctx.results` ne survit pas a une reprise, `stages_done` peut."""
    ctx = context(tmp_path, results={explore.SKILL: answered("### la carte")})
    assert explore.keep(ctx, State()).ok
    assert explore.map_file(ctx).read_text(encoding="utf-8") == "### la carte"
    assert explore.map_file(ctx).name == "r02-explore.map.md"


def test_what_is_kept_is_already_within_the_budget(tmp_path):
    ctx = context(tmp_path,
                  results={explore.SKILL: answered("x" * (explore.BUDGET + 9))})
    explore.keep(ctx, State())
    assert explore.map_file(ctx).read_text(encoding="utf-8").endswith(
        explore.CUT)


def test_an_exploration_that_came_back_empty_stops_the_round(tmp_path):
    """Les etapes qui suivent ont ete reglees pour travailler sur une carte."""
    ctx = context(tmp_path, results={explore.SKILL: answered("   ")})
    got = explore.keep(ctx, State())
    assert got.failed and got.status is Status.FAILED
    assert not explore.map_file(ctx).exists()


def test_a_dry_run_keeps_nothing_and_does_not_fail(tmp_path):
    ctx = context(tmp_path, dry_run=True, results={explore.SKILL: None})
    assert explore.keep(ctx, State()).ok
    assert not explore.map_file(ctx).exists()


# --- ce qu'une etape recoit ------------------------------------------------


def test_a_round_without_a_map_says_so_instead_of_serving_nothing(tmp_path):
    """Un bloc vide se lirait comme une injection cassee."""
    assert explore.repo_context(context(tmp_path)) == explore.UNMAPPED
    assert "No map was established" in explore.UNMAPPED


def test_the_map_of_this_round_is_served_inside_a_block_that_names_itself(
        tmp_path):
    ctx = context(tmp_path,
                  results={explore.SKILL: answered("### Constraints\njamais main")})
    said = explore.repo_context(ctx)
    assert said.startswith(explore.OPEN) and explore.CLOSE in said
    assert "jamais main" in said
    # Ce que la carte autorise vient apres elle : l'orientation est supprimee,
    # pas la verification.
    assert "the code wins" in " ".join(said.split())


def test_a_resumed_round_reads_the_map_back_from_disk(tmp_path):
    """L'etape est dans `stages_done`, donc elle ne retourne pas — et sans le
    fichier, les six sections partiraient sur une carte vide, en silence."""
    ctx = context(tmp_path, results={explore.SKILL: answered("### la carte")})
    explore.keep(ctx, State())
    resumed = context(tmp_path)          # `results` repart vide, comme au vrai
    assert "### la carte" in explore.repo_context(resumed)


def test_explore_beats_a_map_a_previous_round_left_on_disk(tmp_path):
    """Un run lance pour rendre le depot aux etapes ne doit pas leur servir
    la carte d'hier."""
    explore.keep(context(tmp_path,
                         results={explore.SKILL: answered("### la carte")}),
                 State())
    assert explore.repo_context(context(tmp_path, explore=True)) == (
        explore.UNMAPPED)


def test_a_dry_run_says_why_there_is_no_map(tmp_path):
    """Les prompts qu'un dry-run ecrit servent a etre relus."""
    ctx = context(tmp_path, dry_run=True, results={explore.SKILL: None})
    assert explore.repo_context(ctx) == explore.DRY_RUN
    assert explore.repo_context(ctx).count(explore.OPEN) == 1


# --- la substitution -------------------------------------------------------


def test_the_subject_and_the_brief_enter_the_prompt_in_a_single_pass(tmp_path):
    """Le sujet est le corps d'une issue : un `{brief}` qu'un humain y ecrit
    se ferait remplacer par la passe suivante."""
    state = State(subject="regarde {brief} de pres")
    state.brief = "LE-BRIEF"
    said = explore.prompt(context(tmp_path), state)
    assert "regarde {brief} de pres" in said
    assert "LE-BRIEF" in said


def test_the_explorer_is_told_the_repository_is_public():
    """Ce qu'il ecrit finit dans le corps d'une issue publique."""
    assert "public" in explore.EXPLORE_PROMPT
    assert "Never write the value of a secret" in explore.EXPLORE_PROMPT


def test_the_explorer_is_told_to_change_nothing():
    assert "Change no file" in explore.EXPLORE_PROMPT
