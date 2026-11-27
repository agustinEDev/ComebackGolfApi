"""
Tests de PurgeTrashedQuickMatchesUseCase (26 nov 2026): cuando una cuenta se
borra, sus partidas rapidas que con eso quedan «tiradas por todos» se borran de
verdad. Sin esto se quedarian guardadas para siempre: quien las tiro ya no las
ve, y nadie vuelve a pulsar la papelera.

  #   caso                                          | resultado
  ----|----------------------------------------------|---------------------------
  U1  Ana la tiro, Bea no; se borra la cuenta de Bea | se borra de verdad, y
                                                    | Actividad la olvida
  U2  nadie la habia tirado                         | sigue: no la tiro nadie
  U3  queda otro jugador activo que no la ha tirado | sigue
  U4  partidas en las que no jugaba                 | ni se miran
  U5  devuelve cuantas borro                        | para el registro
  U6  una que falla no para a las demas             | es una limpieza: lo que no
                                                    | se pueda, se queda como estaba
"""

from collections.abc import Sequence
from uuid import uuid4

import pytest

from src.modules.golf_course.domain.value_objects.golf_course_id import GolfCourseId
from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    ForgottenActivity,
    QuickMatchActivityInterface,
)
from src.modules.quick_match.application.use_cases.purge_trashed_quick_matches_use_case import (
    PurgeTrashedQuickMatchesUseCase,
)
from src.modules.quick_match.domain.entities.quick_match import QuickMatch
from src.modules.quick_match.domain.value_objects.participant_id import ParticipantId
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.quick_match.domain.value_objects.quick_match_participant import (
    QuickMatchParticipant,
)
from src.modules.user.domain.value_objects.user_id import UserId
from src.shared.domain.value_objects.scoring_format import ScoringFormat
from tests.unit.modules.quick_match.conftest import create_user

pytestmark = pytest.mark.asyncio


class _Actividad(QuickMatchActivityInterface):
    def __init__(self, rotas=()):
        self.olvidadas: list[str] = []
        self.cedidas: list[tuple[str, list[UserId]]] = []
        self._rotas = set(rotas)

    async def forget(self, quick_match_id: str, player_ids: Sequence[UserId]) -> ForgottenActivity:
        if quick_match_id in self._rotas:
            raise RuntimeError("sin base de datos")
        self.olvidadas.append(quick_match_id)
        return ForgottenActivity(events=1)

    async def hand_over_new_course(self, golf_course_id: str, player_ids: Sequence[UserId]) -> None:
        self.cedidas.append((golf_course_id, list(player_ids)))


async def _terminada(qm_uow, creador, *otros, tiran=()):
    qm = QuickMatch.create(
        id=QuickMatchId.generate(),
        creator_id=creador.id,
        golf_course_id=GolfCourseId(uuid4()),
        scoring_format=ScoringFormat.STABLEFORD,
    )
    for otro in otros:
        qm.add_participant(QuickMatchParticipant.for_user(otro.id))
    qm.start([qm.creator_participant_id])
    qm.complete()
    for quien in tiran:
        qm.hide_for(ParticipantId(quien.id.value))
    async with qm_uow:
        await qm_uow.quick_matches.add(qm)
    return qm


async def _borrar_cuenta(user_uow, user) -> None:
    async with user_uow:
        await user_uow.users.delete_by_id(user.id)


class TestPurgeTrashedQuickMatches:
    async def test_u1_the_match_the_other_had_trashed_is_deleted(self, qm_uow, user_uow):
        ana = await create_user(user_uow, "ana-u1@test.com")
        bea = await create_user(user_uow, "bea-u1@test.com")
        qm = await _terminada(qm_uow, ana, bea, tiran=[ana])
        await _borrar_cuenta(user_uow, bea)
        actividad = _Actividad()

        borradas = await PurgeTrashedQuickMatchesUseCase(qm_uow, user_uow, actividad).execute(
            str(bea.id.value)
        )

        assert borradas == 1
        assert await qm_uow.quick_matches.find_by_id(qm.id) is None
        assert actividad.olvidadas == [str(qm.id.value)]

    async def test_u2_a_match_nobody_trashed_stays(self, qm_uow, user_uow):
        ana = await create_user(user_uow, "ana-u2@test.com")
        bea = await create_user(user_uow, "bea-u2@test.com")
        qm = await _terminada(qm_uow, ana, bea)
        await _borrar_cuenta(user_uow, bea)
        actividad = _Actividad()

        borradas = await PurgeTrashedQuickMatchesUseCase(qm_uow, user_uow, actividad).execute(
            str(bea.id.value)
        )

        assert borradas == 0
        assert await qm_uow.quick_matches.find_by_id(qm.id) is not None
        assert actividad.olvidadas == []

    async def test_u3_another_active_player_still_holds_it(self, qm_uow, user_uow):
        ana = await create_user(user_uow, "ana-u3@test.com")
        bea = await create_user(user_uow, "bea-u3@test.com")
        carla = await create_user(user_uow, "carla-u3@test.com")
        qm = await _terminada(qm_uow, ana, bea, carla, tiran=[ana])
        await _borrar_cuenta(user_uow, bea)

        borradas = await PurgeTrashedQuickMatchesUseCase(qm_uow, user_uow, _Actividad()).execute(
            str(bea.id.value)
        )

        assert borradas == 0
        assert await qm_uow.quick_matches.find_by_id(qm.id) is not None

    async def test_u4_matches_they_did_not_play_are_left_alone(self, qm_uow, user_uow):
        ana = await create_user(user_uow, "ana-u4@test.com")
        bea = await create_user(user_uow, "bea-u4@test.com")
        # De Ana sola, tirada por ella... pero aun guardada (como si viniera de antes)
        ajena = await _terminada(qm_uow, ana, tiran=[ana])
        await _borrar_cuenta(user_uow, bea)

        borradas = await PurgeTrashedQuickMatchesUseCase(qm_uow, user_uow, _Actividad()).execute(
            str(bea.id.value)
        )

        assert borradas == 0
        assert await qm_uow.quick_matches.find_by_id(ajena.id) is not None

    async def test_u5_u6_it_counts_what_it_deleted_and_one_failure_does_not_stop_the_rest(
        self, qm_uow, user_uow
    ):
        ana = await create_user(user_uow, "ana-u6@test.com")
        bea = await create_user(user_uow, "bea-u6@test.com")
        rota = await _terminada(qm_uow, ana, bea, tiran=[ana])
        buena = await _terminada(qm_uow, ana, bea, tiran=[ana])
        otra = await _terminada(qm_uow, ana, bea, tiran=[ana])
        await _borrar_cuenta(user_uow, bea)
        actividad = _Actividad(rotas=[str(rota.id.value)])

        borradas = await PurgeTrashedQuickMatchesUseCase(qm_uow, user_uow, actividad).execute(
            str(bea.id.value)
        )

        assert borradas == 2
        assert await qm_uow.quick_matches.find_by_id(rota.id) is not None
        assert await qm_uow.quick_matches.find_by_id(buena.id) is None
        assert await qm_uow.quick_matches.find_by_id(otra.id) is None
