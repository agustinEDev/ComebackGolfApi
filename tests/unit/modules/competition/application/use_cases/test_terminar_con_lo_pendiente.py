"""
Terminar una competición con algo sin cerrar (I1, decidido por Agustín el 22 nov 2026).

`POST /competitions/{id}/complete` no termina mientras quede un partido de la Ryder
sin acabar (SCHEDULED o IN_PROGRESS) o una partida de stroke play sin acabar (no
COMPLETED): 409 PENDING_GAMES con cuántos de cada. No se toca nada.

| Caso                                                   | Resultado                          |
|--------------------------------------------------------|------------------------------------|
| Un partido sin empezar                                 | PendingGamesError(1, 0), sin tocar |
| Un partido en juego                                    | PendingGamesError(1, 0)            |
| Partidos completado, por WO y concedido                | se termina                         |
| Una partida sin salir o en el campo                    | PendingGamesError(0, 1)            |
| Una partida cerrada                                    | se termina                         |
| Dos partidos y una partida pendientes                  | PendingGamesError(2, 1)            |
| Lo pendiente de otra competición                       | no cuenta                          |
| Quien no es el organizador, con algo pendiente         | 403, como siempre                  |
| Sin empezar (CLOSED), con algo pendiente               | error de estado, como siempre      |
| Con la competición bloqueada                           | find_by_id_for_update              |
| Quien no puede (revisión 22 nov)                       | 403 sin bloquear nada (BE #309)    |
| Terminada mientras esperaba el bloqueo                 | error de estado de lo releído      |
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.modules.competition.application.dto.competition_dto import (
    CompleteCompetitionRequestDTO,
)
from src.modules.competition.application.exceptions import (
    NotCompetitionCreatorError,
    PendingGamesError,
)
from src.modules.competition.application.use_cases.complete_competition_use_case import (
    CompleteCompetitionUseCase,
)
from src.modules.competition.domain.entities.competition import CompetitionStateError
from src.modules.competition.domain.value_objects.competition_status import CompetitionStatus
from src.modules.competition.domain.value_objects.estado_partida import EstadoPartida
from src.modules.competition.domain.value_objects.match_status import MatchStatus
from src.modules.user.domain.value_objects.user_id import UserId
from tests.unit.modules.competition.application.use_cases.test_change_enrollment_tee_use_case import (
    _Mundo,
)

pytestmark = pytest.mark.asyncio


async def _en_curso() -> _Mundo:
    mundo = await _Mundo().montar()
    await mundo.cerrar()
    await mundo.empezar()
    return mundo


async def _terminar(mundo: _Mundo, quien: UserId | None = None):
    return await CompleteCompetitionUseCase(mundo.uow).execute(
        CompleteCompetitionRequestDTO(competition_id=mundo.competition_id.value),
        quien or mundo.organizador,
    )


async def _estado(mundo: _Mundo) -> CompetitionStatus:
    return (await mundo.uow.competitions.find_by_id(mundo.competition_id)).status


async def _cambiar_partido(mundo: _Mundo, partido_id, cambio) -> None:
    async with mundo.uow:
        partido = await mundo.uow.matches.find_by_id(partido_id)
        cambio(partido)
        await mundo.uow.matches.update(partido)
        await mundo.uow.commit()


class TestPartidosDeLaRyder:
    @pytest.mark.parametrize("empezado", [False, True])
    async def test_a_match_not_finished_stops_it_and_nothing_changes(self, empezado):
        """
        Given la Ryder en curso con un partido sin empezar o en juego
        When el organizador la termina
        Then PendingGamesError con 1 partido y 0 partidas (PENDING_GAMES); la
            competición sigue en curso y el partido como estaba
        """
        mundo = await _en_curso()
        partido = await mundo.partido([mundo.jugadora], [mundo.otro], empezado=empezado)

        with pytest.raises(PendingGamesError) as error:
            await _terminar(mundo)

        assert (error.value.partidos, error.value.partidas) == (1, 0)
        assert error.value.error_code == "PENDING_GAMES"
        assert await _estado(mundo) == CompetitionStatus.IN_PROGRESS
        esperado = MatchStatus.IN_PROGRESS if empezado else MatchStatus.SCHEDULED
        assert (await mundo.el_partido(partido)).status == esperado

    async def test_finished_matches_let_it_finish(self):
        """
        Given la Ryder en curso con un partido completado, uno por WO y uno concedido
        When el organizador la termina
        Then se termina
        """
        mundo = await _en_curso()
        completado = await mundo.partido([mundo.jugadora], [mundo.otro], empezado=True)
        por_wo = await mundo.partido([mundo.capitana], [mundo.capitan_b])
        concedido = await mundo.partido([mundo.jugadora], [mundo.capitan_b], empezado=True)
        await _cambiar_partido(mundo, completado, lambda p: p.complete({"winner": "A"}))
        await _cambiar_partido(mundo, por_wo, lambda p: p.declare_walkover("A"))
        await _cambiar_partido(mundo, concedido, lambda p: p.concede("B"))

        respuesta = await _terminar(mundo)

        assert respuesta.status == "COMPLETED"
        assert await _estado(mundo) == CompetitionStatus.COMPLETED


class TestPartidasDeStrokePlay:
    @pytest.mark.parametrize("empezada", [False, True])
    async def test_a_group_not_finished_stops_it(self, empezada):
        """
        Given la competición en curso con una partida sin salir o en el campo
        When el organizador la termina
        Then PendingGamesError con 0 partidos y 1 partida, y la partida como estaba
        """
        mundo = await _en_curso()
        partida = await mundo.partida_con(mundo.jugadora, empezada=empezada)

        with pytest.raises(PendingGamesError) as error:
            await _terminar(mundo)

        assert (error.value.partidos, error.value.partidas) == (0, 1)
        esperado = EstadoPartida.IN_PROGRESS if empezada else EstadoPartida.SCHEDULED
        assert (await mundo.la_partida(partida)).estado == esperado

    async def test_a_closed_group_lets_it_finish(self):
        """
        Given la competición en curso con su partida cerrada por el organizador
        When la termina
        Then se termina
        """
        mundo = await _en_curso()
        partida_id = await mundo.partida_con(mundo.jugadora, empezada=True)
        async with mundo.uow:
            partida = await mundo.uow.partidas.find_by_id(partida_id)
            partida.cerrar(completas=[mundo.jugadora])
            await mundo.uow.partidas.guardar([partida])
            await mundo.uow.commit()

        await _terminar(mundo)

        assert await _estado(mundo) == CompetitionStatus.COMPLETED


class TestCuantos:
    async def test_counts_every_pending_match_and_group(self):
        """
        Given dos partidos sin acabar, uno acabado y una partida sin acabar
        When el organizador la termina
        Then PendingGamesError con 2 partidos y 1 partida
        """
        mundo = await _en_curso()
        await mundo.partido([mundo.jugadora], [mundo.otro])
        await mundo.partido([mundo.capitana], [mundo.capitan_b], empezado=True)
        acabado = await mundo.partido([mundo.jugadora], [mundo.capitan_b], empezado=True)
        await _cambiar_partido(mundo, acabado, lambda p: p.concede("A"))
        await mundo.partida_con(mundo.otro)

        with pytest.raises(PendingGamesError) as error:
            await _terminar(mundo)

        assert (error.value.partidos, error.value.partidas) == (2, 1)

    async def test_what_is_pending_in_another_competition_does_not_count(self):
        """
        Given otra competición con un partido y una partida sin acabar
        When el organizador termina la suya, sin nada pendiente
        Then se termina
        """
        otra = await _en_curso()
        await otra.partido([otra.jugadora], [otra.otro])
        await otra.partida_con(otra.jugadora)
        # La suya, en la misma base de datos que la otra
        mundo = _Mundo()
        mundo.uow = otra.uow
        await mundo.montar()
        await mundo.cerrar()
        await mundo.empezar()

        await _terminar(mundo)

        assert await _estado(mundo) == CompetitionStatus.COMPLETED


class TestUnaSolaLectura:
    async def test_reads_the_matches_of_every_round_at_once(self):
        """
        Given la competición en curso con tres rondas, cada una con un partido
        When el organizador la termina
        Then los partidos se leen de una vez para todas las rondas, no ronda a
            ronda dentro del bloqueo (revisión, 22 nov 2026)
        """
        mundo = await _en_curso()
        for _ in range(3):
            await mundo.partido([mundo.jugadora], [mundo.otro])
        mundo.uow.matches.find_by_round = AsyncMock(wraps=mundo.uow.matches.find_by_round)
        mundo.uow.matches.find_by_rounds = AsyncMock(wraps=mundo.uow.matches.find_by_rounds)

        with pytest.raises(PendingGamesError) as error:
            await _terminar(mundo)

        assert error.value.partidos == 3
        mundo.uow.matches.find_by_rounds.assert_awaited_once()
        mundo.uow.matches.find_by_round.assert_not_awaited()


class TestElOrdenDeSiempre:
    async def test_someone_else_is_forbidden_before_looking_at_what_is_pending(self):
        """
        Given la competición en curso con un partido sin acabar
        When la termina alguien que no es el organizador
        Then 403, como siempre, no PENDING_GAMES
        """
        mundo = await _en_curso()
        await mundo.partido([mundo.jugadora], [mundo.otro])

        mundo.uow.competitions.find_by_id_for_update = AsyncMock(
            wraps=mundo.uow.competitions.find_by_id_for_update
        )

        with pytest.raises(NotCompetitionCreatorError):
            await _terminar(mundo, quien=UserId(uuid4()))

        # Autorizar antes de bloquear, como BE #309: quien no puede no retiene la fila
        mundo.uow.competitions.find_by_id_for_update.assert_not_awaited()

    async def test_state_and_pending_are_decided_on_what_is_read_after_locking(self):
        """
        Given la competición en curso con un partido sin acabar, que otra petición
            termina mientras esta espera el bloqueo
        When el organizador la termina
        Then el error de estado de lo releído, no PENDING_GAMES
        """
        mundo = await _en_curso()
        await mundo.partido([mundo.jugadora], [mundo.otro])
        original = mundo.uow.competitions.find_by_id_for_update

        async def terminada_entre_medias(competition_id):
            releida = await original(competition_id)
            releida._status = CompetitionStatus.COMPLETED
            return releida

        mundo.uow.competitions.find_by_id_for_update = terminada_entre_medias

        with pytest.raises(CompetitionStateError):
            await _terminar(mundo)

    async def test_a_competition_not_in_progress_is_a_state_error_first(self):
        """
        Given la competición cerrada (sin empezar) con un partido generado
        When el organizador la termina
        Then el error de estado de siempre, no PENDING_GAMES
        """
        mundo = await _Mundo().montar()
        await mundo.cerrar()
        await mundo.partido([mundo.jugadora], [mundo.otro])

        with pytest.raises(CompetitionStateError):
            await _terminar(mundo)

    async def test_it_looks_with_the_competition_locked(self):
        """
        Given la competición en curso con un partido sin acabar
        When el organizador la termina
        Then la competición se ha leído bloqueada
        """
        mundo = await _en_curso()
        await mundo.partido([mundo.jugadora], [mundo.otro])
        mundo.uow.competitions.find_by_id_for_update = AsyncMock(
            wraps=mundo.uow.competitions.find_by_id_for_update
        )

        with pytest.raises(PendingGamesError):
            await _terminar(mundo)

        mundo.uow.competitions.find_by_id_for_update.assert_awaited_once()
