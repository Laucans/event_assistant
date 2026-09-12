#!/usr/bin/env python3
"""Entree du hook — la logique vit dans pipeline.launcher.hooks.branch_guard, ou elle est testee.

Volontairement mince et sans dependance : ce fichier tourne sous le python du
systeme a chaque appel d'outil, hors du venv.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pipeline" / "src"))

try:
    from pipeline.launcher.main import main
except Exception as exc:  # pragma: no cover - teste par sous-process
    # Hook de securite : s'il ne peut pas se charger, il doit bloquer bruyamment.
    # Sortir en 1 ferait taire la garde sans que personne ne le voie (seul le
    # code 2 bloque un PreToolUse).
    sys.stderr.write("le garde-fou push ne peut pas se charger (%s) — appel bloque.\n" % exc)
    sys.exit(2)

sys.exit(main(["branch-guard"]))
