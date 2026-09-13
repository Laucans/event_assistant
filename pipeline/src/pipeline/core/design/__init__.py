"""Ce qu'on ecrit pour declarer un workflow, plutot que pour en implementer un.

`blueprint` porte la declaration — un nom, une config, des portes, une forme,
ce qu'il doit avoir obtenu. `build` en fait un objet conforme a
`execution.contract.Workflow`, que le lanceur appelle sans savoir qu'il a ete
declare plutot qu'ecrit.

La difference avec `execution/` : la, ce qui fait tourner ; ici, ce qu'on
remplit. Les deux couches sont dans `core/` parce que ni l'une ni l'autre ne
connait un workflow — un `Blueprint` recoit sa forme et ses portes, il ne les
importe pas.

**Une facilite, jamais un carcan.** `contract.Workflow` reste un `Protocol` :
un workflow qui ne rentre pas dans une forme ecrit ses six membres a la main,
et rien en aval ne fait la difference.
"""

from pipeline.core.design.blueprint import Blueprint
from pipeline.core.design.build import workflow

__all__ = ["Blueprint", "workflow"]
