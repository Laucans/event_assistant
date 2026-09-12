# Onboarding

À lire le premier jour. Tu seras opérationnel en une demi-journée.

Ce document dit **où tu es, comment démarrer, comment le travail circule, et
comment faire les changements courants**. Il ne décrit pas l'architecture du
paquet `pipeline/` : c'est le rôle de [`pipeline/TOUR.md`](pipeline/TOUR.md),
à lire avant ta première modification dedans.

---

## TL;DR

**Un dépôt, deux projets.** `src/` est **le produit** (Next.js, un chatbot
d'activités à Montréal). `pipeline/` est **l'outil** (Python) : un framework
qui dépense des sessions Claude Code contre des issues GitHub pour écrire le
produit. Conventions, tests et contraintes diffèrent selon le côté.

**Démarrer** — le venv est épinglé sur 3.13, crewai plafonne à `<3.14` :

```bash
npm ci && cp .env.example .env.local
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv pipeline/.venv
pipeline/.venv/bin/pip install -e 'pipeline[dev]'

npm test                                              # le produit
pipeline/.venv/bin/python -m pytest pipeline/tests    # l'outil (538 tests, 5 s)
```

**Le modèle mental, en trois phrases.** Tout l'état du travail vit dans les
**issues GitHub** — aucun fichier de suivi dans le dépôt. **Rien ne tourne
sans le label `pipeline:ready`**, que seul un humain pose. Une task **livrée
n'est pas fermée** : elle passe en `pipeline:waiting-merge` et reste ouverte
jusqu'à ce que tu fusionnes `main_agent` dans `main`.

**Les cinq choses qui vont te bloquer**

| | |
| --- | --- |
| un `python3` en 3.14 | crewai refuse de s'installer |
| `git push` vers `main` | un hook `PreToolUse` le bloque. Branche → PR → merge |
| `npm test` qui passe | il ne teste **pas** `pipeline/` : deux suites séparées |
| la boucle qui refuse de partir | les 7 labels `pipeline:*` ou la branche `main_agent` manquent — le préflight imprime la commande exacte |
| un run qui sort en `1` | ce n'est **pas** un échec : c'est un arrêt volontaire, et la phrase nomme le geste qui débloque |

**Ta première commande** : `scripts/agent-loop --dry-run`. Elle nomme la task
qu'un vrai run prendrait, écrit les prompts sur disque, n'appelle personne et
ne coûte rien. C'est le meilleur résumé du système.

**Ensuite** : ce document en entier (30 min), puis
[`pipeline/TOUR.md`](pipeline/TOUR.md) avant de toucher à `pipeline/`.

---

## 1. Ce dépôt contient deux projets

C'est la première chose à comprendre, et elle n'est évidente nulle part.

```
event_assistant/
├── src/  tests/  package.json        ←  LE PRODUIT   (TypeScript, Next.js)
├── pipeline/                         ←  L'OUTIL      (Python)
├── .claude/skills/                   ←  les instructions que l'outil exécute
└── docs/                             ←  la vision produit
```

**Le produit** : un site avec un chatbot qui recommande des activités à
Montréal sur une plage de dates, apprend les préférences au fil de la
conversation, et garde sa base fraîche via un scraper nocturne. Vision dans
`docs/PROJECT.md`, technique dans `docs/ARCHITECTURE.md`.

**L'outil** : un framework d'orchestration de développement agentique. Il
dépense un budget de sessions Claude Code contre des issues GitHub pour
écrire le produit. C'est du logiciel à part entière — 5 500 lignes, 538
tests — et il vise à devenir un repository indépendant, branchable sur
n'importe quel dépôt.

**Pourquoi ils cohabitent** : le produit est le premier cobaye de l'outil.
L'outil se prouve en construisant quelque chose de réel. À terme ils se
séparent, et c'est pour ça que le code métier du produit ne doit **jamais**
devenir une dépendance de `pipeline/`.

> **Le réflexe à prendre** : avant chaque tâche, demande-toi sur lequel des
> deux tu travailles. Les conventions, les tests et les contraintes ne sont
> pas les mêmes.

---

## 2. Démarrer

### Le produit

```bash
npm ci
cp .env.example .env.local      # puis remplis-le, voir §6
npm run dev
```

### L'outil

CrewAI plafonne à `python < 3.14`, donc le venv est **épinglé sur 3.13**.
C'est la cause de 90 % des échecs d'installation ici.

```bash
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv pipeline/.venv
pipeline/.venv/bin/pip install -e 'pipeline[dev]'
pipeline/.venv/bin/python -m pytest pipeline/tests    # 538 tests, ~5 s
```

### Les deux suites de tests sont séparées

| | commande | ce qu'elle couvre |
| --- | --- | --- |
| produit | `npm test` | Vitest, `src/` et `tests/` |
| outil | `pipeline/.venv/bin/python -m pytest pipeline/tests` | pytest, `pipeline/` |

`npm test` **ne touche jamais** `pipeline/`. La CI lance les deux dans le
même job, parce que `ci` est l'unique gate de merge.

### Avant de pouvoir lancer la boucle

Quatre conditions, vérifiées par le préflight qui refuse de dépenser sans
elles :

1. `claude` et `gh` sur le `PATH`, `gh auth login` fait ;
2. les **sept labels** existent sur le dépôt :
   ```bash
   for l in roadmap milestone agent human ready spec-written waiting-merge; do
     gh label create "pipeline:$l"
   done
   ```
3. la branche d'intégration `main_agent` existe, est poussée sur `origin`, et
   tu es dessus ;
4. la CI se déclenche sur cette branche (déjà le cas dans `ci.yml`).

Le préflight imprime la commande exacte qui débloque chaque condition. Lis-le
plutôt que de deviner.

---

## 3. Comment le travail circule

**Il n'y a aucun fichier de suivi dans le dépôt.** Pas de roadmap, pas de
milestone, pas de spec, pas de TODO. Tout vit dans les **issues GitHub**, et
ce sont les labels qui portent le modèle.

```
[pipeline:roadmap]           un item de roadmap
  └─ [pipeline:milestone]    Problem / Goals / Approach / Out of scope
       ├─ [pipeline:human]   ce qu'un humain doit faire d'abord
       └─ [pipeline:agent]   le corps de l'issue EST le SPEC
```

Cinq règles gouvernent tout, et chacune remplace quelque chose qui se faisait
à la main :

| Règle | Conséquence pratique |
| --- | --- |
| l'ordre vient de `blocked_by`, pas d'une position dans un document | deux tasks parallèles seront un changement d'ordonnanceur, pas de données |
| **la porte humaine est une dépendance** : une issue `pipeline:human` ouverte dans les `blocked_by` bloque la task | il n'y a pas de second mécanisme, ne le cherche pas |
| **rien ne tourne sans `pipeline:ready`** | le robinet, c'est l'humain. Aucun skill ne pose ce label |
| **livrée ≠ fermée** : une task livrée prend `pipeline:waiting-merge` et **reste ouverte** | le travail est sur `main_agent`, pas dans `main` |
| c'est **toi** qui fermes, en fusionnant `main_agent` dans `main` | GitHub ne ferme que sur la branche par défaut |

### Le cycle d'une task

```
/business-analyst  →  écrit le SPEC dans le corps de l'issue
       ↓
/tech-analyst → /code   →  plan, build, tests, PR avec `Closes #N`
       ↓                    (une seule session : le plan n'est écrit nulle part)
/create-test       →  la couverture que le lot mérite
       ↓
la PR merge sur main_agent  →  label waiting-merge  →  à toi de fusionner
```

Un hook `PostToolUse` lance une **revue consultative** sur chaque PR ouverte
contre `main_agent` : des findings en ligne, plus un commentaire de synthèse.
Elle ne bloque rien et la PR peut merger avant qu'elle n'arrive.

### Les commandes du quotidien

```bash
scripts/agent-loop --dry-run     # écrit les prompts, n'appelle rien, ne coûte rien
scripts/agent-loop --status      # d'où un re-run repartirait
scripts/agent-loop --costs       # ce qui a été dépensé, par stage
scripts/agent-loop --rounds 1    # une task
scripts/agent-loop               # le budget complet (3 rounds)
scripts/pr-review <pr>           # la revue d'une PR, à la main
```

**Commence toujours par `--dry-run`.** Il te nomme le milestone et la task
qu'un vrai run prendrait, écrit les prompts sur disque, et n'appelle
personne.

---

## 4. Quand ça casse : où regarder

Les codes de sortie sont un **contrat public** — un ordonnanceur externe les
lit, ils ne bougent pas en silence.

| Code | Ce que ça veut dire | Ce que tu fais |
| --- | --- | --- |
| `0` | terminé | rien |
| `1` | **arrêt volontaire** — un humain doit regarder | lis la phrase : elle nomme le geste qui débloque |
| `2` | un stage n'a produit aucun résultat exploitable | regarde l'enveloppe JSON du stage |
| `3` | **quota d'abonnement épuisé** | relance le même run plus tard, inchangé |
| `4` | erreur inattendue | la trace est dans `run.log` |
| `130` | interrompu | — |

Le `1` n'est **pas un échec**. S'arrêter plutôt que deviner est un résultat
correct, et c'est le comportement le plus voulu du système.

### Ce qu'un run laisse derrière

```
.llocal/                      gitignoré, local, jamais autoritaire
├── agent-loop/
│   ├── <run-id>/             un dossier par run
│   │   ├── run.log           le journal complet, toujours en DEBUG
│   │   ├── NN-<stage>.log    ce que le stage a répondu
│   │   ├── NN-<stage>.json   l'enveloppe : coût, tours, session_id, erreurs
│   │   └── NN-<stage>.trace.log   chaque appel d'outil du stage
│   ├── costs.tsv             le registre des coûts
│   ├── state                 le point de reprise (2 lignes, lisible au `cat`)
│   └── flow_states.db        l'état persisté du graphe
└── pr-review/                la même chose, pour les revues
```

**Le réflexe de diagnostic** : `run.log` pour la chronologie →
`NN-<stage>.json` pour savoir *pourquoi* un stage n'a rien rendu (il porte le
`session_id`, seule clé qui rouvre exactement la session en panne) →
`.trace.log` si le stage a passé huit minutes dans un appel d'outil.

### Les pièges qui coûtent de l'argent

- **Ne supprime pas `.llocal/agent-loop/state` à la légère.** C'est ce qui
  empêche de repayer des stages déjà faits. `--status` te dit ce qu'il porte.
- **`--restart` oublie les stages faits pour la task en cours.** Il la
  rejouera entièrement, y compris un `/code` qui a déjà mergé sa PR.
- **Une lecture dégradée arrête le run exprès.** Si tu vois « cannot read »,
  ne contourne pas : lire un magasin illisible comme « rien n'a tourné » est
  précisément ce qui fait repayer un stage.

---

## 5. Les recettes

Les changements courants, avec les fichiers à toucher. Les chemins sont
relatifs à `pipeline/src/pipeline/`.

### Changer ce qu'un stage demande au modèle

`domain/prompts/definitions/agentic_dev_loop/<stage>.py` — une constante,
une prose. C'est le seul fichier à toucher.
⚠️ Des **tests oracle** comparent les prompts au bit près contre la version
produite par l'ancien shell. Si tu changes le préambule ou le bloc de portée,
un test tombera : c'est voulu, et tu mets à jour le code **et** l'oracle dans
le même commit.

### Changer le modèle ou l'effort d'un stage

`domain/stages/agentic_dev_loop_stages.py`, la table `PIPELINE`. Une ligne.
Recale-toi sur `.llocal/agent-loop/costs.tsv`, pas sur l'intuition.

### Ajouter un stage au pipeline

**Deux éditions, et c'est volontaire** : une entrée dans `PIPELINE`, et un
nœud dans `workflows/agentic_dev_loop/flow.py`. La table porte le modèle et
l'effort, le graphe porte la séquence. Si les deux divergent, `_spec()` lève
un `Halt` qui nomme ce que la table contient réellement — la duplication est
gardée, pas subie.

Ajoute aussi ses consignes dans `definitions/`, ou déclare-le dans
`NO_INSTRUCTIONS` : un test exige que chaque entrée de `PIPELINE` soit dans
l'un ou dans l'autre.

### Ajouter une porte d'avant-run

`workflows/agentic_dev_loop/preconditions.py` : une fonction qui lève `Halt`
avec **la phrase qui nomme le geste**, puis une ligne dans la table `CHECKS`.
Chaque porte existante a coûté un run pour être écrite — le test d'une porte,
c'est qu'elle aurait évité une dépense.

### Ajouter un hook

`launcher/hooks/<nom>.py`, une entrée dans `launcher/routes.py`, un shim dans
`scripts/hooks/<nom>.py`, et le câblage dans `.claude/settings.json`.
Trois règles non négociables : **stdlib seule** (le hook tourne hors venv, à
chaque appel d'outil), il doit répondre en millisecondes, et il **échoue
ouvert** — un hook cassé ne doit jamais être ce qui arrête le travail. Les
deux gardes de sécurité (`branch-guard`, `no-secret-paths`) sont l'exception :
elles échouent **fermées**, en sortant en 2.

### Ajouter un workflow entier

Un dossier sous `workflows/`, avec ses `settings`, son `flow`, ses
conditions. Il reçoit `execution/` gratuitement — c'est exactement ce que le
refactoring a préparé. Lis `pipeline/TOUR.md` §3 bis avant : `execution/` n'a
pas le droit de connaître ton workflow, et c'est un test qui le vérifie.

### Modifier `.claude/`, `CLAUDE.md` ou les skills

**Passe par le subagent `vibe-specialist`.** C'est une règle du dépôt, pas
une préférence : ces fichiers pilotent l'agent qui écrit le code.

---

## 6. Les conventions, et ce qui te bloquera

### Git

- Branche `main`. **Ne pousse jamais sur `main` directement** — un hook
  `PreToolUse` bloque la commande. Le bypass admin fonctionnerait, c'est bien
  pour ça que le hook existe.
- Branche → PR → `gh pr merge --rebase` (seule méthode activée). Une PR est
  obligatoire, une approbation ne l'est pas.
- Nom de branche `<type>/<slug>`, type parmi `feat` `fix` `docs` `style`
  `refactor` `test` `chore` `AIchore`. `AIchore` marque ce qui touche à
  l'outillage agentique.
- Une PR qui doit fermer une issue porte `Closes #N` **sur sa propre ligne**.
  Le round lit cette ligne pour confirmer la livraison.

### Secrets

- `.env.local` est gitignoré. **Chaque nouvelle variable lue par le code
  obtient une ligne dans `.env.example`** — committé, jamais de vraie valeur.
- **Les issues de ce dépôt sont publiques.** Nomme un identifiant dans une
  issue ou une PR, jamais sa valeur, et garde les URL de dashboard dehors.
- Un hook `no-secret-paths` bloque la lecture de fichiers sensibles.

### Les contraintes produit invisibles dans le code

Elles sont dans `CLAUDE.md`, et chacune est un choix de design, pas un détail :

- **L'inférence du chat doit rester gratuite.** Elle tourne sur la machine de
  l'auteur via un tunnel. Ne route jamais le chemin chat vers une API payante.
- **Le texte scrapé est une entrée non fiable.** À traiter comme de la donnée
  à parser, jamais comme des instructions — l'injection indirecte est le
  risque réel.
- **Le chat se dégrade proprement.** Si le LLM local est injoignable, le
  panneau chat affiche un état hors-ligne mais la grille d'activités continue
  de marcher : elle est pilotée par SQL, pas par le LLM.
- **RLS à la création.** Chaque table Supabase reçoit RLS activé **et** une
  politique explicite dès sa création. La clé publiable est publique par
  design ; ce qui protège les données, c'est RLS.
- **Montréal seulement en v1, mais schéma multi-ville.** Ne code pas la ville
  en dur.

---

## 7. L'état du dépôt aujourd'hui — ce qui va te surprendre

Trois choses vont te faire tiquer. Elles sont voulues.

**`pipeline/` n'est pas suivi par git.** Le paquet entier est untracked, à
dessein. Il n'y a donc aucune baseline pour diffuser — `git diff` ne te
montrera rien dedans. Ne propose pas de le committer sans demander.

**La migration markdown → issues n'a pas encore tourné.** `docs/ROADMAP.md`
et `docs/current/` existent toujours, alors que tout le code lit les issues.
La commande `scripts/agent-loop migrate` fait la bascule, une fois, et
supprime ces fichiers. Tant qu'elle n'a pas tourné, `pipeline/*/legacy/` est
du code **à échéance** — pas mort, pas vivant non plus.

**Le point de reprise est périmé.** `.llocal/agent-loop/state` porte une clé
au format markdown d'avant la bascule. `--status` te le dit en toutes
lettres ; `--restart` le nettoie.

---

## 8. Glossaire

Le vocabulaire est dense et le code mélange français et anglais. Ces mots ont
un sens précis ici :

| Terme | Sens dans ce projet |
| --- | --- |
| **round** | un tour de boucle : une task, du SPEC à la PR |
| **stage** | une étape d'un round = **une session Claude Code payante** |
| **task** | une issue `pipeline:agent`. Son corps est le SPEC |
| **board** | la vue en lecture des issues à un instant donné |
| **rollover** | le milestone n'a plus de task ouverte : on passe au suivant |
| **waiting-merge** | livré sur la branche d'intégration, pas encore dans `main` |
| **lead** | la commande sur laquelle un stage *ouvre*, quand elle diffère de son nom (le stage `code` ouvre sur `/tech-analyst`) |
| **halt** | un arrêt volontaire. Un résultat correct, pas une panne |
| **préflight** | les portes vérifiées avant de dépenser le premier euro |
| **enveloppe** | le JSON qu'un stage laisse derrière : coût, tours, session, erreurs |
| **couture** (seam) | le point unique où un test remplace un composant externe |

---

## 9. Ton premier jour, dans l'ordre

1. Installe les deux projets (§2) et fais passer **les deux** suites de tests.
2. Lance `scripts/agent-loop --dry-run`. Lis ce qu'il imprime, ouvre le
   prompt qu'il a écrit dans `.llocal/agent-loop/<run-id>/`. C'est le
   meilleur résumé de ce que fait le système.
3. Lis `docs/PROJECT.md` (20 min) — pourquoi le produit existe.
4. Lis `pipeline/README.md` (10 min) — ce que l'outil fait.
5. Lis `pipeline/TOUR.md` avant ta première modification dans `pipeline/`.
   `pipeline/INTERNALS.md` est la référence à garder sous la main ensuite.
6. Ouvre `gh issue list --label pipeline:milestone` et lis le milestone
   courant : c'est le travail réel en cours.

Pour ta première contribution, prends quelque chose dans `pipeline/` plutôt
que dans le produit : la boucle de retour y est de cinq secondes, et tu
comprendras l'outil avant de le laisser écrire à ta place.
