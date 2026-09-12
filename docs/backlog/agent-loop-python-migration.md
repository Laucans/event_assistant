# Migration du pipeline : Bash → Python (Claude Agent SDK + CrewAI Flows)

État : **fait le 2026-09-09.** Le code vit dans `pipeline/` ; les deux
scripts shell sont supprimés. Ce document reste la trace des décisions et
de la preuve d'équivalence — voir `pipeline/README.md` pour l'usage et `pipeline/INTERNALS.md` pour les rouages.

## Décisions prises

| Question | Réponse |
| --- | --- |
| Cible | **Agent SDK + CrewAI Flows** (option B) — l'orchestration devient un `Flow`, le travail reste des sessions Claude Code |
| Douleur à résoudre | maintenabilité long terme et **abstraction du flow** |
| Périmètre | `scripts/agent-loop.sh` **+** `scripts/pr-review.sh` **+** les hooks Python |
| Méthode | **big bang** — le `.sh` disparaît dans la même PR |
| Forme du flow | **un nœud par stage**, graphe explicite et lisible dans le code |
| État | `@persist` pour la reprise, **`costs.tsv` conservé** au même format |

L'option A (Python nu, sans CrewAI) avait été recommandée sur la base du coût
de dépendances ; B est retenue en connaissance de cause pour l'abstraction de
flow qu'elle apporte. Ce document part de B.

## Faits établis (vérifiés le 2026-09-09)

- `crewai` 1.15.21 — `requires_python = "<3.14,>=3.10"`, ~30 dépendances
  runtime dont `chromadb`, `lancedb`, `openai>=2.30`, `tokenizers`,
  `pdfplumber`, `opentelemetry-*`.
- **La machine tourne en Python 3.14.5 : CrewAI ne s'y installe pas.**
  Interpréteur utilisable déjà présent :
  `/opt/homebrew/opt/python@3.13/bin/python3.13` → 3.13.13. Pas de `uv`,
  `poetry` ni `pipx`.
- `claude-agent-sdk` 0.2.152 — `requires_python = ">=3.10"`, 4 dépendances
  (`anyio`, `jsonschema`, `mcp`, `sniffio`).
- Le SDK s'authentifie **via le login du CLI** : l'inférence reste sur
  l'abonnement, contrainte n°1 de `CLAUDE.md`.
- `ClaudeAgentOptions` expose `model`, `permission_mode`, `setting_sources`
  (`["project"]` charge `.claude/settings.json` — hooks, agents, skills,
  permissions), `resume`, `fork_session`, `continue_conversation`,
  `max_budget_usd`. `ResultMessage` porte `total_cost_usd`.
- Les `Flow` CrewAI acceptent des méthodes `async def`, s'exécutent via
  `kickoff()` / `kickoff_async()`, et `@persist` écrit l'état dans un SQLite,
  avec reprise (`kickoff(inputs={"id": ...})`) et fork
  (`kickoff(restore_from_state_id=...)`).
- Le repo contient déjà du Python : `scripts/hooks/*.py` et **4 heredocs**
  dans `agent-loop.sh` (lignes 142, 210, 237, 379).

## Architecture cible

```
pipeline/
  pyproject.toml            # requires-python ">=3.13,<3.14"  (plafond crewai)
  .venv/                    # gitignoré, cree avec python3.13
  src/pipeline/
    domain/                 # le métier pur : table, prompts, regex, arrêts
    runtime/                # chemins, journal, mesures (feuille)
    adapters/               # SDK, moteur de graphe, git/gh, registre, reprise
    workflow/               # le round, les passes de revue, le préflight, RunConfig
    cli/                    # les flags, les codes de sortie, la mise en forme
    hooks/                  # logique des hooks, importable et testable
  tests/                    # pytest, en miroir de l'arborescence ci-dessus
scripts/
  agent-loop                # shim 3 lignes -> pipeline/.venv/bin/python -m pipeline.cli.loop
  hooks/*.py                # entrypoints minces qui importent pipeline.hooks
```

Le shim `scripts/agent-loop` existe pour la mémoire musculaire et parce que
des chemins en dur pointent vers `scripts/` ; il ne contient aucune logique.

### Le flow

