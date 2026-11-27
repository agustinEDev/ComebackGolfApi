"""
Tests de HideQuickMatchUseCase: la papelera de una partida rapida, que la borra
de verdad cuando la han tirado todos (26 nov 2026).

  #   caso                                        | resultado
  ----|--------------------------------------------|--------------------------------
  H1  la tira el primero de dos                   | queda guardada, tirada para el;
                                                  | no se toca Actividad; `deleted`
                                                  | es False
  H2  la tira el ultimo                           | Actividad la olvida (todos los
                                                  | jugadores con cuenta) y la
                                                  | partida se borra; `deleted` True
  H3  un jugador con cuenta y un invitado         | su papelera ya es el borrado
  H4  el otro jugador tiene la cuenta desactivada | no la retiene: se borra
  H5  Actividad falla al olvidar                  | el fallo sale; la partida sigue
                                                  | ahi y no se cede nada
  H6  partida que no existe                       | QuickMatchNotFoundError
  H7  partida en curso                            | la regla del dominio sale tal
                                                  | cual; nada cambia
  H8  la respuesta de un borrado                  | trae la partida entera, montada
                                                  | antes de borrarla
  H9  repetir tras el borrado                     | QuickMatchNotFoundError
  H10 el «campo nuevo» se cede DESPUES de         | con la partida ya borrada y
      guardar, y SOLO a quien lo tenia por ella   | confirmada; a los demas no se
                                                  | les publica nada
  H11 la partida borrada no tenia «campo nuevo»   | no se cede nada: publicaria un
      (una cancelada, por ejemplo)                | logro que nunca existio
  H12 un borrado de verdad deja registro          | quien, que partida, cuantos
                                                  | eventos; solo identificadores
  H13 a quien no es de la partida se le dice lo   | «no existe», no «no eres de
      mismo que si no existiera                   | aqui»: no delata que existe
"""

from collections.abc import Sequence
from uuid import uuid4

import pytest

from src.modules.golf_course.domain.value_objects.golf_course_id import GolfCourseId
from src.modules.quick_match.application.dto.quick_match_dto import HideQuickMatchRequestDTO
from src.modules.quick_match.application.exceptions import QuickMatchNotFoundError
from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    ForgottenActivity,
    QuickMatchActivityInterface,
)
from src.modules.quick_match.application.use_cases.hide_quick_match_use_case import (
    HideQuickMatchUseCase,
)
from src.modules.quick_match.domain.entities.quick_match import QuickMatch
from src.modules.quick_match.domain.exceptions.quick_match_violations import (
    InvalidQuickMatchStatusViolation,
)
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.quick_match.domain.value_objects.quick_match_participant import (
    QuickMatchParticipant,
)
from src.modules.user.domain.value_objects.user_id import UserId
from src.shared.domain.value_objects.match_format import MatchFormat
from tests.unit.modules.quick_match.conftest import create_user

pytestmark = pytest.mark.asyncio


class _Actividad(QuickMatchActivityInterface):
    """Apunta lo que se le pide, y si la partida ya estaba guardada al cederlo."""

    def __init__(self, qm_uow, falla: Exception | None = None, con_campo_nuevo=()):
        self._qm_uow = qm_uow
        self._falla = falla
        # Los jugadores que tenian «campo nuevo» por la partida que se borra
        self._con_campo_nuevo = tuple(con_campo_nuevo)
        self.olvidadas: list[tuple[str, list[UserId]]] = []
        self.cedidas: list[tuple[str, list[UserId], bool, bool]] = []

    async def forget(self, quick_match_id: str, player_ids: Sequence[UserId]) -> ForgottenActivity:
        if self._falla is not None:
            raise self._falla
        self.olvidadas.append((quick_match_id, list(player_ids)))
        return ForgottenActivity(events=3, new_course_holders=self._con_campo_nuevo)

    async def hand_over_new_course(self, golf_course_id: str, player_ids: Sequence[UserId]) -> None:
        sigue = await self._qm_uow.quick_matches.count_all() > 0
        self.cedidas.append((golf_course_id, list(player_ids), self._qm_uow.committed, sigue))


async def _terminada(qm_uow, creador: UserId, *otros: QuickMatchParticipant, empezada=True):
    qm = QuickMatch.create(
        id=QuickMatchId.generate(),
        creator_id=creador,
        golf_course_id=GolfCourseId(uuid4()),
        match_format=MatchFormat.SINGLES,
    )
    for otro in otros:
        qm.add_participant(otro)
    if empezada:
        qm.start([qm.creator_participant_id])
        qm.complete()
    async with qm_uow:
        await qm_uow.quick_matches.add(qm)
    return qm


