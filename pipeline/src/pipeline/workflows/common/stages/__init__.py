"""L'exploration : une lecture gratuite, une session qui condense, une carte.

Ce que ca remplace : six sessions payees qui relisaient chacune CLAUDE.md,
`docs/ARCHITECTURE.md` et `docs/PROJECT.md` avant d'ecrire trois paragraphes.
Le registre le montrait — sept a quinze tours par section, dont la moitie a
s'orienter.

**Deux entrees de table, dont une seule paie :**

1. `ground` colle les trois documents verbatim et la liste des fichiers
   suivis. Aucune session, aucun jugement, aucune perte. Ca ne va nulle part
   ailleurs que dans le prompt de l'etape 2 ;
2. `explore` lit ca, plus le code que le sujet touche, et rend une carte
   compacte. Elle ne paie donc aucun tour de lecture de documents.

C'est cette carte, et elle seule, que `repo_context()` sert ensuite a chaque
etape qui suit. Le budget est dans `BUDGET` et il n'est pas decoratif : chaque
session est un processus neuf, donc la carte est **reecrite dans le cache** a
chaque etape. Une carte qui double fait doubler ce qu'elle coute, six fois.

**Deux entrees de table et non un crochet** : la sortie d'une etape payante
voyage deja dans `ctx.results`, sous son nom — c'est par la que le routeur lit
sa reponse et que la publication lit les sections. Un canal parallele pour la
meme chose aurait fait de l'ordre d'execution deux choses a lire au lieu
d'une, alors que la table *est* la sequence.

**La carte est aussi gardee sur disque**, parce que `ctx.results` ne survit
pas a une reprise (`core/execution/context.py` le dit en toutes lettres) et
que `stages_done`, lui, peut y survivre : une reprise sauterait `explore` et
servirait une carte vide, en silence. Le fichier porte le tag d'artefact du
round, donc il vaut pour **ce round-la** — ce n'est pas un cache entre rounds,
qui servirait la carte d'hier a un depot qui a bouge depuis.

Ce garde-fou est **latent chez le raffinage** : son etat est reconstruit a
chaque run et il ne lit pas `--stages`, donc rien n'y saute jamais `explore`.
Il devient vivant le jour ou ces deux entrees montent dans une table dont
l'etat est persiste — celle de la boucle — et c'est exactement le jour ou le
trou serait coute un round. Il est ecrit maintenant parce qu'apres, il se
decouvre en production.

Dans `common/` parce que rien ici ne nomme un workflow : un workflow branche
ces deux entrees en declarant `explore_model` et `explore_effort` sur sa
config, et un etat qui porte `brief` et `subject` (le `Explored` plus bas).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pipeline.core.adapters import hub
from pipeline.core.domain import prompts
from pipeline.core.domain.action import Action
from pipeline.core.domain.outcomes.result import Result
from pipeline.core.domain.stage_spec import StageSpec
from pipeline.workflows.common.stages.explore import (
    CLOSE, EXPLORE_PROMPT, MAPPED, OPEN, UNMAPPED)

__all__ = ["BUDGET", "CLOSE", "EXPLORE_PROMPT", "Explored", "GROUND",
           "GROUNDING", "MAPPED", "OPEN", "SKILL", "TREE_LINES", "UNMAPPED",
           "entries", "ground", "keep", "map_file", "prompt", "repo_context",
           "spec", "turned_off"]

# Les noms des deux entrees : ceux du registre, et ceux que `--stages` filtre.
GROUND = "ground"
SKILL = "explore"

# Les documents colles verbatim dans le prompt de l'explorateur. Verbatim et
# non resumes : ils font 21 Ko en tout, et payer un modele pour les condenser
# couterait plus que les trois k de contexte que ca economise — en perdant la
# formulation exacte des contraintes, qui est justement ce qui compte.
# Un fichier absent est dit, jamais tu : une section vide et une section
# manquante ne se corrigent pas pareil.
GROUNDING = ("CLAUDE.md", "docs/ARCHITECTURE.md", "docs/PROJECT.md")

# Combien de fichiers suivis sont listes avant qu'on coupe. Un depot de mille
# fichiers n'a pas besoin d'etre enumere pour etre cartographie.
TREE_LINES = 1500

# Ce que la carte a le droit de peser, en caracteres (~4 k tokens). Le nombre
# vient du registre : une etape de raffinage ecrit dans son cache 17 a 34 k
# tokens par session, et la carte s'y ajoute a chacune des six. Au-dela de ce
# budget elle coute plus que les tours qu'elle supprime.
BUDGET = 16_000

ABSENT = "(absent from this repository)"
CUT = "\n[... truncated: the map ran over its budget ...]"
TREE_CUT = "[... truncated: only the first %d tracked files are listed ...]"

# Ce que le prompt d'une etape recoit quand un dry-run n'a fait tourner
# personne. Dit plutot que laisse vide : les prompts qu'un dry-run ecrit sur
# disque servent a etre relus, et un `{repo_context}` blanc s'y lirait comme
# une injection cassee plutot que comme une session non payee.
DRY_RUN = f"""{OPEN}
(dry run — no exploration session was paid, so there is no map)
{CLOSE}"""


@runtime_checkable
class Explored(Protocol):
    """Ce qu'un etat doit porter pour que ces deux entrees tournent.

    `subject` dit ce que ce run travaille — c'est ce qui decide quelles
    parties du depot comptent. `brief` est ou l'etape gratuite depose sa
    lecture, et seul l'explorateur le lit : il ne va jamais aux etapes qui
    suivent, qui ne recoivent que la carte.
    """

    stages_done: list[str]
    brief: str

    @property
    def subject(self) -> str: ...


# --- ce qui est gratuit ----------------------------------------------------


def _read(workspace, name: str) -> str:
    """Un document du depot, ou le mot qui dit qu'il n'y en a pas."""
    try:
        return (workspace.root / name).read_text(encoding="utf-8")
    except OSError:
        return ABSENT


def tree(files: list[str]) -> str:
    """Les fichiers suivis, coupes au budget."""
    if len(files) <= TREE_LINES:
        return "\n".join(files)
    return "\n".join([*files[:TREE_LINES], TREE_CUT % TREE_LINES])


def ground(ctx, state: Explored) -> Result[None]:
    """Les documents du depot et son arbre, poses dans l'etat. Rien n'est paye.

    Une entree de table et non un appel depuis le prompt de l'explorateur :
    lire le depot peut echouer, et une etape rend un `Result` que la sequence
    propage, la ou une fabrique de prompt n'aurait eu que la levee.

    Rend un echec quand git ne liste rien : sur un depot ca ne veut pas dire
    « aucun fichier », ca veut dire que l'adaptateur n'a pas repondu — et une
    carte etablie sans savoir ce que le depot contient vaut moins que pas de
    carte du tout.
    """
    workspace = ctx.cfg.workspace
    files = hub.repo(workspace).tracked_files()
    if not files:
        return Result.fail(
            "git listed no tracked file, so there is nothing to map — check"
            " that the workspace is a git repository")
    blocks = [f"<file path=\"{name}\">\n{_read(workspace, name)}\n</file>"
              for name in GROUNDING]
    blocks.append(f"<tracked-files count=\"{len(files)}\">\n{tree(files)}\n"
                  f"</tracked-files>")
    state.brief = "\n\n".join(blocks)
    return Result.of(None)


# --- ce qui paie -----------------------------------------------------------


def turned_off(ctx, state) -> Result[str]:
    """Le `skip` des deux entrees : `--explore` rend le depot a chaque etape."""
    if not ctx.cfg.explore:
        return Result.of("")
    return Result.of("--explore — no repo map; every stage reads the"
                     " repository for itself")


def prompt(ctx, state: Explored) -> str:
    """Le texte de l'exploration.

    `splice` et non `fill` : le sujet est le corps d'une issue et le brief est
    le depot lui-meme — les deux portent des `{...}` qu'une seconde passe de
    remplacement irait substituer.
    """
    return prompts.splice(EXPLORE_PROMPT, subject=state.subject,
                          brief=state.brief, budget=f"{BUDGET:,}")


def map_file(ctx) -> Path:
    """Ou la carte de ce round est gardee, a cote des autres artefacts."""
    tag = ctx.cfg.artifact_tag(ctx.round_no)
    return ctx.log_dir / f"{tag}-{SKILL}.map.md"


def fits(text: str, log=None) -> str:
    """La carte, ramenee dans son budget. Le dit quand elle deborde.

    Coupee plutot que refusee : une carte trop longue reste une carte, et
    faire echouer le run sur une session qui a bien travaille couterait plus
    que les caracteres en trop. L'avertissement est ce qui fait qu'on finit
    par regler le prompt plutot que de payer la coupe a chaque round.
    """
    text = text.strip()
    if len(text) <= BUDGET:
        return text
    if log is not None:
        log.warn(f"the repo map came back at {len(text)} characters for a"
                 f" {BUDGET} budget — truncated; tighten"
                 f" workflows/common/stages/explore.py if it keeps happening")
    return text[:BUDGET] + CUT


def keep(ctx, state) -> Result[None]:
    """L'`after` de l'exploration : ce qu'elle doit avoir obtenu, et ou il va.

    Une carte vide arrete le round. Les etapes qui suivent ont ete reglees
    pour travailler dessus, et les laisser partir sans ferait payer un round
    entier a un demi-contexte — un resultat qu'on ne saurait ni lire ni
    comparer a celui d'avant.

    L'ecriture sur disque, elle, n'arrete rien : elle ne sert qu'a une
    reprise, et ce run-ci tient deja sa carte dans `ctx.results`.
    """
    got = ctx.results.get(SKILL)
    if got is None:      # dry-run : personne n'a tourne, rien a garder
        return Result.of(None)
    said = fits(got.text, ctx.log)
    if not said:
        return Result.fail(
            "the exploration came back empty, so every section would work"
            " without a map — re-run, or use --explore to give each section"
            " the repository back")
    try:
        map_file(ctx).write_text(said, encoding="utf-8")
    except OSError as broke:
        ctx.log.warn(f"the repo map could not be kept on disk ({broke}) —"
                     f" this round is fine, a resumed one would lose it")
    ctx.log(f"repo map established — {len(said):,} characters served to every"
            f" stage of this round")
    return Result.of(None)


def spec(cfg) -> StageSpec:
    """L'entree payante de l'exploration, reglee par la config du workflow."""
    return StageSpec(SKILL, cfg.explore_model, cfg.explore_effort,
                     skip=turned_off, after=keep)


def entries(cfg) -> tuple:
    """Les deux entrees, dans l'ordre, a mettre en tete d'une table."""
    return (Action(GROUND, ground, skip=turned_off), spec(cfg))


# --- ce qu'une etape recoit ------------------------------------------------


def _block(said: str) -> str:
    return prompts.splice(MAPPED, digest=said)


def _kept(ctx) -> str:
    """La carte de ce round, relue sur disque. Vide quand il n'y en a pas."""
    try:
        return map_file(ctx).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def repo_context(ctx) -> str:
    """Le bloc `{repo_context}` d'une etape : la carte, ou son absence.

    Une seule porte pour toutes les facons de n'avoir pas de carte —
    `--explore`, `--stages` qui a ecarte l'etape, un dry-run, un workflow qui
    ne met pas ces entrees dans sa table. Les etapes n'ont pas a les
    distinguer : ce qui change pour elles est qu'il y a une carte ou non.

    L'ordre compte. `--explore` passe avant la relecture du disque : sinon un
    run lance pour rendre le depot aux etapes leur servirait la carte qu'un
    run precedent a laissee la.
    """
    if getattr(ctx.cfg, "explore", False):
        return UNMAPPED
    if SKILL in ctx.results:
        got = ctx.results[SKILL]
        # Presente mais vide : le dry-run, ou personne n'a tourne.
        return _block(fits(got.text)) if got is not None else DRY_RUN
    # Absente : l'etape a ete sautee. Une reprise la retrouve sur disque.
    said = _kept(ctx)
    return _block(said) if said else UNMAPPED
