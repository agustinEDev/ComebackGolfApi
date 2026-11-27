"""Servicio de aplicacion: borrar de verdad una partida rapida que ya tiraron todos."""

import logging
from dataclasses import dataclass

from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    ForgottenActivity,
    QuickMatchActivityInterface,
)
from src.modules.quick_match.domain.entities.quick_match import QuickMatch
from src.modules.quick_match.domain.repositories.quick_match_unit_of_work_interface import (
    QuickMatchUnitOfWorkInterface,
)
from src.modules.quick_match.domain.value_objects.participant_id import ParticipantId
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.repositories.user_unit_of_work_interface import (
    UserUnitOfWorkInterface,
)
from src.modules.user.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemovedQuickMatch:
    """Lo que hace falta de una partida ya borrada para cerrar el borrado tras el commit."""

    quick_match_id: str
    golf_course_id: str
    players: tuple[UserId, ...]
    forgotten: ForgottenActivity


class TrashedQuickMatchRemover:
    """
    El borrado de verdad de una partida rapida, en UN sitio (26 nov 2026). Lo
    disparan dos cosas: la papelera del ultimo jugador que faltaba, y el borrado
    de una cuenta, que puede dejar «tiradas por todos» partidas que su dueño no
    habia tirado.

    Va en dos tiempos, que quien llama respeta:

    - `remove_if_trashed_by_everyone`, DENTRO de su transaccion y con la partida
      bloqueada: decide con la regla del dominio y, si toca, olvida lo que
      publico en Actividad y borra la partida. O las dos cosas o ninguna.
    - `after_commit`, ya guardado: deja registro y cede el «campo nuevo».
    """

    def __init__(
        self,
        uow: QuickMatchUnitOfWorkInterface,
        user_uow: UserUnitOfWorkInterface,
        activity: QuickMatchActivityInterface,
    ):
        self._uow = uow
        self._user_uow = user_uow
        self._activity = activity

    async def players_of(self, quick_match: QuickMatch) -> dict[UserId, User]:
        """
        Los jugadores con cuenta que siguen existiendo, por su id. Se leen SIN
        abrir la unidad de trabajo de usuarios: comparte sesion con la de la
        partida, y al cerrarse confirmaria a media transaccion.
        """
        jugadores = [p.user_id for p in quick_match.participants if p.user_id is not None]
        return {u.id: u for u in await self._user_uow.users.find_by_ids(jugadores)}

    async def remove_if_trashed_by_everyone(
        self, quick_match: QuickMatch, users: dict[UserId, User]
    ) -> RemovedQuickMatch | None:
        """
        Si la han tirado todos los que siguen teniendo la cuenta activa, la
        borra con lo que publico; si no, no toca nada y devuelve None.
        """
        activos = [ParticipantId(u.id.value) for u in users.values() if u.is_active]
        if not quick_match.is_trashed_by_everyone(activos):
            return None

        # De todos los que la jugaron con cuenta, sigan o no: la partida ya no existe
        jugadores = tuple(p.user_id for p in quick_match.participants if p.user_id is not None)
        olvidado = await self._activity.forget(str(quick_match.id.value), jugadores)
        await self._uow.quick_matches.delete(quick_match)
        return RemovedQuickMatch(
            quick_match_id=str(quick_match.id.value),
            golf_course_id=str(quick_match.golf_course_id.value),
            players=jugadores,
            forgotten=olvidado,
        )

    async def after_commit(self, removed: RemovedQuickMatch, *, triggered_by: str) -> None:
        """
        Con el borrado ya guardado. Un borrado que no tiene vuelta, y de datos de
        varios jugadores, deja dicho que lo disparo y que se llevo: solo
        identificadores. Y el «campo nuevo» pasa a quien lo tenia por esta
        partida; a los demas les publicaria un logro que nunca existio.
        """
        logger.info(
            "Quick match %s deleted for good: trashed by every active player (%s). "
            "Players: %s. It took %d activity events with it.",
            removed.quick_match_id,
            triggered_by,
            ", ".join(str(j.value) for j in removed.players),
            removed.forgotten.events,
        )
        if removed.forgotten.new_course_holders:
            await self._activity.hand_over_new_course(
                removed.golf_course_id, removed.forgotten.new_course_holders
            )
