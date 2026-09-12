"""L'etat d'un round, separe du graphe qui le fait avancer."""

from __future__ import annotations

from pydantic import BaseModel

from pipeline.core.domain.outcomes.result import Result, Status


class RoundState(BaseModel):
    """L'etat d'un round. Persiste tel quel par le moteur apres chaque noeud.

    Les corps des deux issues y sont : c'est la portee que chaque stage
    recoit, et une reprise doit la retrouver telle quelle plutot que
    dependre de ce que l'API repondra la prochaine fois.

    L'arret y est aussi, et il le faut : un noeud du graphe qui rend un
    `Result` en echec n'arrete rien tout seul — le moteur declenche le noeud
    suivant. C'est `stopped` que chaque noeud lit pour ne pas partir, et qui
    permet au round de rendre, apres coup, la raison exacte pour laquelle il
    s'est arrete la.
    """

    id: str = ""
    task_num: str = ""
    task_title: str = ""
    task_body: str = ""
    task_key: str = ""
    kind: str = "auto"
    milestone_num: str = ""
    milestone_title: str = ""
    milestone_body: str = ""
    spec_written: bool = False
    stages_done: list[str] = []
    rollover: bool = False
    # L'arret, garde parce que le graphe ne peut pas le porter lui-meme.
    stopped: bool = False
    stop_status: str = ""
    stop_reason: str = ""

    def record(self, failure: Result) -> Result:
        """Garde l'echec dans l'etat, et le rend pour que l'appelant propage.

        Les deux a la fois : l'etat est ce que les noeuds suivants liront
        pour ne pas partir, le retour est ce que le noeud courant propage.
        """
        self.stopped = True
        self.stop_status = failure.status.value
        self.stop_reason = failure.reason
        return failure

    def starts_a_round(self) -> None:
        """Oublie l'arret du round precedent, au debut d'un round repris.

        L'etat est persiste **avec** son arret : c'est ce qui permet a la
        boucle de relire, apres le kickoff, pourquoi le round s'est arrete.
        Mais un round repris repart de cet etat-la, et sans ce nettoyage
        chaque garde le lirait comme « ce round est deja arrete » — le round
        repris ne ferait rien du tout, et `/create-test` ne serait jamais
        rejoue. L'arret appartient au round qui l'a enregistre, pas au
        suivant.
        """
        self.stopped = False
        self.stop_status = ""
        self.stop_reason = ""

    @property
    def halt(self) -> Result[None]:
        """L'arret enregistre, relu depuis l'etat apres le round."""
        if not self.stopped:
            return Result.of(None)
        return Result(status=Status(self.stop_status), reason=self.stop_reason)
