"""
La papelera de una partida rapida en Actividad (22 oct 2026; regla ampliada el
26 nov 2026): lo que salio de una partida tirada deja de verse.

| Caso                                                         | Resultado               |
|--------------------------------------------------------------|-------------------------|
| QUICK_MATCH_FINISHED y logros de esa partida, en el feed de  | No salen                |
| un amigo del autor que la tiro                               |                         |
| Lo mismo en la actividad de su perfil                        | No sale                 |
| El propio autor que la tiro (feed, perfil y contador)        | TAMPOCO los ve: para el |
|                                                              | ha desaparecido         |
| Quien la tiro, sobre lo de OTRO jugador de esa partida que   | Tampoco lo ve: es de    |
| no la ha tirado                                              | una partida que tiro    |
| Un amigo que no jugo, sobre lo del jugador que no la tiro    | Lo sigue viendo         |
| Logros de torneo y avisos que no son de partida rapida       | No se tocan             |
| El contador de novedades                                     | Dice lo mismo que el    |
|                                                              | feed                    |
| Pagina llena con uno oculto                                  | El cursor no pierde ni  |
|                                                              | repite nada             |
| Toda la pagina se pregunta de una vez                        | Una consulta por pagina |

Ya no hay «sacarla de la papelera»: es definitiva.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from src.modules.golf_course.infrastructure.persistence.in_memory.in_memory_golf_course_unit_of_work import (
    InMemoryGolfCourseUnitOfWork,
)
from src.modules.social.application.ports.quick_match_trash_interface import (
    QuickMatchTrashInterface,
)
from src.modules.social.application.use_cases.get_feed_unseen_count_use_case import (
    GetFeedUnseenCountUseCase,
)
from src.modules.social.application.use_cases.get_friends_feed_use_case import (
    GetFriendsFeedUseCase,
)
from src.modules.social.application.use_cases.get_player_activity_use_case import (
    GetPlayerActivityUseCase,
)
from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.entities.friendship import Friendship
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.social.domain.value_objects.friendship_id import FriendshipId
from src.modules.social.infrastructure.persistence.in_memory.in_memory_social_unit_of_work import (
    InMemorySocialUnitOfWork,
)
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.value_objects.user_id import UserId
from src.modules.user.infrastructure.persistence.in_memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork as InMemoryUserUnitOfWork,
)

pytestmark = pytest.mark.asyncio

T = ActivityEventType
AHORA = datetime(2026, 10, 22, 12, 0)


class _Papelera(QuickMatchTrashInterface):
    """Que partidas tiene cada uno en su papelera; apunta cada pregunta."""

    def __init__(self):
        self.en_la_papelera: set[tuple[str, UserId]] = set()
        self.preguntas: list[list[tuple[str, UserId]]] = []

    async def trashed_by_author(
        self, pairs: Sequence[tuple[str, UserId]]
    ) -> set[tuple[str, UserId]]:
        self.preguntas.append(sorted(pairs, key=lambda p: (p[0], str(p[1].value))))
        return {p for p in pairs if p in self.en_la_papelera}


@pytest.fixture
def social_uow():
    return InMemorySocialUnitOfWork()


@pytest.fixture
def user_uow():
    return InMemoryUserUnitOfWork()


@pytest.fixture
def papelera():
    return _Papelera()


async def _user(user_uow, nombre: str) -> User:
    user = User.create(
        first_name=nombre,
        last_name="Garcia",
        email_str=f"trash_{uuid4().hex[:8]}@test.com",
        plain_password="SecureP@ssw0rd123",
    )
    async with user_uow:
        await user_uow.users.save(user)
    return user


async def _amigos(social_uow, a: User, b: User) -> None:
    amistad = Friendship.create(id=FriendshipId(uuid4()), requester_id=a.id, addressee_id=b.id)
    amistad.accept()
    async with social_uow:
        await social_uow.friendships.add(amistad)


async def _evento(
    social_uow, user: User, tipo: ActivityEventType, origen: str, minuto: int, **payload
) -> ActivityEvent:
    evento = ActivityEvent.create(
        user_id=user.id,
        type=tipo,
        occurred_at=AHORA,
        source_match_id=origen,
        payload=payload,
        published_at=AHORA + timedelta(minutes=minuto),
    )
    async with social_uow:
        await social_uow.activity_events.add_many([evento])
    return evento


def _feed(social_uow, user_uow, papelera=None) -> GetFriendsFeedUseCase:
    return GetFriendsFeedUseCase(
        social_uow, user_uow, InMemoryGolfCourseUnitOfWork(), quick_match_trash=papelera
    )


def _actividad(social_uow, user_uow, papelera=None) -> GetPlayerActivityUseCase:
    return GetPlayerActivityUseCase(
        social_uow, user_uow, InMemoryGolfCourseUnitOfWork(), quick_match_trash=papelera
    )


class _Escena:
    """Ana y Bea juegan la partida M; Xavi es amigo de las dos."""

    def __init__(self, ana, bea, xavi, partida):
        self.ana, self.bea, self.xavi, self.partida = ana, bea, xavi, partida


@pytest.fixture
async def escena(social_uow, user_uow):
    ana, bea, xavi = [await _user(user_uow, n) for n in ("Ana", "Bea", "Xavi")]
    await _amigos(social_uow, xavi, ana)
    await _amigos(social_uow, xavi, bea)
    partida = str(uuid4())
    escena = _Escena(ana, bea, xavi, partida)
    escena.ana_terminada = await _evento(social_uow, ana, T.QUICK_MATCH_FINISHED, partida, 1)
    escena.ana_birdie = await _evento(social_uow, ana, T.BIRDIE, partida, 1)
    escena.bea_terminada = await _evento(social_uow, bea, T.QUICK_MATCH_FINISHED, partida, 2)
    return escena


def _ids(respuesta) -> set[str]:
    return {e.id for e in respuesta.events}


class TestFeedDeUnAmigo:
    async def test_lo_de_la_partida_en_la_papelera_del_autor_no_sale(
        self, social_uow, user_uow, papelera, escena
    ):
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.xavi.id.value))

        assert _ids(feed) == {str(escena.bea_terminada.id)}

    async def test_quien_la_tiro_tampoco_ve_lo_de_otro_jugador_de_esa_partida(
        self, social_uow, user_uow, papelera, escena
    ):
        """Bea la tiro: lo de Ana en esa partida, que Ana no ha tirado, tampoco le sale."""
        await _amigos(social_uow, escena.bea, escena.ana)
        papelera.en_la_papelera.add((escena.partida, escena.bea.id))

        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.bea.id.value))

        assert _ids(feed) == set()

    async def test_la_papelera_de_otro_jugador_no_oculta_lo_del_autor(
        self, social_uow, user_uow, papelera, escena
    ):
        papelera.en_la_papelera.add((escena.partida, escena.bea.id))

        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.xavi.id.value))

        assert _ids(feed) == {str(escena.ana_terminada.id), str(escena.ana_birdie.id)}

    async def test_el_autor_que_la_tiro_tampoco_ve_lo_suyo(
        self, social_uow, user_uow, papelera, escena
    ):
        """Para quien la tiro ha desaparecido: ni en su lista ni en su Actividad."""
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.ana.id.value))

        assert _ids(feed).isdisjoint({str(escena.ana_terminada.id), str(escena.ana_birdie.id)})

    async def test_solo_se_pregunta_por_lo_de_partida_rapida_y_de_una_vez(
        self, social_uow, user_uow, papelera, escena
    ):
        """Ni los avisos de torneo: una pregunta, por cada autor y por quien mira."""
        await _evento(
            social_uow, escena.ana, T.ENROLLED_IN_TOURNAMENT, str(uuid4()), 3, competition_id="c"
        )
        otra = str(uuid4())
        await _evento(social_uow, escena.xavi, T.BIRDIE, otra, 4)

        await _feed(social_uow, user_uow, papelera).execute(str(escena.xavi.id.value))

        assert len(papelera.preguntas) == 1
        assert set(papelera.preguntas[0]) == {
            (escena.partida, escena.ana.id),
            (escena.partida, escena.bea.id),
            # Y si quien mira la tiene tirada, aunque no sea suyo lo que sale
            (escena.partida, escena.xavi.id),
            (otra, escena.xavi.id),
        }

    async def test_un_logro_de_torneo_no_se_toca(self, social_uow, user_uow, papelera, escena):
        """Su origen es un partido de torneo, nunca una partida rapida en la papelera."""
        torneo = await _evento(
            social_uow, escena.ana, T.NEW_COURSE, str(uuid4()), 5, from_tournament=True
        )
        papelera.en_la_papelera.add((torneo.source_match_id, escena.ana.id))

        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.xavi.id.value))

        assert str(torneo.id) in _ids(feed)

    async def test_el_cursor_no_pierde_ni_repite_nada(self, social_uow, user_uow, papelera, escena):
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))
        visibles = [str(escena.bea_terminada.id)]
        for minuto in range(3, 7):
            evento = await _evento(
                social_uow, escena.bea, T.QUICK_MATCH_FINISHED, str(uuid4()), minuto
            )
            visibles.append(str(evento.id))

        vistas, cursor = [], None
        for _ in range(10):
            pagina = await _feed(social_uow, user_uow, papelera).execute(
                str(escena.xavi.id.value), limit=2, cursor=cursor
            )
            vistas.extend(e.id for e in pagina.events)
            cursor = pagina.next_cursor
            if cursor is None:
                break

        assert sorted(vistas) == sorted(visibles)
        assert len(vistas) == len(set(vistas))

    async def test_sin_el_puerto_no_se_filtra(self, social_uow, user_uow, escena):
        feed = await _feed(social_uow, user_uow).execute(str(escena.xavi.id.value))

        assert len(feed.events) == 3


class TestActividadDelPerfil:
    async def test_un_amigo_no_la_ve_en_el_perfil_del_autor(
        self, social_uow, user_uow, papelera, escena
    ):
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        actividad = await _actividad(social_uow, user_uow, papelera).execute(
            str(escena.xavi.id.value), str(escena.ana.id.value)
        )

        assert actividad.events == []

    async def test_el_autor_que_la_tiro_tampoco_la_ve_en_su_perfil(
        self, social_uow, user_uow, papelera, escena
    ):
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        actividad = await _actividad(social_uow, user_uow, papelera).execute(
            str(escena.ana.id.value), str(escena.ana.id.value)
        )

        assert actividad.events == []


class TestContador:
    async def test_el_contador_no_cuenta_lo_de_la_papelera_del_autor(
        self, social_uow, user_uow, papelera, escena
    ):
        # El repositorio en memoria no conoce las partidas: se le dice cuales
        social_uow.activity_events.trashed_quick_matches = {(escena.partida, escena.ana.id)}
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        contador = await GetFeedUnseenCountUseCase(social_uow, user_uow).execute(
            str(escena.xavi.id.value)
        )
        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.xavi.id.value))

        # La tarjeta de Bea y nada de Ana
        assert contador.unseen_count == 1
        assert feed.unseen_count == 1
        assert len(feed.events) == 1

    async def test_a_quien_la_tiro_el_contador_no_le_cuenta_nada_de_esa_partida(
        self, social_uow, user_uow, papelera, escena
    ):
        """Ni lo suyo ni lo de Bea, que no la ha tirado: lo mismo que su feed."""
        await _amigos(social_uow, escena.ana, escena.bea)
        sin_papelera = await GetFeedUnseenCountUseCase(social_uow, user_uow).execute(
            str(escena.ana.id.value)
        )
        social_uow.activity_events.trashed_quick_matches = {(escena.partida, escena.ana.id)}
        papelera.en_la_papelera.add((escena.partida, escena.ana.id))

        contador = await GetFeedUnseenCountUseCase(social_uow, user_uow).execute(
            str(escena.ana.id.value)
        )
        feed = await _feed(social_uow, user_uow, papelera).execute(str(escena.ana.id.value))

        assert sin_papelera.unseen_count > 0
        assert contador.unseen_count == 0
        assert feed.unseen_count == 0
        assert feed.events == []
