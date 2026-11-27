"""
Las rutas de las barras por campo (20 nov 2026): lo que no se puede llega con su
código y un texto fijo, y pasan al caso de uso quién lo pide y si es admin.
"""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.modules.competition.application.exceptions import (
    CourseNotInCompetitionError,
    CourseTeeNotAvailableError,
    EnrollmentNotApprovedError,
    PendingGameNotRecalculableError,
    PlayerTeeChangeInProgressError,
    TeeChangeClosedError,
    TeeNotAvailableError,
    TeeNotSelectableError,
)
from src.modules.competition.application.use_cases.request_enrollment_use_case import (
    TeeRequiredError,
)
from src.modules.competition.infrastructure.api.v1 import (
    competition_golf_course_routes,
    enrollment_routes,
)
from src.modules.golf_course.domain.value_objects.tee_color import TeeColor
from src.modules.user.application.dto.user_dto import UserResponseDTO
from src.shared.domain.value_objects.gender import Gender

NEGATIVAS = [
    (TeeNotAvailableError, "TEE_NOT_AVAILABLE", 422),
    (TeeChangeClosedError, "TEE_CHANGE_CLOSED", 409),
    (PendingGameNotRecalculableError, "PENDING_GAME_NOT_RECALCULABLE", 409),
    (EnrollmentNotApprovedError, "ENROLLMENT_NOT_APPROVED", 409),
    (CourseNotInCompetitionError, "COURSE_NOT_IN_COMPETITION", 404),
]


def _quien(is_admin=False) -> UserResponseDTO:
    return UserResponseDTO.model_construct(id=uuid4(), email="o@test.com", is_admin=is_admin)


async def _propia(caso, quien=None, color=TeeColor.BLUE):
    return await enrollment_routes.change_enrollment_course_tee(
        uuid4(),
        uuid4(),
        enrollment_routes.ChangeCourseTeeBody(tee_color=color),
        quien or _quien(),
        caso,
    )


