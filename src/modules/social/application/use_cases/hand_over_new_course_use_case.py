"""Caso de Uso: ceder el «campo nuevo» de una partida rapida que se ha borrado."""

import logging
from collections.abc import Collection, Sequence
from typing import Protocol

from src.modules.social.application.exclusive_achievements import first_on_each_course
from src.modules.social.application.ports.player_course_history_interface import (
    PlayerCourseHistoryInterface,
)
from src.modules.user.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


class _QuickMatchHeir(Protocol):
    async def republish_new_course(
        self, quick_match_id_raw: str, only_for: Collection[UserId] | None = None
    ) -> int: ...


class _TournamentHeir(Protocol):
    async def republish_exclusive(self, competition_id_raw: str, user_ids: list[UserId]) -> int: ...


class HandOverNewCourseUseCase:
    """
    «Campo nuevo» es de la vuelta mas antigua de un jugador en un campo. Si esa
    vuelta era una partida rapida que se borra, el logro no desaparece: pasa a
    la mas antigua que le QUEDE alli, sea otra partida rapida o un torneo
    cerrado (Agustin, 26 nov 2026). Es lo mismo que pasa al reabrir un torneo
    (`CompetitionActivityPublisher._ceder_los_exclusivos`).

    Se ejecuta con el borrado ya guardado, asi que el historial ya no cuenta la
    partida borrada. Volver a publicar es idempotente y pasa por la regla de
    siempre: si la heredera ya lo tenia, o no es la mas antigua, no cambia nada.
    Si el logro estaba oculto, llega oculto: lo dice el apunte que deja
    `forget_source`.

    Con fallo seguro: es un logro, y no poder cederlo no deshace el borrado. Lo
    que falle en una heredera no para a las demas.
    """

    def __init__(
        self,
        history: PlayerCourseHistoryInterface,
        quick_matches: _QuickMatchHeir,
        tournaments: _TournamentHeir,
    ):
        self._history = history
        self._quick_matches = quick_matches
        self._tournaments = tournaments

    async def execute(self, golf_course_id: str, player_ids: Sequence[UserId]) -> None:
        jugadores = list(dict.fromkeys(player_ids))
        if not jugadores:
            return
        try:
            rondas = await self._history.played_rounds(jugadores)
        except Exception:
            logger.warning(
                "Could not find who inherits the new course %s", golf_course_id, exc_info=True
            )
            return

        partidas: dict[str, list[UserId]] = {}
        torneos: dict[str, list[UserId]] = {}
        for (jugador, campo), primera in first_on_each_course(rondas).items():
            if campo != golf_course_id:
                continue
            if primera.competition_id is None:
                partidas.setdefault(primera.source_id, []).append(jugador)
            else:
                torneos.setdefault(primera.competition_id, []).append(jugador)

        # Solo para sus herederos, como con los torneos: republicar la partida
        # entera daria el logro a otro jugador suyo que no lo tenia
        for partida, herederos in sorted(partidas.items()):
            try:
                await self._quick_matches.republish_new_course(partida, herederos)
            except Exception:
                logger.warning(
                    "Could not hand the new course over to quick match %s", partida, exc_info=True
                )
        for torneo, herederos in sorted(torneos.items()):
            try:
                await self._tournaments.republish_exclusive(torneo, herederos)
            except Exception:
                logger.warning(
                    "Could not hand the new course over to tournament %s", torneo, exc_info=True
                )
