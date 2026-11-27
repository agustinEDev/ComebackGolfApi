"""Caso de Uso: olvidar lo que publico una partida rapida que se borra de verdad."""

from collections.abc import Sequence

from src.modules.social.application.exclusive_achievements import lock_players
from src.modules.social.domain.repositories.social_unit_of_work_interface import (
    SocialUnitOfWorkInterface,
)
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.user.domain.value_objects.user_id import UserId


class ForgetQuickMatchActivityUseCase:
    """
    Borra de Actividad, para todos sus jugadores, lo que salio de una partida
    rapida: como acabo y sus logros (26 nov 2026).

    Corre DENTRO de la transaccion que borra la partida, sobre la misma sesion:
    por eso no abre su unidad de trabajo —al cerrarla confirmaria a media
    transaccion— ni se traga los fallos. O se van la partida y su rastro, o no
    se va nada.

    Toma los candados de los jugadores, como quien publica: asi un logro que se
    este publicando a la vez no se cruza con el borrado. Quien llama ya tiene
    bloqueada la partida, que es el orden de siempre: primero la partida, luego
    los jugadores.
    """

    def __init__(self, social_uow: SocialUnitOfWorkInterface):
        self._social_uow = social_uow

    async def execute(
        self, quick_match_id: str, player_ids: Sequence[UserId]
    ) -> tuple[int, list[UserId]]:
        """
        Devuelve cuantos eventos borro y que jugadores tenian por esta partida su
        «campo nuevo»: solo a esos hay que cederselo despues. Ceder a quien no
        lo tenia —una partida cancelada, o una que no fue su primera vez en el
        campo— publicaria un logro que nunca existio.
        """
        repo = self._social_uow.activity_events
        await lock_players(repo, player_ids)
        con_campo_nuevo = sorted(
            {
                evento.user_id
                for evento in await repo.find_from_source(
                    quick_match_id, [ActivityEventType.NEW_COURSE]
                )
                if evento.comes_from_a_quick_match
            },
            key=lambda user_id: str(user_id.value),
        )
        tipos = [t for t in ActivityEventType if t.may_come_from_a_quick_match]
        return await repo.forget_source(quick_match_id, tipos), con_campo_nuevo
