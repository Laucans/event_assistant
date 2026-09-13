"""Tout ce qui touche a l'exterieur, emballe derriere une interface a nous.

Un sous-paquet par composant externe : le moteur d'agent (`agent/`), les
binaires du systeme (`shell/`), les fichiers que la boucle ecrit et relit
(`store/`) ; `hub.py` est le seul endroit qui les construit. Le reste du
paquet parle a ces interfaces, jamais aux bibliotheques qu'elles enveloppent.
"""
