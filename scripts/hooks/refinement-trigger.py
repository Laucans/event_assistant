#!/usr/bin/env python3
"""Entree du hook — la logique vit dans pipeline.launcher.hooks.refinement_trigger, ou elle est testee.

Volontairement mince et sans dependance : ce fichier tourne sous le python du
systeme, hors du venv.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pipeline" / "src"))

try:
    from pipeline.launcher.main import main
except Exception as exc:  # pragma: no cover - teste par sous-process
    # Hook informatif : s'il ne peut pas se charger, il ne doit rien bloquer.
    sys.exit(0)

sys.exit(main(["refinement-trigger"]))