```python
@persist
class AgentLoop(Flow[LoopState]):
    @start()
    def preflight(self): ...

    @listen(preflight)
    def pick_task(self): ...              # première task todo, ou rollover

    @router(pick_task)
    def route(self):
        return "planner" if self.state.all_done else "spec"

    @listen("spec")
    async def business_analyst(self): ...  # skip si le SPEC existe déjà

    @listen(business_analyst)
    def human_gate(self): ...              # halt si un item "Before Claude starts" est ouvert

    @listen(human_gate)
    async def code(self): ...              # /tech-analyst -> /code, une session

    @listen(code)
    async def create_test(self): ...

    @listen(create_test)
    async def archive(self): ...           # post-conditions : SPEC parti, count_done +1
```

`LoopState` est un `BaseModel` : `round`, `task_num`, `task_title`,
`stages_done`, `spec_present`, `done_before`, `run_id`.

## Table de parité — les 12 invariants du script actuel

Aucune PR ne se ferme tant que cette colonne de droite n'est pas verte.

| # | Invariant (aujourd'hui) | Où il atterrit |
| --- | --- | --- |
| 1 | Table `PIPELINE` + `STAGES`/`MODEL`/`EFFORT` | `config.py` (`StageSpec`) ; les filtres deviennent des flags CLI |
| 2 | Un process par stage = contexte frais | `session.py` : une `query()` par nœud, sans `resume` |
| 3 | Inférence sur l'abonnement | acquis : le SDK passe par le login CLI. **Ne jamais poser `ANTHROPIC_API_KEY`** |
| 4 | Coût réel + détection des faux succès (quota) | `ResultMessage` : `total_cost_usd`, `is_error`, `subtype`, **`api_error_status`** (429), `terminal_reason`, `stop_reason`, `model_usage`. Le `grep -iE 'usage limit\|rate limit\|session limit'` sur du texte anglais disparaît |
| 5 | `AGENT_LOOP_OK` / `AGENT_LOOP_STOP` | **conservé** — lisible par un humain dans les logs, indépendant du SDK |
| 6 | Reprise au stage près, scopée à une task | `@persist` + un pointeur `current_task` → `state_id` |
| 7 | Parsing du milestone | `docs_state.py` (le heredoc ligne 210, testé) |
| 8 | Gate humaine | `docs_state.py` (heredoc ligne 237) — l'absence du fichier reste bloquante |
| 9 | Pré/post-conditions par stage | dans le nœud du stage concerné |
| 10 | 12 vérifications de preflight | `preflight.py` + le nœud `@start` |
| 11 | Logs, notification macOS, `halt` | `cli.py` ; `halt` devient une exception typée |
| 12 | `--dry-run` | conservé : les prompts sont écrits, aucune session n'est ouverte |

## Ce qui change volontairement

- **Le contrôle de session devient explicite.** `/tech-analyst` → `/code`
  tient aujourd'hui parce que les deux commandes sont collées dans un seul
  prompt. Avec `resume` / `fork_session`, l'enchaînement s'exprime en Python.
  À faire **après** la parité, pas pendant.
- **Les hooks deviennent du code testé.** Les `python3 -c '...'` inline de
  `.claude/settings.json` migrent vers `pipeline/hooks/`, les entrypoints de
  `scripts/hooks/` restent minces. Contrainte : un hook doit rendre la main en
  millisecondes — l'entrypoint ne doit **pas** importer `crewai`.
- **`pr-review.sh` partage le module de session et le ledger** au lieu de
  redupliquer le parsing d'enveloppe.

## Ce que l'introspection du SDK ouvre en plus (non prévu au départ)

Vérifié sur `claude-agent-sdk` 0.2.152, `ClaudeAgentOptions` (48 champs) :

- `max_budget_usd` et `task_budget` — un **plafond de coût par stage**, là où
  le ledger ne fait que constater après coup.
- `fallback_model` — un stage bloqué par le quota peut basculer de modèle au
  lieu de faire halter la boucle.
- `session_id` est **assignable** : l'id de session du ledger devient
  déterministe et corrélable au run, au lieu d'être lu après coup.
- `skills`, `agents` (avec `model`/`effort`/`skills` par sous-agent), `hooks`
  programmatiques — en plus de `setting_sources`, qui charge déjà
  `.claude/settings.json`.
