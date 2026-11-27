"""
Lo que hace Actividad cuando una partida rapida se borra de verdad (26 nov 2026).

Olvidarla (`ForgetQuickMatchActivityUseCase`), dentro de la transaccion que la borra:

  #   caso                                        | resultado
  ----|--------------------------------------------|--------------------------------
  O1  lo que publico la partida, de sus jugadores | borrado: como acabo y logros
  O2  lo de otra partida y los avisos de torneo   | intacto
  O3  no confirma por su cuenta                   | no abre la unidad de trabajo: va
                                                  | en la transaccion de quien llama
  O4  dice quien tenia «campo nuevo» por ella     | solo a esos se les cede despues

Ceder el «campo nuevo» (`HandOverNewCourseUseCase`), ya con el borrado guardado:

  #   caso                                        | resultado
  ----|--------------------------------------------|--------------------------------
  C1  al jugador le queda otra partida rapida en  | se vuelve a publicar el «campo
      ese campo                                   | nuevo» de esa partida
  C2  lo que le queda es una vuelta de torneo     | lo hereda el torneo, solo para el
  C3  le quedan varias: manda la mas antigua      | una sola heredera por jugador
  C4  sus vueltas en OTRO campo                   | no se tocan
  C8  la partida heredera la jugaron mas          | el «campo nuevo» se republica
      jugadores                                   | SOLO para quien lo hereda
  C5  no le queda ninguna en ese campo            | nada que ceder
  C6  falla una heredera                          | no para a las demas ni sale el
                                                  | fallo: el borrado ya esta hecho
  C7  falla leer el historial                     | tampoco sale
"""

from datetime import datetime, timedelta

import pytest

from src.modules.social.application.exclusive_achievements import PlayedRound
from src.modules.social.application.use_cases.forget_quick_match_activity_use_case import (
    ForgetQuickMatchActivityUseCase,
)
from src.modules.social.application.use_cases.hand_over_new_course_use_case import (
    HandOverNewCourseUseCase,
)
from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.repositories.activity_event_repository_interface import (
    ActivitySlice,
)
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.social.infrastructure.persistence.in_memory.in_memory_social_unit_of_work import (
    InMemorySocialUnitOfWork,
)
from src.modules.user.domain.value_objects.user_id import UserId

pytestmark = pytest.mark.asyncio

T = ActivityEventType
DIA = datetime(2026, 11, 20, 9, 0)
ANA, BEA = UserId.generate(), UserId.generate()


def _evento(tipo, origen, user=ANA, **payload) -> ActivityEvent:
    return ActivityEvent.create(
        user_id=user,
        type=tipo,
        occurred_at=DIA,
        source_match_id=origen,
        published_at=DIA + timedelta(minutes=1),
        payload=payload,
    )


async def _quedan(uow, user=ANA) -> set[tuple]:
    eventos = await uow.activity_events.find_in(
        [ActivitySlice(user_ids=(user,), types=frozenset(ActivityEventType))], 50
    )
    return {(e.type, e.source_match_id) for e in eventos}


class TestForget:
    async def test_o1_what_the_match_published_is_gone_for_its_players(self):
        uow = InMemorySocialUnitOfWork()
        await uow.activity_events.add_many(
            [
                _evento(T.QUICK_MATCH_FINISHED, "m"),
                _evento(T.BIRDIE, "m"),
                _evento(T.QUICK_MATCH_FINISHED, "m", BEA),
            ]
        )

        borrados, con_campo_nuevo = await ForgetQuickMatchActivityUseCase(uow).execute(
            "m", [ANA, BEA]
        )

        assert borrados == 3
        assert con_campo_nuevo == []
        assert await _quedan(uow) == set()
        assert await _quedan(uow, BEA) == set()

    async def test_o2_another_match_and_tournament_notices_stay(self):
        uow = InMemorySocialUnitOfWork()
        await uow.activity_events.add_many(
            [
                _evento(T.BIRDIE, "m"),
                _evento(T.BIRDIE, "otra"),
                _evento(T.ENROLLED_IN_TOURNAMENT, "m", competition_id="c"),
            ]
        )

        await ForgetQuickMatchActivityUseCase(uow).execute("m", [ANA])

        assert await _quedan(uow) == {(T.BIRDIE, "otra"), (T.ENROLLED_IN_TOURNAMENT, "m")}

    async def test_o4_it_tells_who_held_a_new_course_through_that_match(self):
        """Solo ellos lo heredan despues; un «campo nuevo» de torneo con ese origen no cuenta."""
        uow = InMemorySocialUnitOfWork()
        await uow.activity_events.add_many(
            [
                _evento(T.NEW_COURSE, "m", BEA, golf_course_id="campo"),
                _evento(T.BIRDIE, "m"),
                _evento(T.NEW_COURSE, "otra", golf_course_id="campo"),
            ]
        )

        borrados, con_campo_nuevo = await ForgetQuickMatchActivityUseCase(uow).execute(
            "m", [ANA, BEA]
        )

        assert borrados == 2
        assert con_campo_nuevo == [BEA]

    async def test_o3_it_does_not_commit_on_its_own(self):
        uow = InMemorySocialUnitOfWork()
        uow.committed = False
        await uow.activity_events.add_many([_evento(T.BIRDIE, "m")])

        await ForgetQuickMatchActivityUseCase(uow).execute("m", [ANA])

        assert uow.committed is False