async def _del_campo(caso, quien=None, color=TeeColor.BLUE):
    return await competition_golf_course_routes.set_competition_course_tee(
        uuid4(),
        uuid4(),
        competition_golf_course_routes.SetCourseTeeBody(gender=Gender.FEMALE, tee_color=color),
        quien or _quien(),
        caso,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ruta", [_propia, _del_campo])
@pytest.mark.parametrize(("error", "codigo", "estado"), NEGATIVAS)
async def test_course_tee_refused_answers_its_code_and_a_fixed_text(ruta, error, codigo, estado):
    """
    Given un caso de uso que no deja fijar la barra
    When llega la petición a cualquiera de las dos rutas
    Then su código HTTP, su error_code y un texto fijo, no el de la excepción
    """
    caso = AsyncMock()
    caso.execute.side_effect = error("texto interno con datos")

    respuesta = await ruta(caso)

    assert respuesta.status_code == estado
    cuerpo = json.loads(respuesta.body)
    assert cuerpo["error_code"] == codigo
    assert "texto interno" not in cuerpo["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_enrollment_course_tee_passes_the_ids_the_tee_and_who_asks(is_admin):
    """
    Given una petición para fijar azules en un campo
    When llega a la ruta de la inscripción
    Then el caso de uso recibe inscripción, campo, barra, quién y si es admin
    """
    caso = AsyncMock()
    quien = _quien(is_admin)
    inscripcion, campo = uuid4(), uuid4()

    await enrollment_routes.change_enrollment_course_tee(
        inscripcion, campo, enrollment_routes.ChangeCourseTeeBody(tee_color=None), quien, caso
    )

    peticion, usuario = caso.execute.call_args.args
    assert (peticion.enrollment_id, peticion.golf_course_id, peticion.tee_color) == (
        inscripcion,
        campo,
        None,
    )
    assert str(usuario.value) == str(quien.id)
    assert caso.execute.call_args.kwargs == {"is_admin": is_admin}


@pytest.mark.asyncio
async def test_competition_course_tee_passes_the_gender_and_the_tee():
    """
    Given una petición para fijar azules a las mujeres en un campo
    When llega a la ruta de la competición
    Then el caso de uso recibe competición, campo, género y barra
    """
    caso = AsyncMock()
    competicion, campo = uuid4(), uuid4()

    await competition_golf_course_routes.set_competition_course_tee(
        competicion,
        campo,
        competition_golf_course_routes.SetCourseTeeBody(
            gender=Gender.FEMALE, tee_color=TeeColor.BLUE
        ),
        _quien(),
        caso,
    )

    peticion = caso.execute.call_args.args[0]
    assert (peticion.competition_id, peticion.golf_course_id) == (competicion, campo)
    assert (peticion.gender, peticion.tee_color) == (Gender.FEMALE, TeeColor.BLUE)


def test_competition_course_tee_body_rejects_an_unknown_gender():
    """
    Given un género que no es MALE ni FEMALE
    When se valida el cuerpo
    Then no pasa (422 de FastAPI)
    """
    with pytest.raises(ValueError):
        competition_golf_course_routes.SetCourseTeeBody(gender="OTHER", tee_color=None)


@pytest.mark.asyncio
async def test_course_tee_for_a_gender_not_available_has_its_own_text():
    """
    Given la barra del campo para un género que ese campo no tiene
    When llega a la ruta de la competición
    Then 422 TEE_NOT_AVAILABLE con el texto del género y el campo, no el del jugador
    """
    caso = AsyncMock()
    caso.execute.side_effect = CourseTeeNotAvailableError("interno")

    respuesta = await _del_campo(caso)

    cuerpo = json.loads(respuesta.body)
    assert respuesta.status_code == 422
    assert cuerpo == {
        "detail": "That tee is not available for this gender on this course.",
        "error_code": "TEE_NOT_AVAILABLE",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_competition_course_tees_passes_the_competition_and_who_asks(is_admin):
    """
    Given una petición de lo fijado por campo (tabla del 21 nov 2026, A)
    When llega a la ruta
    Then el caso de uso recibe la competición, quién y si es admin, y se devuelve lo suyo
    """
    caso = AsyncMock()
    caso.execute.return_value = []
    quien = _quien(is_admin)
    competicion = uuid4()

    respuesta = await competition_golf_course_routes.get_competition_course_tees(
        competicion, quien, caso
    )

    pedida, usuario = caso.execute.call_args.args
    assert pedida.competition_id == competicion
    assert str(usuario.value) == str(quien.id)
    assert caso.execute.call_args.kwargs == {"is_admin": is_admin}
    assert respuesta == []


async def _general(caso, quien=None):
    return await enrollment_routes.change_enrollment_tee(
        uuid4(), enrollment_routes.ChangeTeeBody(tee_color=TeeColor.OTHER), quien or _quien(), caso
    )


async def _apuntarse(caso, quien=None):
    return await enrollment_routes.request_enrollment(
        uuid4(), enrollment_routes.RequestEnrollmentBody(tee_color="OTHER"), quien or _quien(), caso
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ruta", [_apuntarse, _general, _propia, _del_campo])
async def test_other_tee_answers_422_tee_not_available_with_its_own_text(ruta):
    """
    Given un caso de uso que rechaza OTHER (tabla del 21 nov 2026, C)
    When llega a inscribirse, a la barra general o a cualquiera de las de un campo
    Then 422 TEE_NOT_AVAILABLE con su texto fijo, no el de la excepción
    """
    caso = AsyncMock()
    caso.execute.side_effect = TeeNotSelectableError("texto interno")

    respuesta = await ruta(caso)

    assert respuesta.status_code == 422
    assert json.loads(respuesta.body) == {
        "detail": "That tee cannot be chosen: pick one of the course's tee colors.",
        "error_code": "TEE_NOT_AVAILABLE",
    }


@pytest.mark.asyncio
async def test_own_course_tee_by_the_player_in_progress_answers_403_with_its_code():
    """
    Given un caso de uso que no deja al propio jugador fijar su barra en un campo
        con la competición en curso
    When llega la petición
    Then 403 PLAYER_TEE_CHANGE_IN_PROGRESS con su texto fijo (G1, 22 nov 2026)
    """
    caso = AsyncMock()
    caso.execute.side_effect = PlayerTeeChangeInProgressError("texto interno")

    respuesta = await _propia(caso)

    assert respuesta.status_code == 403
    cuerpo = json.loads(respuesta.body)
    assert cuerpo["error_code"] == "PLAYER_TEE_CHANGE_IN_PROGRESS"
    assert cuerpo["detail"].startswith("With the competition in progress")


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [None, enrollment_routes.RequestEnrollmentBody()])
async def test_enrolling_without_a_tee_answers_422_tee_required(body):
    """
    Given un caso de uso que no deja entrar sin barra general (H1, 22 nov 2026)
    When llega la inscripción sin cuerpo o sin barra
    Then el caso de uso la recibe sin barra, y la respuesta es 422 TEE_REQUIRED con
        su texto fijo, no el de la excepción
    """
    caso = AsyncMock()
    caso.execute.side_effect = TeeRequiredError("texto interno")

    respuesta = await enrollment_routes.request_enrollment(uuid4(), body, _quien(), caso)

    assert caso.execute.call_args.args[0].tee_color is None
    assert respuesta.status_code == 422
    assert json.loads(respuesta.body) == {
        "detail": "Choose your tee to enroll.",
        "error_code": "TEE_REQUIRED",
    }
