"""Les portes qu'un workflow passe avant de depenser quoi que ce soit.

Chaque porte ici a coute un run a ecrire. Une faute de frappe dans la table
ne coute rien a trouver a ce moment-la, et un stage entier a trouver une fois
que `claude` a ete facture.

Elles sont communes parce qu'aucune n'est propre a un workflow : `claude` sur
le PATH, `gh` authentifie, un arbre de travail propre, une branche qui existe
— la boucle les exigeait toutes, la revue de PR n'en exigeait aucune alors
qu'elle depend de `gh` autant que la boucle. Un workflow compose la liste qui
le concerne ; ce qui lui est propre reste chez lui.

**Une porte ne rend jamais None** : elle rend un `Result`, en echec avec la
phrase sur laquelle un humain agit, ou en succes. Aucun appel externe n'est
fait ici — `adapters.shell` les porte tous.

Standard library seulement, hors adaptateurs : le preflight tourne avant le
moteur, et doit pouvoir echouer sans l'avoir charge.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pipeline.adapters.shell import binaries
from pipeline.domain.outcomes.result import Result
from pipeline.runtime.filesystem.workspace import Workspace
from pipeline.runtime.monitoring.logbook import Logbook
from pipeline.workflows.common.utils import hub


class Checked(Protocol):
    """Le minimum qu'une porte commune lit dans une config de workflow."""

    workspace: Workspace


class BranchChecked(Checked, Protocol):
    """Ce que les portes de branche lisent en plus."""

    integration_branch: str


@dataclass(frozen=True)
class Check:
    """Une porte : un nom pour la nommer, et ce qu'elle verifie.

    Le nom est la pour qu'un lecteur liste ce qui est verifie sans lire les
    corps — et pour qu'une passe d'observabilite ait quelque chose a
    journaliser quand chacune passe.
    """

    name: str
    verify: Callable[[Checked, Logbook], Result[None]]


def verify_all(checks: tuple[Check, ...], cfg: Checked,
               log: Logbook) -> Result[None]:
    """Les portes, dans l'ordre, jusqu'a la premiere qui echoue.

    S'arreter a la premiere est le comportement voulu : les portes se
    supposent les unes les autres — demander a `gh` quelles etiquettes existe
    n'a pas de sens tant qu'on ne sait pas s'il est authentifie.
    """
    for check in checks:
        got = check.verify(cfg, log)
        if got.failed:
            return got
    return Result.of(None)


# --- les portes, une fonction chacune --------------------------------------


def claude_on_path(cfg: Checked, log: Logbook) -> Result[None]:
    if not binaries.installed("claude"):
        return Result.halt("claude CLI not on PATH")
    return Result.of(None)


def gh_on_path(cfg: Checked, log: Logbook) -> Result[None]:
    if not binaries.installed("gh"):
        return Result.halt("gh CLI not on PATH")
    return Result.of(None)


def gh_authenticated(cfg: Checked, log: Logbook) -> Result[None]:
    if not hub.gh(cfg.workspace).authenticated():
        return Result.halt("gh is not authenticated — run: gh auth login")
    return Result.of(None)


def integration_branch_exists(cfg: BranchChecked,
                              log: Logbook) -> Result[None]:
    branch = cfg.integration_branch
    if not hub.repo(cfg.workspace).has_branch(branch):
        return Result.halt(f"branch {branch} does not exist — run: git branch"
                           f" {branch} origin/main")
    return Result.of(None)


def on_the_integration_branch(cfg: BranchChecked,
                              log: Logbook) -> Result[None]:
    current = hub.repo(cfg.workspace).current_branch()
    if current != cfg.integration_branch:
        return Result.halt(f"on branch {current} — run: git checkout"
                           f" {cfg.integration_branch}")
    return Result.of(None)


def branch_is_on_origin(cfg: BranchChecked, log: Logbook) -> Result[None]:
    branch = cfg.integration_branch
    if not hub.repo(cfg.workspace).origin_has_branch(branch):
        return Result.halt(f"origin has no {branch} — run: git push -u origin"
                           f" {branch}")
    return Result.of(None)


def ci_triggers_on_the_branch(cfg: BranchChecked,
                              log: Logbook) -> Result[None]:
    """Sans ca les PR que les stages ouvrent ne portent aucun check `ci`.

    Et le `gh pr checks` que les skills attendent ne se resout jamais.
    """
    ci = cfg.workspace.ci_workflow
    branch = cfg.integration_branch
    if not ci.exists() or branch not in ci.read_text(encoding="utf-8"):
        return Result.halt(f".github/workflows/ci.yml does not trigger on"
                           f" {branch}")
    return Result.of(None)


def working_tree_is_clean(cfg: Checked, log: Logbook) -> Result[None]:
    """L'arbre de travail est propre, sauf si le run a demande le contraire.

    `allow_dirty` est lu par `getattr` : un workflow qui n'offre pas le
    reglage exige simplement un arbre propre, sans avoir a porter un champ
    pour cette porte.
    """
    if getattr(cfg, "allow_dirty", False):
        return Result.of(None)
    dirty = hub.repo(cfg.workspace).dirty_files()
    if dirty:
        for line in dirty:
            log.warn(line)
        return Result.halt("working tree is dirty — commit, stash, or re-run"
                           " with ALLOW_DIRTY=1")
    return Result.of(None)


# Ce dont tout workflow de ce paquet depend, dans l'ordre ou ca se verifie.
# Un workflow compose sa liste a partir de la :
# `(*checks.TOOLING, Check("pipeline-labels", ...))`.
TOOLING: tuple[Check, ...] = (
    Check("claude-cli", claude_on_path),
    Check("gh-cli", gh_on_path),
    Check("gh-auth", gh_authenticated),
)

# Ce qu'un workflow qui travaille sur la branche d'integration exige d'elle.
BRANCH: tuple[Check, ...] = (
    Check("branch-exists", integration_branch_exists),
    Check("branch-checked-out", on_the_integration_branch),
    Check("branch-on-origin", branch_is_on_origin),
    Check("ci-triggers", ci_triggers_on_the_branch),
)
