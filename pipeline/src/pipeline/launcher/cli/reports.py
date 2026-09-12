"""Ce que `--costs` et `--status` impriment.

De la mise en forme, et rien d'autre : ces fonctions lisent le registre et
l'etat de reprise, et rendent une chaine. Elles ne decident de rien, n'ecrivent
rien, et sont sur le chemin rapide — bibliotheque standard, ni crewai ni SDK.

Les deux rapports ont la meme forme — lire, ecarter ce qui est illisible,
filtrer, agreger, rendre — et chaque etape est une fonction pure qui prend des
lignes et rend des lignes.

La premiere table est celle du shell, caractere pour caractere : un test
oracle la compare. Ce qui la suit est en plus, separe par une ligne vide pour
que la comparaison reste possible.
"""

from __future__ import annotations

import collections
from pathlib import Path

from pipeline.core.adapters.store.ledger import (
    CACHE_READ, CACHE_WRITE, COST, OUTCOME, RAN_ON, RUN, STAGE, TASK,
    TOKENS_IN, WHEN, rows)
from pipeline.core.adapters.store.resume import read_pointer, stages_done
from pipeline.core.runtime.filesystem.workspace import Workspace
from pipeline.core.runtime.monitoring import metrics
from pipeline.workflows.common.utils import hub

Rows = list[list[str]]


# --- lire et ecarter -------------------------------------------------------


def _usable(data: Rows) -> tuple[Rows, int]:
    """Les lignes exploitables, et le nombre de celles qui ne le sont pas.

    Une ligne trop courte ne porte pas `ran_on` et ne peut etre placee dans
    aucune table. L'ecarter en silence faisait qu'un registre tronque
    sous-estimait la depense sans rien dire.
    """
    usable = [r for r in data if len(r) > RAN_ON]
    return usable, len(data) - len(usable)


def _ignored(n: int, ledger: Path) -> str:
    """What an unreadable row costs the reader: a total that is too small."""
    return (f"{n} row(s) ignored: fewer than {RAN_ON + 1} columns. {ledger} is"
            f" truncated, and every total above under-reports what was spent.")


def _empty(ledger: Path) -> str:
    return f"no cost ledger yet — {ledger} is written as stages run"


# --- agreger ---------------------------------------------------------------


def _cost(row: list[str]) -> float:
    return float(row[COST] or 0)


def _by_stage(data: Rows) -> dict[tuple[str, str], list]:
    """`(stage, ran_on)` -> `[total, compte]`."""
    by: dict[tuple[str, str], list] = collections.OrderedDict()
    for r in data:
        agg = by.setdefault((r[STAGE], r[RAN_ON]), [0.0, 0])
        agg[0] += _cost(r)
        agg[1] += 1
    return by


def _grouped(data: Rows, column: int, *, daily: bool
             ) -> tuple[dict[str, list], int]:
    """`cle` -> `[total, stages, echecs, gaspille]`, et les lignes sans issue.

    L'argent depense sur un stage qui a echoue n'a rien achete : il est
    compte a cote du total plutot que fondu dedans.
    """
    agg: dict[str, list] = collections.OrderedDict()
    unknown = 0
    for r in data:
        key = r[column][:10] if daily else r[column]
        cell = agg.setdefault(key, [0.0, 0, 0, 0.0])
        cell[0] += _cost(r)
        cell[1] += 1
        outcome = r[OUTCOME] if len(r) > OUTCOME else ""
        if not outcome:
            unknown += 1
        elif outcome != "ok":
            cell[2] += 1
            cell[3] += _cost(r)
    return agg, unknown


def _usage(row: list[str]) -> dict[str, int]:
    """The token counters a row carries, under the SDK's own key names.

    Written back into the shape `metrics` speaks, so that the input-token
    arithmetic has one home rather than one per reader.
    """
    return {"cache_read_input_tokens": int(row[CACHE_READ] or 0),
            "cache_creation_input_tokens": int(row[CACHE_WRITE] or 0),
            "input_tokens": (int(row[TOKENS_IN])
                             if row[TOKENS_IN].isdigit() else 0)}


