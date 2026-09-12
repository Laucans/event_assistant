"""Tout ce qui touche a l'exterieur, emballe derriere une interface a nous.

Un sous-paquet par composant externe : le moteur d'agent (`agent/`), le moteur
de graphe (`engine/`), les binaires du systeme (`shell/`), les fichiers que la
boucle ecrit et relit (`store/`). Le reste du paquet parle a ces interfaces,
jamais aux bibliotheques qu'elles enveloppent.
"""
