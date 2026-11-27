"""
`forget_source` en Postgres (26 nov 2026): lo que hace el repositorio cuando una
partida rapida se borra de verdad. Los mismos casos que el doble en memoria
(`tests/unit/.../test_in_memory_forget_source.py`), que es en el que se apoyan
los tests de los casos de uso: tienen que decir lo mismo.

| Caso                                              | Resultado                    |
|---------------------------------------------------|------------------------------|
| Lo de todos los jugadores de esa partida          | Borrado; devuelve cuantos    |
| Lo de otra partida, y un aviso de otro tipo       | Intacto                      |
| Un logro de torneo con ese mismo origen           | Intacto                      |
| Un birdie que estaba oculto                       | No deja apunte               |
| Un apunte que ya habia de esa partida             | Se purga                     |
| Un «campo nuevo» que estaba oculto                | Deja apunte: el heredero en  |
|                                                   | ese campo sale oculto        |
| Sin tipos                                         | No borra nada                |
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.repositories.activity_event_repository_interface import (
    ActivitySlice,
)
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.social.infrastructure.persistence.sqlalchemy.activity_event_repository import (
    SQLAlchemyActivityEventRepository,
)
from tests.integration.modules.social.infrastructure.persistence.sqlalchemy.test_activity_event_notices import (
    _user,
)

pytestmark = pytest.mark.integration

T = ActivityEventType
CUANDO = datetime(2026, 11, 26, 12, 0)
TODOS = frozenset(ActivityEventType)
DE_PARTIDA = sorted(t for t in ActivityEventType if t.may_come_from_a_quick_match)


def _evento(user, tipo, origen: str, *, visible: bool = True, **payload) -> ActivityEvent:
    return ActivityEvent.create(
        user_id=user.id,
        type=tipo,
        occurred_at=CUANDO,
        source_match_id=origen,
        published_at=CUANDO + timedelta(minutes=1),
        payload=payload,
        visible_to_friends=visible,
    )


async def _de(repository, user) -> dict[tuple, bool]:
    eventos = await repository.find_in([ActivitySlice(user_ids=(user.id,), types=TODOS)], 50)
    return {(e.type, e.source_match_id): e.visible_to_friends for e in eventos}


async def _apuntes(db_session, origen: str) -> int:
    resultado = await db_session.execute(
        text("SELECT count(*) FROM withdrawn_hidden_achievements WHERE source_match_id = :o"),
        {"o": origen},
    )
    return int(resultado.scalar_one())


async def test_everything_from_that_match_is_gone_and_the_rest_stays(db_session):
    ana, bea = await _user(db_session), await _user(db_session)
    partida, otra = str(uuid4()), str(uuid4())
    repository = SQLAlchemyActivityEventRepository(db_session)
    await repository.add_many(
        [
            _evento(ana, T.QUICK_MATCH_FINISHED, partida),
            _evento(ana, T.BIRDIE, partida),
            _evento(bea, T.QUICK_MATCH_FINISHED, partida),
            _evento(ana, T.BIRDIE, otra),
            _evento(ana, T.TEE_TIME_ASSIGNED, partida),
            _evento(bea, T.NEW_COURSE, partida, from_tournament=True),
        ]
    )
    await db_session.commit()

    borrados = await repository.forget_source(partida, DE_PARTIDA)
    await db_session.commit()

    assert borrados == 3
    assert set(await _de(repository, ana)) == {(T.BIRDIE, otra), (T.TEE_TIME_ASSIGNED, partida)}
    assert set(await _de(repository, bea)) == {(T.NEW_COURSE, partida)}
    assert await repository.forget_source(otra, []) == 0
    assert (T.BIRDIE, otra) in await _de(repository, ana)


async def test_a_hidden_birdie_leaves_no_note_and_old_notes_are_purged(db_session):
    ana = await _user(db_session)
    partida, retirada = str(uuid4()), str(uuid4())
    repository = SQLAlchemyActivityEventRepository(db_session)
    await repository.add_many(
        [
            _evento(ana, T.BIRDIE, partida, visible=False),
            _evento(ana, T.BIRDIE, retirada, visible=False),
        ]
    )
    # Retirado como un aviso que puede volver: deja apunte
    await repository.delete_from_source(retirada, [T.BIRDIE])
    await db_session.commit()
    assert await _apuntes(db_session, retirada) == 1

    await repository.forget_source(partida, DE_PARTIDA)
    await repository.forget_source(retirada, DE_PARTIDA)
    await db_session.commit()

    assert (await _apuntes(db_session, partida), await _apuntes(db_session, retirada)) == (0, 0)
    await repository.add_many([_evento(ana, T.BIRDIE, partida), _evento(ana, T.BIRDIE, retirada)])
    await db_session.commit()
    assert await _de(repository, ana) == {(T.BIRDIE, partida): True, (T.BIRDIE, retirada): True}


async def test_a_hidden_new_course_reaches_its_heir_hidden(db_session):
    ana = await _user(db_session)
    partida, heredera, campo = str(uuid4()), str(uuid4()), str(uuid4())
    repository = SQLAlchemyActivityEventRepository(db_session)
    await repository.add_many(
        [_evento(ana, T.NEW_COURSE, partida, visible=False, golf_course_id=campo)]
    )
    await db_session.commit()

    await repository.forget_source(partida, DE_PARTIDA)
    await db_session.commit()
    await repository.add_many([_evento(ana, T.NEW_COURSE, heredera, golf_course_id=campo)])
    await db_session.commit()

    assert await _apuntes(db_session, partida) == 1
    assert await _de(repository, ana) == {(T.NEW_COURSE, heredera): False}