def _by_cache(data: Rows) -> dict[str, list[int]]:
    """`stage` -> `[tokens lus en cache, tokens d'entree]`."""
    by: dict[str, list[int]] = collections.OrderedDict()
    for r in data:
        if len(r) <= CACHE_WRITE or not r[CACHE_READ]:
            continue
        usage = _usage(r)
        agg = by.setdefault(r[STAGE], [0, 0])
        agg[0] += usage["cache_read_input_tokens"]
        agg[1] += metrics.input_tokens(usage)
    return by


# --- rendre ----------------------------------------------------------------


def _stage_table(by: dict[tuple[str, str], list]) -> list[str]:
    """La table du shell, caractere pour caractere — un oracle la compare."""
    out = [f"{'stage':<22} {'ran on':<16} {'total $':>9} {'runs':>5} {'avg $':>9}"]
    out += [f"{stage:<22} {ran_on:<16} {total:>9.4f} {n:>5d} {total / n:>9.4f}"
            for (stage, ran_on), (total, n) in by.items()]
    out.append(f"{'ALL':<22} {'':<16} {sum(v[0] for v in by.values()):>9.4f}"
               f" {sum(v[1] for v in by.values()):>5d}")
    return out


def _cache_table(by: dict[str, list[int]]) -> list[str]:
    """What the cache saved, by stage.

    A cache read costs a fraction of the full price: a ratio that collapses is
    the first thing to look at when the bill goes up without the work
    changing.
    """
    if not by:
        return []
    out = [f"{'stage':<22} {'in':>9} {'cache':>9}"]
    out += [f"{stage:<22} {metrics.tokens(total):>9}"
            f" {(round(read / total * 100) if total else 0):>8d}%"
            for stage, (read, total) in by.items()]
    return out


def _group_table(agg: dict[str, list], title: str) -> list[str]:
    width = min(max([len(k) for k in agg] + [len(title)]), 44)
    out = [f"{title:<{width}} {'total $':>9} {'stages':>7} {'failed':>7}"
           f" {'wasted $':>9}"]
    out += [f"{key[:width]:<{width}} {total:>9.4f} {n:>7d} {failed:>7d}"
            f" {wasted:>9.4f}"
            for key, (total, n, failed, wasted) in agg.items()]
    out.append(f"{'ALL':<{width}} {sum(v[0] for v in agg.values()):>9.4f}"
               f" {sum(v[1] for v in agg.values()):>7d}"
               f" {sum(v[2] for v in agg.values()):>7d}"
               f" {sum(v[3] for v in agg.values()):>9.4f}")
    return out


def _section(lines: list[str]) -> list[str]:
    """Un bloc en plus, separe par une ligne vide — ou rien."""
    return ["", *lines] if lines else []


def _footnotes(*, unknown: int = 0, skipped: int = 0,
               ledger: Path | None = None) -> list[str]:
    """Ce que les totaux ci-dessus ne disent pas d'eux-memes."""
    notes = []
    if unknown:
        notes.append(f"{unknown} row(s) predate the outcome column and count"
                     f" as neither.")
    if skipped and ledger is not None:
        notes.append(_ignored(skipped, ledger))
    return notes


# --- les deux rapports -----------------------------------------------------


def report(ledger: Path) -> str:
    """What the loop has spent, by stage — the output of `--costs`."""
    if not ledger.exists() or ledger.stat().st_size == 0:
        return _empty(ledger)
    all_rows = rows(ledger)
    data, skipped = _usable(all_rows)
    # La section cache lit `all_rows` : elle a ses propres exigences de
    # colonnes, plus larges que celles de la table principale.
    return "\n".join([
        *_stage_table(_by_stage(data)),
        *_section(_cache_table(_by_cache(all_rows))),
        *_section(_footnotes(skipped=skipped, ledger=ledger)),
    ])


