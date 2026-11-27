"""
Olvidar lo que salio de una partida rapida que se borra de verdad (26 nov 2026).

No es retirar un aviso que puede volver (`delete_from_source`, que deja apunte
de lo que estaba oculto): la partida ya no existe y nada suyo va a volver a
publicarse. Solo «campo nuevo» deja su apunte, porque ese logro NO desaparece:
pasa a la siguiente vuelta del jugador en ese campo, y si el lo tenia oculto,
oculto tiene que llegarle al heredero.

  #   caso                                          | resultado
  ----|----------------------------------------------|-----------------------------
  F1  lo de todos los jugadores de esa partida      | borrado; devuelve cuantos
  F2  lo de otra partida, y lo de otros tipos       | intacto
  F3  un birdie que estaba oculto                   | no deja apunte: uno nuevo con
                                                    | ese origen saldria visible
  F4  un apunte que ya habia de esa partida         | se purga tambien
  F5  un «campo nuevo» que estaba oculto            | deja apunte: el del heredero
                                                    | en ese campo sale oculto
  F6  sin tipos                                     | no borra nada
"""

from datetime import datetime, timedelta

import pytest

from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.repositories.activity_event_repository_interface import (
    ActivitySlice,
)
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.social.infrastructure.persistence.in_memory.in_memory_activity_event_repository import (
    InMemoryActivityEventRepository,
)
from src.modules.user.domain.value_objects.user_id import UserId

pytestmark = pytest.mark.asyncio

T = ActivityEventType
CUANDO = datetime(2026, 11, 26, 12, 0)
ANA = UserId.generate()
BEA = UserId.generate()
DE_PARTIDA = sorted(t for t in ActivityEventType if t.may_come_from_a_quick_match)


def _evento(tipo, origen, *, user=ANA, visible=True, **payload) -> ActivityEvent:
    return ActivityEvent.create(
        user_id=user,
        type=tipo,
        occurred_at=CUANDO,
        source_match_id=origen,
        published_at=CUANDO + timedelta(minutes=1),
        payload=payload,
        visible_to_friends=visible,
    )


async def _de(repo, user=ANA) -> dict[tuple, bool]:
    eventos = await repo.find_in(
        [ActivitySlice(user_ids=(user,), types=frozenset(ActivityEventType))], 50
    )
    return {(e.type, e.source_match_id): e.visible_to_friends for e in eventos}


@pytest.fixture
def repo():
    return InMemoryActivityEventRepository()


async def test_f1_everything_from_that_match_is_gone_for_every_player(repo):
    await repo.add_many(
        [
            _evento(T.QUICK_MATCH_FINISHED, "m"),
            _evento(T.BIRDIE, "m"),
            _evento(T.QUICK_MATCH_FINISHED, "m", user=BEA),
        ]
    )

    borrados = await repo.forget_source("m", DE_PARTIDA)

    assert borrados == 3
    assert await _de(repo) == {}
    assert await _de(repo, BEA) == {}


async def test_f2_another_match_and_other_types_stay(repo):
    await repo.add_many(
        [
            _evento(T.BIRDIE, "m"),
            _evento(T.BIRDIE, "otra"),
            _evento(T.ENROLLED_IN_TOURNAMENT, "m", competition_id="c"),
        ]
    )

    await repo.forget_source("m", DE_PARTIDA)

    assert set(await _de(repo)) == {(T.BIRDIE, "otra"), (T.ENROLLED_IN_TOURNAMENT, "m")}


async def test_f3_a_hidden_birdie_leaves_no_note_behind(repo):
    await repo.add_many([_evento(T.BIRDIE, "m", visible=False)])

    await repo.forget_source("m", DE_PARTIDA)
    await repo.add_many([_evento(T.BIRDIE, "m")])

    assert await _de(repo) == {(T.BIRDIE, "m"): True}


async def test_f4_a_note_that_was_already_there_is_purged_too(repo):
    await repo.add_many([_evento(T.BIRDIE, "m", visible=False)])
    # Retirado como un aviso: deja apunte de que estaba oculto
    await repo.delete_from_source("m", [T.BIRDIE])

    await repo.forget_source("m", DE_PARTIDA)
    await repo.add_many([_evento(T.BIRDIE, "m")])

    assert await _de(repo) == {(T.BIRDIE, "m"): True}


async def test_f5_a_hidden_new_course_reaches_its_heir_hidden(repo):
    await repo.add_many([_evento(T.NEW_COURSE, "m", visible=False, golf_course_id="campo")])

    await repo.forget_source("m", DE_PARTIDA)
    await repo.add_many([_evento(T.NEW_COURSE, "heredera", golf_course_id="campo")])

    assert await _de(repo) == {(T.NEW_COURSE, "heredera"): False}


async def test_f6_without_types_nothing_is_deleted(repo):
    await repo.add_many([_evento(T.BIRDIE, "m")])

    assert await repo.forget_source("m", []) == 0
    assert set(await _de(repo)) == {(T.BIRDIE, "m")}