class _Historial:
    def __init__(self, rondas=(), falla: Exception | None = None):
        self._rondas, self._falla = list(rondas), falla
        self.preguntas: list[set[UserId]] = []

    async def played_rounds(self, user_ids):
        self.preguntas.append(set(user_ids))
        if self._falla is not None:
            raise self._falla
        return list(self._rondas)


class _Rapidas:
    def __init__(self, rotas=()):
        self.republicadas: list[str] = []
        # Para quien se republico cada una: solo sus herederos
        self.para: dict[str, list[UserId]] = {}
        self._rotas = set(rotas)

    async def republish_new_course(self, quick_match_id: str, only_for=None) -> int:
        if quick_match_id in self._rotas:
            raise RuntimeError("no se pudo")
        self.republicadas.append(quick_match_id)
        self.para[quick_match_id] = list(only_for or [])
        return 1


class _Torneos:
    def __init__(self):
        self.republicados: list[tuple[str, list[UserId]]] = []

    async def republish_exclusive(self, competition_id: str, user_ids: list[UserId]) -> int:
        self.republicados.append((competition_id, list(user_ids)))
        return 1


def _vuelta(origen, *, user=ANA, campo="campo", dias=0, torneo=None) -> PlayedRound:
    return PlayedRound(
        user_id=user,
        golf_course_id=campo,
        instant=DIA + timedelta(days=dias),
        source_id=origen,
        holes_played=18,
        competition_id=torneo,
    )


def _caso(historial, rapidas=None, torneos=None):
    rapidas, torneos = rapidas or _Rapidas(), torneos or _Torneos()
    return HandOverNewCourseUseCase(historial, rapidas, torneos), rapidas, torneos


class TestHandOver:
    async def test_c1_another_quick_match_on_that_course_inherits_it(self):
        caso, rapidas, torneos = _caso(_Historial([_vuelta("heredera")]))

        await caso.execute("campo", [ANA])

        assert rapidas.republicadas == ["heredera"]
        # Solo para quien la hereda, no para todos los que jugaron esa partida
        assert rapidas.para == {"heredera": [ANA]}
        assert torneos.republicados == []

    async def test_c2_a_tournament_round_inherits_it_only_for_that_player(self):
        caso, rapidas, torneos = _caso(
            _Historial([_vuelta("partido", torneo="torneo-1"), _vuelta("otra", user=BEA)])
        )

        await caso.execute("campo", [ANA, BEA])

        assert torneos.republicados == [("torneo-1", [ANA])]
        assert rapidas.republicadas == ["otra"]
        assert rapidas.para == {"otra": [BEA]}

    async def test_c3_the_oldest_round_left_is_the_heir(self):
        caso, rapidas, _ = _caso(
            _Historial([_vuelta("tardia", dias=5), _vuelta("antigua", dias=1)])
        )

        await caso.execute("campo", [ANA])

        assert rapidas.republicadas == ["antigua"]

    async def test_c4_rounds_on_another_course_are_left_alone(self):
        caso, rapidas, torneos = _caso(_Historial([_vuelta("de-otro", campo="otro-campo")]))

        await caso.execute("campo", [ANA])

        assert (rapidas.republicadas, torneos.republicados) == ([], [])

    async def test_c5_with_no_round_left_there_is_nothing_to_hand_over(self):
        historial = _Historial([])
        caso, rapidas, torneos = _caso(historial)

        await caso.execute("campo", [ANA])

        assert historial.preguntas == [{ANA}]
        assert (rapidas.republicadas, torneos.republicados) == ([], [])

    async def test_c6_a_failing_heir_does_not_stop_the_others(self):
        # La que falla va ANTES (se recorren por orden de id): si el fallo cortara
        # el recorrido, la buena no llegaria a publicarse
        caso, rapidas, _ = _caso(
            _Historial([_vuelta("a-rota"), _vuelta("z-buena", user=BEA)]),
            _Rapidas(rotas=["a-rota"]),
        )

        await caso.execute("campo", [ANA, BEA])

        assert rapidas.republicadas == ["z-buena"]

    async def test_c7_a_failing_history_does_not_raise(self):
        caso, rapidas, _ = _caso(_Historial(falla=RuntimeError("sin base de datos")))

        await caso.execute("campo", [ANA])

        assert rapidas.republicadas == []

    async def test_without_players_it_asks_nothing(self):
        historial = _Historial([])
        caso, _, _ = _caso(historial)

        await caso.execute("campo", [])

        assert historial.preguntas == []