# What a run/task/day breakdown groups by, and how it reads in the header.
GROUPS = {"run": (RUN, "run"), "task": (TASK, "task"),
          "day": (WHEN, "day"), "stage": (STAGE, "stage")}


def _matching(data: Rows, *, run: str, task: str, since: str) -> Rows:
    """Les lignes que les trois filtres laissent passer."""
    if run:
        data = [r for r in data if r[RUN] == run]
    if task:
        data = [r for r in data if task.lower() in r[TASK].lower()]
    if since:
        data = [r for r in data if r[WHEN][:10] >= since]
    return data


def breakdown(ledger: Path, *, by: str = "task", run: str = "",
              task: str = "", since: str = "") -> str:
    """The same register, grouped another way — and honest about failures.

    `report` answers "what does a stage cost on average", which is the
    question the shell answered. It cannot answer "what did task 4 cost me"
    or "what did today cost", because it ignores the `run` and `task` columns
    it writes; those took an awk one-liner over a file the loop already had.
    """
    if by not in GROUPS:
        return (f"unknown grouping {by!r} — pick one of:"
                f" {', '.join(sorted(GROUPS))}")
    data, skipped = _usable(rows(ledger))
    if not data:
        # Un registre entierement tronque n'est pas un registre vide, et les
        # deux ne demandent pas la meme chose a l'operateur : l'un dit
        # « rien n'a encore tourne », l'autre « le fichier est abime et tes
        # totaux sont faux ». `report` faisait deja la difference.
        return _ignored(skipped, ledger) if skipped else _empty(ledger)

    data = _matching(data, run=run, task=task, since=since)
    if not data:
        return "no ledger row matches that filter"

    column, title = GROUPS[by]
    agg, unknown = _grouped(data, column, daily=by == "day")
    return "\n".join([
        *_group_table(agg, title),
        *_section(_footnotes(unknown=unknown, skipped=skipped, ledger=ledger)),
    ])


# --- `--status` ------------------------------------------------------------


def status_text(workspace: Workspace) -> str:
    """La sortie de `--status` : d'ou un re-run repartirait."""
    task, flow_id = read_pointer(workspace.state)
    if not task:
        return "no resume point — the next run starts a round from the top"
    return "\n".join([
        f"resume point ({workspace.rel(workspace.state)}):",
        f"  task={task}",
        *([f"  flow_id={flow_id}"] if flow_id else []),
        *_completed_lines(workspace, flow_id or ""),
        *_issue_lines(workspace, task),
    ])


def _completed_lines(workspace: Workspace, flow_id: str) -> list[str]:
    """Les stages deja faits, ou pourquoi on n'a pas su les lire.

    `--status` doit rester une commande qui repond, donc une lecture degradee
    est une ligne ici — mais jamais une ligne qui dirait « rien ».
    """
    read = stages_done(flow_id, workspace.flow_db)
    if read.failed:
        return [f"  completed: unknown — {read.reason}"]
    return [f"  completed: {' '.join(read.value)}"] if read.value else []


def _issue_lines(workspace: Workspace, key: str) -> list[str]:
    """Ce que l'issue de reprise dit d'elle-meme, ou pourquoi on n'a pas su.

    L'inverse exact de ce que fait le round : la, une lecture d'issue ratee
    arrete le run, parce que la suite depense de l'argent. Ici rien ne se
    depense, et `--status` doit rester une commande qui repond — donc une API
    muette est une ligne, et le `Result` en echec ne va pas plus loin.
    """
    if not key.isdigit():
        return [f"  (this pointer predates the move to GitHub issues:"
                f" {key!r} is not an issue number. Clear it with"
                f" `agent-loop --restart`.)"]
    read = hub.gh(workspace).issue(int(key))
    if read.failed:
        return [f"  issue #{key}: unreadable — {read.reason}"]
    issue = read.value
    marks = " ".join(l for l in issue.labels if l.startswith("pipeline:"))
    line = f"  issue #{issue.number}: {issue.title} [{issue.state}]"
    return [line + (f" — {marks}" if marks else "")]
