"""Caso de Uso: borrar las partidas rapidas que quedan «tiradas por todos» al irse un jugador."""

import logging

from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    QuickMatchActivityInterface,
)
from src.modules.quick_match.application.services.trashed_quick_match_remover import (
    RemovedQuickMatch,
    TrashedQuickMatchRemover,
)
from src.modules.quick_match.domain.repositories.quick_match_unit_of_work_interface import (
    QuickMatchUnitOfWorkInterface,
)
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.user.domain.repositories.user_unit_of_work_interface import (
    UserUnitOfWorkInterface,
)
from src.modules.user.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


class PurgeTrashedQuickMatchesUseCase:
    """
    Una partida rapida se borra de verdad cuando la han tirado todos los que
    siguen teniendo cuenta, y eso solo se miraba al pulsar la papelera. Si Ana la
    tiro, Bea no, y luego se BORRA la cuenta de Bea, la partida ya cumple la
    regla, pero Ana no la ve y nadie vuelve a pulsar nada: se quedaria guardada
    para siempre (Agustin, 26 nov 2026).

    Esta pasada se lanza al borrar una cuenta, con ella ya borrada: mira las
    partidas de ese jugador que alguien tenia en la papelera y borra las que
    ahora tienen tirada todos.

    Cada partida en su transaccion, vuelta a leer con bloqueo. Es una limpieza:
    la que falle se queda como estaba —y se apunta— sin parar a las demas.
    """

    def __init__(
        self,
        uow: QuickMatchUnitOfWorkInterface,
        user_uow: UserUnitOfWorkInterface,
        activity: QuickMatchActivityInterface,
    ):
        self._uow = uow
        self._remover = TrashedQuickMatchRemover(uow, user_uow, activity)

    async def execute(self, gone_player_id: str) -> int:
        """Devuelve cuantas partidas borro."""
        jugador = UserId(gone_player_id)
        async with self._uow:
            candidatas = await self._uow.quick_matches.find_trashed_with_participant(jugador)

        borradas = 0
        for quick_match_id in candidatas:
            try:
                borrada = await self._borrar_si_toca(quick_match_id)
            except Exception:
                logger.warning(
                    "Could not purge quick match %s after its player %s was deleted",
                    quick_match_id.value,
                    jugador.value,
                    exc_info=True,
                )
                continue
            if borrada is not None:
                await self._remover.after_commit(
                    borrada, triggered_by=f"after the account {jugador.value} was deleted"
                )
                borradas += 1
        return borradas

    async def _borrar_si_toca(self, quick_match_id: QuickMatchId) -> RemovedQuickMatch | None:
        async with self._uow:
            quick_match = await self._uow.quick_matches.find_by_id_for_update(quick_match_id)
            if quick_match is None:
                return None
            usuarios = await self._remover.players_of(quick_match)
            return await self._remover.remove_if_trashed_by_everyone(quick_match, usuarios)
