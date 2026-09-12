"""Les binaires dont le pipeline depend, cherches sur le PATH.

Un `shutil.which` nu vivait dans les portes de preflight. Il est ici pour la
meme raison que `git` et `gh` y sont : une porte decide, elle n'appelle pas
le systeme — et ce qui appelle le systeme doit avoir un endroit ou un test
peut glisser son double.
"""

from __future__ import annotations

import shutil


def installed(name: str, which=None) -> bool:
    """`name` est-il sur le PATH ?

    `which` est resolu **a l'appel**, pas en valeur par defaut : un
    `which=shutil.which` dans la signature est capture a l'import, et un test
    qui remplace `binaries.shutil` ensuite ne change alors plus rien — la
    porte continuerait de regarder le vrai PATH de la machine.
    """
    return (which or shutil.which)(name) is not None
