"""Puerto: lo que una partida rapida dejo en Actividad, cuando se borra de verdad."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.modules.user.domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class ForgottenActivity:
    """
    Lo que se llevo de Actividad el borrado de una partida: cuantos eventos, y
    que jugadores tenian por ella su «campo nuevo». Solo a esos hay que cederles
    el logro: ceder a quien no lo tenia publicaria uno que nunca existio.
    """

    events: int = 0
    new_course_holders: tuple[UserId, ...] = ()


class QuickMatchActivityInterface(ABC):
    """
    Lo que `quick_match` necesita de Actividad al borrar una partida, sin
    depender de `social` (26 nov 2026).

    Son dos pasos con garantias distintas, y por eso dos metodos:

    - olvidar lo que la partida publico va DENTRO de la transaccion que la
      borra: o se van las dos cosas o ninguna;
    - ceder el «campo nuevo» va DESPUES, cuando el borrado ya esta guardado, y
      no puede deshacerlo.
    """

    @abstractmethod
    async def forget(self, quick_match_id: str, player_ids: Sequence[UserId]) -> ForgottenActivity:
        """
        Borra, de todos esos jugadores, lo que salio de la partida: como acabo
        y sus logros. Devuelve cuanto borro y a quien hay que ceder despues.

        Corre en la transaccion de quien llama: no confirma nada por su cuenta
        y PROPAGA los fallos. Si no puede olvidar, la partida no se borra: un
        evento que apunta a una partida que ya no existe abre un «no existe».
        """

    @abstractmethod
    async def hand_over_new_course(self, golf_course_id: str, player_ids: Sequence[UserId]) -> None:
        """
        El «campo nuevo» que esos jugadores TENIAN por la partida borrada
        (`ForgottenActivity.new_course_holders`) pasa a la vuelta mas antigua que
        les quede en ese campo, sea un torneo u otra partida rapida.

        Se llama con el borrado ya guardado y NO falla: es un logro, y que no se
        pueda ceder no deshace un borrado hecho.
        """