- `stderr` (callback) et `include_partial_messages` — du log structuré au fil
  de l'eau, au lieu d'un fichier lu à la fin.
- `extra_args: dict[str, str | None]` — l'échappatoire pour tout flag CLI que
  le SDK n'exposerait pas encore.
- `enable_file_checkpointing`, `sandbox`, `max_turns` — à évaluer plus tard.

Le SDK reste un **wrapper au-dessus du binaire `claude`** (il lève
`CLINotFoundError` s'il est absent) : même modèle d'exécution, même
authentification, mêmes hooks qu'aujourd'hui. La migration réécrit
l'orchestration, pas l'exécution — c'est ce qui rend le big bang tenable.

## Risques et points à vérifier en premier

1. ~~`effort` n'est peut-être pas exposé par `ClaudeAgentOptions`.~~
   **Levé le 2026-09-09** par introspection du paquet installé (0.2.152) :
   `ClaudeAgentOptions` a 48 champs dont
   `effort: Literal['low','medium','high','xhigh','max'] | None`, et
   `_internal/transport/subprocess_cli.py:767` fait
   `cmd.extend(["--effort", self._options.effort])` — le même flag que le
   script actuel. `AgentDefinition` porte en plus son propre `effort`, donc
   un sous-agent peut être réglé indépendamment.
2. ~~Installer CrewAI sur un venv 3.13 et mesurer.~~ **Fait le 2026-09-09**,
   sur `/opt/homebrew/opt/python@3.13/bin/python3.13` :

   | Mesure | CrewAI + SDK | SDK seul | Bash actuel |
   | --- | --- | --- | --- |
   | Install | 65 s | ~10 s | — |
   | Poids du venv | **771 Mo** | 245 Mo | — |
   | Paquets | **135** | 31 | — |
   | Import (à chaud) | 1,2–1,5 s | 0,4–0,6 s | — |
   | Process bout-en-bout | **2,5–3,1 s** | — | **0,01–0,02 s** |

   Un `Flow` réel (`@start` / `@router` / `@listen` async / `@persist`,
   subprocess, **sans LLM ni clé API**) s'exécute correctement : la faisabilité
   est acquise. Mais importer `crewai.flow.flow` charge `chromadb`, `openai`,
   `opentelemetry` et `numpy` — 2331 modules — juste pour obtenir `@listen`.
3. **Télémétrie** : au premier run, CrewAI écrit une préférence de tracing
   (désactivée par défaut hors interactif). Variables à poser explicitement :
   `CREWAI_DISABLE_TELEMETRY`, `CREWAI_DISABLE_TRACKING`,
   `CREWAI_DISABLE_VERSION_CHECK`, `CREWAI_TRACING_ENABLED=false`. À
   documenter dans `.env.example`.
4. **Le plafond `<3.14` est une dette** : la machine est déjà en 3.14. À
   réévaluer à chaque bump de CrewAI.
5. **`@persist` ne connaît pas la notion de task**, et **écrit hors du
   repo** : mesuré, il a créé
   `~/Library/Application Support/<nom ambiant>/flow_states.db` — un chemin
   dérivé du nom du processus, pas du projet. Deux conséquences : le mapping
   task → `state_id` est à écrire à la main, et le chemin de la base doit être
   épinglé explicitement dans `.llocal/agent-loop/`, sinon l'état de la boucle
   vit dans un dossier système que `--restart` ne sait pas nettoyer.
6. **CI** : `.github/workflows/ci.yml` ne connaît que npm. Décider si les
   tests pytest y entrent (et donc un setup Python dans CI) ou restent locaux.

## Ce que CrewAI apporte au-delà des décorateurs

Inventaire fait sur le paquet installé (2026-09-09). Quatre choses réelles,
une seule qui touche une mécanique centrale du pipeline :

- **Suspension / reprise sur intervention humaine** — `@human_feedback`,
  `Flow.pending_feedback`, `Flow.from_pending(flow_id)`,
  `Flow.resume(feedback)`. Aujourd'hui la gate humaine fait `halt()` : le
  process meurt, l'humain coche, et un nouveau run **re-dérive** où il en
  était. Ici le flow est *suspendu* et ranimé au point exact. À évaluer : ce
  chemin n'a pas été testé de bout en bout, seulement l'exécution nominale.
- **Checkpoint / fork** — `from_checkpoint(config)`,
  `fork(config, branch=...)`. Le fichier `state` actuel en est un
  sous-ensemble écrit à la main. Le fork permet ce qu'on ne sait pas faire :
  rejouer la task 4 depuis le stage `code` sur sonnet **en branche**, en
  gardant l'original pour comparer les coûts.
- **`plot(filename, show)`** — visualisation HTML interactive du graphe. Le
  pipeline devient regardable ; c'est littéralement « l'abstraction du flow ».
- **`stream_events()` / bus d'événements** — log, notification macOS et halt
  s'abonnent au lieu d'être appelés en ligne dans chaque fonction.

Et ce qui **n'apporte rien ici**, pour être complet : `usage_metrics` ne
compte que les tokens des LLM appelés *par CrewAI* — nos stages sont des
sous-process, le ledger reste écrit à la main ; `@or_`/`@and_` ne servent pas
sur une séquence stricte ; l'état structuré, c'est Pydantic (une dépendance,
pas 771 Mo) ; toute la couche conversationnelle (`chat`, `ask`, `recall`,
`remember`) est hors sujet.

**Option à terme** : le scraper de `docs/ARCHITECTURE.md` (Playwright +
API Mistral) est déjà un agent sur API payante — la contrainte d'inférence
gratuite ne couvre que le chat. C'est le seul endroit du projet où un vrai
Crew CrewAI (fan-out sur les sources) aurait un sens.

## Alternatives évaluées et écartées

- **Rust** (évalué le 2026-09-09, écarté ; `cargo`/`rustc` 1.95 sont pourtant
  installés). Techniquement solide : **toutes** les options que le SDK Python
  règle sont des flags CLI (`--effort`, `--model`, `--permission-mode`,
  `--resume`, `--fork-session`, `--session-id`, `--output-format json`,
  `--max-budget-usd`, `--fallback-model`, `--settings`), donc un runner qui
  `spawn` le binaire ne perd presque rien ; le pipeline étant séquentiel,
  aucun runtime async n'est nécessaire ; les hooks compilés démarreraient en
  ~1-5 ms contre 30-50 ms en Python. Remplacer ce que CrewAI apporte
  (`@persist`, suspension, `fork`, `plot` → mermaid) coûterait **~280 lignes**.
  Volume total estimé : ~1800-2200 lignes, **~6 j** contre ~3-4 j pour B.
  Écarté au profit de la vitesse de livraison et de l'option « un Crew sur le
  scraper » ; à rouvrir si le venv Python devient un fardeau à l'usage.
- **Option A** (Python nu, sans CrewAI) — voir l'en-tête : recommandée à
  l'origine, écartée pour l'abstraction de flow.
- **Option D** (rester en Bash, extraire les heredocs) — ~3 h, ne traite pas
  la douleur de fond.

## Contrainte de conception imposée par la mesure

Les 2,5 s de démarrage sont **du bruit pour un stage** (qui dure des minutes)
et **inacceptables ailleurs**. D'où une règle d'architecture, non négociable :

> `crewai` n'est importé que par `flow.py` et le chemin d'exécution d'un run
> réel. `--status`, `--costs` et **tous les hooks** doivent s'exécuter sans
> jamais l'importer.

**Corrigé à l'implémentation** : `--dry-run` était dans cette liste, il en est
sorti. Un dry-run traverse le vrai graphe — c'est ce qui lui permet de
prévisualiser les vrais sauts de stage — donc il paie l'import. 2,5 s pour une
prévisualisation est acceptable ; se tromper sur ce qu'un run ferait ne l'est
pas. Un test verrouille la règle sur les deux commandes qui restent
(`test_the_fast_paths_never_import_crewai_or_the_sdk`).

Concrètement : `cli.py` route les commandes rapides vers `ledger.py` /
`docs_state.py` (imports standard uniquement) et ne fait `import flow` qu'au
moment de lancer une boucle. Un hook `PreToolUse` qui paierait 2,5 s
d'import à chaque appel d'outil rendrait la session inutilisable.

## Découpage

Big bang = une PR pour la disparition du `.sh`, mais l'ordre interne compte :

1. Spike `effort` + install CrewAI sur venv 3.13 (bloquant, ~1 h).
2. `config.py`, `docs_state.py`, `ledger.py`, `preflight.py` + pytest — c'est
   du parsing pur, testable sans jamais appeler Claude.
3. `session.py` + `--dry-run` : comparer les prompts générés au **diff exact**
   de ceux du `.sh` (le `.sh` est encore là, c'est le moment de s'en servir).
4. `flow.py` + `cli.py`, parité sur la table des 12 invariants.
5. `review.py` et les hooks.
6. Suppression de `scripts/agent-loop.sh` et `scripts/pr-review.sh`, shim,
   mise à jour de `CLAUDE.md` et de `.claude/settings.json`.

**Critère de sortie** : un round réel complet (business-analyst → code →
create-test → archive) qui merge une PR, ledger écrit, reprise testée après
un halt volontaire.

## Ce qui a été livré, et comment l'équivalence a été prouvée

154 tests (`pipeline/.venv/bin/python -m pytest pipeline/tests`, ~5 s). La
preuve ne repose pas sur une relecture : des **oracles** ont été capturés
depuis les scripts shell avant leur suppression, et les tests comparent la
sortie Python à ces fichiers (`pipeline/tests/oracle/`).

| Ce qui est prouvé | Comment |
| --- | --- |
| Les prompts envoyés aux stages | Diff au bit près contre 3 prompts d'un dry-run réel du `.sh` |
| Le prompt de revue de PR | Diff contre le heredoc expansé par bash lui-même |
| Le parsing du milestone | Diff contre la sortie du heredoc Python du `.sh` |
| La table des coûts | Diff contre la sortie de `agent-loop.sh --costs` |
| Le garde-fou `git push` | 17 cas, mêmes codes de sortie que le hook inline |
| Les haltes de préflight | 3 conditions comparées en exécutant les deux implémentations |
| La séquence des stages | 13 tests de graphe, sans jamais appeler Claude |
| Le chemin rapide sans crewai | Assertion sur `sys.modules` après `--status` / `--costs` |
| La reprise au stage près | Un round halté, puis relancé : seul le stage manquant repart |

**Revue `/code-review` du 2026-09-10** — six findings, tous confirmés en les
reproduisant, tous corrigés et couverts par un test nommé d'après le finding :

1. la phrase de quota était cherchée dans les réponses **réussies** : un stage
   qui *parle* de rate limiting passait pour un stage bloqué, et comme il
   n'était pas marqué fait, le re-run repayait un `/code` déjà mergé ;
2. le rollover `/planner` était actif par défaut — un run opus/high non
   surveillé qui engage le projet sur un item de roadmap que personne n'a
   relu. Il est repassé opt-in, comme dans le shell ;
3. `pipeline.egg-info/` n'était pas ignoré : l'install éditable documentée
   faisait halter le run suivant sur « working tree is dirty » ;
4. une entrée de hook qui ne peut pas charger son module sortait en 1 — non
   bloquant : le garde-fou `push` se taisait au lieu de garder. Les hooks de
   sécurité sortent maintenant en 2, les hooks informatifs en 0 ;
5. la gate humaine bloquait même quand `--stages` ne laissait aucun stage de
   construction à protéger ;
6. un `gh pr comment` en échec levait une `CalledProcessError` nue en avalant
   stderr : deux passes payées perdues sans dire où était le texte.

**Deux bugs trouvés par les tests pendant la migration**, tous deux corrigés :
les post-conditions d'un stage filtré par `--stages` s'exécutaient quand même
(le shell sautait le wrapper entier), et `Path.relative_to` faisait tomber un
run dès qu'un chemin sortait du dépôt.

**Trois divergences voulues**, assumées et documentées :

1. le préambule cite `pipeline/cli/loop.py` comme injecteur ;
2. en `--dry-run`, les post-conditions ne sont plus vérifiées — rien n'a
   tourné. L'ancien dry-run haltait systématiquement sur l'une d'elles ;
3. `pr-review --dry-run` affiche vraiment ses prompts. Dans le shell ils
   étaient avalés par la substitution `findings=$(...)` et n'apparaissaient
   jamais.

Non fait, et su : aucun round réel n'a été lancé — cela dépense de l'argent et
n'a pas été demandé. Le critère de sortie ci-dessus reste donc ouvert.
