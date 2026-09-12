# Fermer les `pipeline:waiting-merge` par cron

État : **à faire.** Décidé le 2026-09-10, volontairement reporté. Aujourd'hui
le geste est manuel.

## Le problème

Une task livrée ne se ferme pas toute seule. Quand la PR de `/code` merge
dans `main_agent` avec `Closes #N`, le round pose `pipeline:waiting-merge` et
laisse l'issue **ouverte** : le travail est sur la branche d'intégration, pas
dans `main`, et la fermer dirait le contraire.

GitHub ne prendra pas le relais à la fusion suivante. Il ne ferme une issue
liée qu'au merge dans la branche **par défaut**, et le `Closes #N` vit dans le
corps de la PR d'origine — un `--rebase` ne le reporte pas dans les messages
de commit. Donc rien, nulle part, ne referme ces issues.

## Aujourd'hui

C'est vous, à la main, en fusionnant `main_agent` dans `main`. Le risque
assumé est l'oubli : des issues restent en `waiting-merge` indéfiniment et
personne ne le signale. La boucle, elle, ne s'en trouve pas bloquée — une
task `waiting-merge` ne bloque plus sa suivante.

Le seul endroit où l'oubli se voit : quand **toutes** les tasks d'un
milestone sont en `waiting-merge`, le run s'arrête sur
`Everything is delivered on the integration branch and waiting for you to
merge it` au lieu d'ouvrir le milestone suivant. C'est un garde-fou, pas une
alerte : il faut lancer la boucle pour le lire.

## Ce qu'il faudrait

Un cron qui, périodiquement :

1. liste les issues ouvertes portant `pipeline:waiting-merge` ;
2. pour chacune, retrouve la PR mergée qui porte `Closes #N`
   (`GitHub.merged_pr_closing`, déjà écrit) ;
3. vérifie que le commit de merge de cette PR est **ancêtre de `main`** —
   c'est ça, et pas la date, qui prouve l'intégration ;
4. ferme l'issue et retire l'étiquette.

Les briques 1, 2 et 4 existent déjà dans `adapters/shell/github.py`
(`issues_labelled`, `merged_pr_closing`, `close_issue`, `remove_label`).
La seule à écrire est la 3.

## Pourquoi pas tout de suite

Trois raisons, dans l'ordre :

- **rien n'a encore tourné pour de vrai.** Aucune issue n'existe sur le dépôt,
  et les endpoints sous-issues/dépendances ne sont prouvés que contre le
  double de test. Automatiser une fermeture avant d'avoir vu une seule
  ouverture, c'est écrire à l'aveugle ;
- **c'est une écriture GitHub non sollicitée**, déclenchée par une horloge et
  pas par une commande. Elle mérite d'être ajoutée une fois que le flux
  manuel a fait ses preuves ;
- **le geste manuel est de toute façon nécessaire** — quelqu'un doit décider
  de fusionner `main_agent` dans `main`. Le cron n'automatise que le
  rangement qui suit, pas la décision.
