"""
La limpieza de partidas rapidas al borrar una cuenta, en Postgres (26 nov 2026):
la consulta que busca las candidatas (`find_trashed_with_participant`) y el caso
de uso entero, con las unidades de trabajo reales sobre una sola sesion.

| Caso                                                        | Resultado          |
|-------------------------------------------------------------|--------------------|
| Partidas del jugador que alguien tiene en la papelera       | Candidatas         |
| Las suyas que nadie ha tirado, y las tiradas de otros        | No                 |
| Ana la tiro, Bea no, y se borra la cuenta de Bea            | Se borra, con sus  |
|                                                             | golpes y eventos   |
| Queda Carla, activa, sin tirarla                            | Sigue              |
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from src.modules.quick_match.application.use_cases.purge_trashed_quick_matches_use_case import (
    PurgeTrashedQuickMatchesUseCase,
)
from src.modules.quick_match.infrastructure.persistence.sqlalchemy.quick_match_repository import (
    SQLAlchemyQuickMatchRepository,
)
from src.modules.quick_match.infrastructure.persistence.sqlalchemy.quick_match_unit_of_work import (
    SQLAlchemyQuickMatchUnitOfWork,
)
from src.modules.social.application.use_cases.forget_quick_match_activity_use_case import (
    ForgetQuickMatchActivityUseCase,
)
from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.social.infrastructure.adapters.quick_match_activity_adapter import (
    QuickMatchActivityAdapter,
)
from src.modules.social.infrastructure.persistence.sqlalchemy.activity_event_repository import (
    SQLAlchemyActivityEventRepository,
)
from src.modules.social.infrastructure.persistence.sqlalchemy.social_unit_of_work import (
    SQLAlchemySocialUnitOfWork,
)
from src.modules.user.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SQLAlchemyUnitOfWork,
)
from tests.integration.modules.social.infrastructure.persistence.sqlalchemy.test_activity_event_notices import (
    _user,
)
from tests.integration.modules.social.infrastructure.test_shared_games_repositories import (
    _campo,
    _rapida,
)

pytestmark = pytest.mark.integration

CUANDO = datetime(2026, 11, 26, 12, 0)


class _SinCesion:
    """La cesion del «campo nuevo» va por otra sesion y no es lo que se prueba aqui."""

    async def execute(self, golf_course_id, player_ids) -> None:
        return None


def _caso(db_session) -> PurgeTrashedQuickMatchesUseCase:
    actividad = QuickMatchActivityAdapter(
        ForgetQuickMatchActivityUseCase(SQLAlchemySocialUnitOfWork(db_session)),
        _SinCesion(),  # type: ignore[arg-type]
    )
    return PurgeTrashedQuickMatchesUseCase(
        SQLAlchemyQuickMatchUnitOfWork(db_session), SQLAlchemyUnitOfWork(db_session), actividad
    )


async def _existe(db_session, partida) -> bool:
    resultado = await db_session.execute(
        text("SELECT count(*) FROM quick_matches WHERE id::text = :v"),
        {"v": str(partida.id.value)},
    )
    return int(resultado.scalar_one()) == 1


async def _eventos(db_session, partida) -> int:
    resultado = await db_session.execute(
        text("SELECT count(*) FROM activity_events WHERE source_match_id = :v"),
        {"v": str(partida.id.value)},
    )
    return int(resultado.scalar_one())


async def test_only_the_players_trashed_matches_are_candidates(db_session):
    ana, bea, carla = [await _user(db_session) for _ in range(3)]
    campo = await _campo(db_session, ana.id)
    tirada = await _rapida(db_session, campo, ana.id, [bea.id], oculta_por=ana.id)
    await _rapida(db_session, campo, ana.id, [bea.id])  # nadie la tiro
    await _rapida(db_session, campo, ana.id, [carla.id], oculta_por=ana.id)  # Bea no jugo

    candidatas = await SQLAlchemyQuickMatchRepository(db_session).find_trashed_with_participant(
        bea.id
    )

    assert candidatas == [tirada.id]


async def test_deleting_the_account_purges_what_everyone_else_had_trashed(db_session):
    ana, bea, carla = [await _user(db_session) for _ in range(3)]
    campo = await _campo(db_session, ana.id)
    de_dos = await _rapida(db_session, campo, ana.id, [bea.id], oculta_por=ana.id)
    de_tres = await _rapida(db_session, campo, ana.id, [bea.id, carla.id], oculta_por=ana.id)
    await SQLAlchemyActivityEventRepository(db_session).add_many(
        [
            ActivityEvent.create(
                user_id=ana.id,
                type=ActivityEventType.QUICK_MATCH_FINISHED,
                occurred_at=CUANDO,
                source_match_id=str(partida.id.value),
                published_at=CUANDO + timedelta(minutes=1),
                payload={},
            )
            for partida in (de_dos, de_tres)
        ]
    )
    await db_session.commit()
    # Se borra la cuenta de Bea: ya no retiene nada
    await db_session.execute(
        text("DELETE FROM users WHERE id::text = :u"), {"u": str(bea.id.value)}
    )
    await db_session.commit()

    borradas = await _caso(db_session).execute(str(bea.id.value))

    assert borradas == 1
    assert not await _existe(db_session, de_dos)
    assert await _eventos(db_session, de_dos) == 0
    # La de tres sigue: Carla, activa, no la ha tirado
    assert await _existe(db_session, de_tres)
    assert await _eventos(db_session, de_tres) == 1
