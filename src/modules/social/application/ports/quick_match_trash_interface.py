"""Puerto: que partidas rapidas tiene cada autor en su papelera."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.user.domain.value_objects.user_id import UserId


class QuickMatchTrashInterface(ABC):
    """
    Lo que el feed necesita saber de la papelera de partidas rapidas.

    Si un jugador manda una partida rapida a su papelera, lo que salio de ella
    —el «como acabo» y sus logros— deja de verse en Actividad: lo suyo, a todos
    y tambien a el; y a el, ademas, lo de los otros jugadores de esa partida
    (prueba de punta a punta, 22 oct 2026; ampliado el 26 nov 2026). La
    papelera es de cada uno y definitiva: la de otro jugador no oculta a un
    tercero lo del que no la tiro. Es un puerto porque `social` no lee las
    tablas de partidas rapidas.
    """

    @abstractmethod
    async def trashed_by_author(
        self, pairs: Sequence[tuple[str, UserId]]
    ) -> set[tuple[str, UserId]]:
        """
        De esas parejas (partida, jugador), las de partidas rapidas que ese
        jugador tiene en su papelera, en una sola lectura. El feed pregunta por
        el autor de cada evento y por quien mira. Un id ilegible, que no es de
        una partida rapida, o de una que el jugador no jugo, no cuenta.
        """