def _pedir(qm, quien: UserId) -> HideQuickMatchRequestDTO:
    return HideQuickMatchRequestDTO(quick_match_id=qm.id.value, requester_id=quien.value)


@pytest.fixture
def actividad(qm_uow):
    return _Actividad(qm_uow)


class TestHideQuickMatchUseCase:
    async def test_h1_the_first_of_two_only_hides_it_for_themselves(
        self, qm_uow, user_uow, actividad
    ):
        ana = await create_user(user_uow, "ana-h1@test.com")
        bea = await create_user(user_uow, "bea-h1@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_user(bea.id))

        respuesta = await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
            _pedir(qm, bea.id)
        )

        guardada = await qm_uow.quick_matches.find_by_id(qm.id)
        assert guardada.is_hidden_for(guardada.participants[1].participant_id)
        assert not guardada.is_hidden_for(guardada.creator_participant_id)
        assert respuesta.deleted is False
        assert (actividad.olvidadas, actividad.cedidas) == ([], [])

    async def test_h2_the_last_one_deletes_it_for_real(self, qm_uow, user_uow, actividad):
        ana = await create_user(user_uow, "ana-h2@test.com")
        bea = await create_user(user_uow, "bea-h2@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_user(bea.id))
        caso = HideQuickMatchUseCase(qm_uow, user_uow, actividad)
        await caso.execute(_pedir(qm, ana.id))

        respuesta = await caso.execute(_pedir(qm, bea.id))

        assert await qm_uow.quick_matches.find_by_id(qm.id) is None
        assert respuesta.deleted is True
        assert len(actividad.olvidadas) == 1
        partida, jugadores = actividad.olvidadas[0]
        assert partida == str(qm.id.value)
        assert set(jugadores) == {ana.id, bea.id}

    async def test_h3_with_a_single_registered_player_the_trash_is_the_deletion(
        self, qm_uow, user_uow, actividad
    ):
        ana = await create_user(user_uow, "ana-h3@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))

        respuesta = await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
            _pedir(qm, ana.id)
        )

        assert respuesta.deleted is True
        assert await qm_uow.quick_matches.find_by_id(qm.id) is None
        assert actividad.olvidadas == [(str(qm.id.value), [ana.id])]

    async def test_h4_a_deactivated_player_does_not_hold_it(self, qm_uow, user_uow, actividad):
        ana = await create_user(user_uow, "ana-h4@test.com")
        bea = await create_user(user_uow, "bea-h4@test.com")
        bea.deactivate()
        async with user_uow:
            await user_uow.users.save(bea)
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_user(bea.id))

        respuesta = await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
            _pedir(qm, ana.id)
        )

        assert respuesta.deleted is True
        assert await qm_uow.quick_matches.find_by_id(qm.id) is None
        # Lo de Bea en Actividad tambien se olvida: la partida ya no existe
        assert set(actividad.olvidadas[0][1]) == {ana.id, bea.id}

    async def test_h5_if_the_activity_cannot_forget_nothing_is_deleted(self, qm_uow, user_uow):
        ana = await create_user(user_uow, "ana-h5@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))
        rota = _Actividad(qm_uow, falla=RuntimeError("sin base de datos"))

        with pytest.raises(RuntimeError):
            await HideQuickMatchUseCase(qm_uow, user_uow, rota).execute(_pedir(qm, ana.id))

        assert await qm_uow.quick_matches.find_by_id(qm.id) is not None
        assert qm_uow.committed is False
        assert rota.cedidas == []

    async def test_h6_not_found_raises(self, qm_uow, user_uow, actividad):
        with pytest.raises(QuickMatchNotFoundError):
            await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
                HideQuickMatchRequestDTO(quick_match_id=uuid4(), requester_id=uuid4())
            )

    async def test_h7_a_match_in_play_is_not_trashed(self, qm_uow, user_uow, actividad):
        ana = await create_user(user_uow, "ana-h7@test.com")
        qm = await _terminada(qm_uow, ana.id, empezada=False)

        with pytest.raises(InvalidQuickMatchStatusViolation):
            await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(_pedir(qm, ana.id))

        guardada = await qm_uow.quick_matches.find_by_id(qm.id)
        assert guardada.hidden_by_participant_ids == []
        assert (actividad.olvidadas, actividad.cedidas) == ([], [])

    async def test_h8_the_answer_of_a_deletion_still_carries_the_match(
        self, qm_uow, user_uow, actividad
    ):
        ana = await create_user(user_uow, "ana-h8@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))

        respuesta = await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
            _pedir(qm, ana.id)
        )

        assert respuesta.id == qm.id.value
        assert respuesta.status == "COMPLETED"
        assert [p.name for p in respuesta.participants] == [ana.display_name, "Gon Invitado"]

    async def test_h9_asking_again_after_the_deletion_is_not_found(
        self, qm_uow, user_uow, actividad
    ):
        ana = await create_user(user_uow, "ana-h9@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))
        caso = HideQuickMatchUseCase(qm_uow, user_uow, actividad)
        await caso.execute(_pedir(qm, ana.id))

        with pytest.raises(QuickMatchNotFoundError):
            await caso.execute(_pedir(qm, ana.id))

    async def test_h10_the_new_course_is_handed_over_once_saved_and_only_to_its_holder(
        self, qm_uow, user_uow
    ):
        ana = await create_user(user_uow, "ana-h10@test.com")
        bea = await create_user(user_uow, "bea-h10@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_user(bea.id))
        actividad = _Actividad(qm_uow, con_campo_nuevo=[bea.id])
        caso = HideQuickMatchUseCase(qm_uow, user_uow, actividad)
        await caso.execute(_pedir(qm, ana.id))
        assert actividad.cedidas == []

        await caso.execute(_pedir(qm, bea.id))

        assert len(actividad.cedidas) == 1
        campo, jugadores, ya_guardado, sigue_la_partida = actividad.cedidas[0]
        assert campo == str(qm.golf_course_id.value)
        # Solo Bea: Ana no tenia «campo nuevo» por esta partida
        assert jugadores == [bea.id]
        assert (ya_guardado, sigue_la_partida) == (True, False)

    async def test_h11_without_a_new_course_nothing_is_handed_over(
        self, qm_uow, user_uow, actividad
    ):
        ana = await create_user(user_uow, "ana-h11@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))

        respuesta = await HideQuickMatchUseCase(qm_uow, user_uow, actividad).execute(
            _pedir(qm, ana.id)
        )

        assert respuesta.deleted is True
        assert actividad.cedidas == []

    async def test_h12_a_real_deletion_leaves_a_record(self, qm_uow, user_uow, actividad, caplog):
        ana = await create_user(user_uow, "ana-h12@test.com")
        bea = await create_user(user_uow, "bea-h12@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_user(bea.id))
        caso = HideQuickMatchUseCase(qm_uow, user_uow, actividad)

        with caplog.at_level("INFO"):
            await caso.execute(_pedir(qm, ana.id))
            assert "deleted for good" not in caplog.text
            await caso.execute(_pedir(qm, bea.id))

        [registro] = [r for r in caplog.records if "deleted for good" in r.getMessage()]
        texto = registro.getMessage()
        # Que partida, quien lo disparo, de quienes era y cuanto se llevo
        assert str(qm.id.value) in texto
        assert str(bea.id.value) in texto
        assert str(ana.id.value) in texto
        assert "3 activity events" in texto
        # Solo identificadores: ni nombres ni correos
        assert "@" not in texto
        assert ana.display_name not in texto

    async def test_h13_a_stranger_is_told_it_does_not_exist(self, qm_uow, user_uow, actividad):
        ana = await create_user(user_uow, "ana-h13@test.com")
        ajeno = await create_user(user_uow, "ajeno-h13@test.com")
        qm = await _terminada(qm_uow, ana.id, QuickMatchParticipant.for_guest("Gon", "Invitado"))
        caso = HideQuickMatchUseCase(qm_uow, user_uow, actividad)

        with pytest.raises(QuickMatchNotFoundError) as de_un_ajeno:
            await caso.execute(_pedir(qm, ajeno.id))
        with pytest.raises(QuickMatchNotFoundError) as de_una_que_no_existe:
            await caso.execute(
                HideQuickMatchRequestDTO(quick_match_id=uuid4(), requester_id=ajeno.id.value)
            )

        # El mismo mensaje, salvo el id: no se distingue una de otra
        assert (
            str(de_un_ajeno.value).replace(str(qm.id.value), "X").split(":")[0]
            == str(de_una_que_no_existe.value).split(":")[0]
        )
        assert await qm_uow.quick_matches.find_by_id(qm.id) is not None
