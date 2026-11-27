"""
Borrar una partida rapida en los repositorios en memoria (26 nov 2026).

En la base de datos, los golpes caen solos con la partida (ON DELETE CASCADE).
El doble en memoria tiene que hacer lo mismo, o los tests unitarios del borrado
dirian que no queda nada cuando en memoria quedan golpes huerfanos.

  #   caso                                   | resultado
  ----|---------------------------------------|---------------------------------
  B1  borrar una partida                     | deja de encontrarse, por id y en
                                             | la lista de su jugador
  B2  borrarla se lleva sus golpes           | como el CASCADE de la base
  B3  los golpes de OTRA partida             | intactos
  B4  borrar una que no esta guardada        | no hace nada, sin error
"""

from uuid import uuid4

import pytest

from src.modules.golf_course.domain.value_objects.golf_course_id import GolfCourseId
from src.modules.quick_match.domain.entities.quick_match import QuickMatch
from src.modules.quick_match.domain.entities.quick_match_hole_score import QuickMatchHoleScore
from src.modules.quick_match.domain.value_objects.quick_match_hole_score_id import (
    QuickMatchHoleScoreId,
)
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.quick_match.infrastructure.persistence.in_memory.in_memory_quick_match_unit_of_work import (
    InMemoryQuickMatchUnitOfWork,
)
from src.modules.user.domain.value_objects.user_id import UserId
from src.shared.domain.value_objects.scoring_format import ScoringFormat

pytestmark = pytest.mark.asyncio


def _partida(creador: UserId) -> QuickMatch:
    return QuickMatch.create(
        id=QuickMatchId.generate(),
        creator_id=creador,
        golf_course_id=GolfCourseId(uuid4()),
        scoring_format=ScoringFormat.STABLEFORD,
    )


async def _con_golpes(uow, partida: QuickMatch, hoyos: int) -> None:
    async with uow:
        await uow.quick_matches.add(partida)
        for hoyo in range(1, hoyos + 1):
            await uow.quick_match_hole_scores.add(
                QuickMatchHoleScore.create(
                    id=QuickMatchHoleScoreId.generate(),
                    quick_match_id=partida.id,
                    hole_number=hoyo,
                    participant_id=partida.creator_participant_id,
                    score=4,
                    recorded_by_participant_id=partida.creator_participant_id,
                )
            )


async def test_b1_a_deleted_match_is_gone():
    uow = InMemoryQuickMatchUnitOfWork()
    creador = UserId(uuid4())
    partida = _partida(creador)
    await _con_golpes(uow, partida, 0)

    async with uow:
        await uow.quick_matches.delete(partida)

    assert await uow.quick_matches.find_by_id(partida.id) is None
    assert await uow.quick_matches.find_by_ids([partida.id]) == []
    assert await uow.quick_matches.list_for_user(creador) == []


async def test_b2_its_scores_go_with_it():
    uow = InMemoryQuickMatchUnitOfWork()
    partida = _partida(UserId(uuid4()))
    await _con_golpes(uow, partida, 3)
    assert len(await uow.quick_match_hole_scores.find_by_match(partida.id)) == 3

    async with uow:
        await uow.quick_matches.delete(partida)

    assert await uow.quick_match_hole_scores.find_by_match(partida.id) == []


async def test_b3_the_scores_of_another_match_stay():
    uow = InMemoryQuickMatchUnitOfWork()
    borrada, otra = _partida(UserId(uuid4())), _partida(UserId(uuid4()))
    await _con_golpes(uow, borrada, 2)
    await _con_golpes(uow, otra, 2)

    async with uow:
        await uow.quick_matches.delete(borrada)

    assert await uow.quick_matches.find_by_id(otra.id) is otra
    assert len(await uow.quick_match_hole_scores.find_by_match(otra.id)) == 2


async def test_b4_deleting_an_unknown_match_does_nothing():
    uow = InMemoryQuickMatchUnitOfWork()

    async with uow:
        await uow.quick_matches.delete(_partida(UserId(uuid4())))

    assert await uow.quick_matches.count_all() == 0
