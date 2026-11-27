"""
Cambiar las barras de una inscripción por la API (BE #912, 20 nov 2026).

| Caso                                                   | Respuesta                        |
|--------------------------------------------------------|----------------------------------|
| La jugadora, rojas de mujer que el campo tiene          | 200 con RED                      |
| La jugadora, azules que el campo no tiene, sin pendiente | 200: su barra de siempre         |
| Otro jugador                                           | 403                              |
| El organizador vuelve a las de por defecto (null)      | 200 sin barras                   |
| Un color que no existe                                 | 422 de validación                |
| La jugadora, con la competición en curso (G1)          | 403 PLAYER_TEE_CHANGE_IN_PROGRESS (también en un campo) |
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    approve_golf_course,
    create_admin_user,
    create_authenticated_user,
    create_competition,
    create_golf_course,
    inscrito_por_invitacion,
    set_auth_cookies,
    sql_en_la_bd_de_test,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BARRAS = [
    {
        "identifier": "Amarillo",
        "color": "YELLOW",
        "tee_gender": "MALE",
        "course_rating": 70.2,
        "slope_rating": 128,
        "par": 72,
    },
    {
        "identifier": "Rojo",
        "color": "RED",
        "tee_gender": "FEMALE",
        "course_rating": 71.0,
        "slope_rating": 124,
        "par": 72,
    },
]


async def _usuario(client: AsyncClient, gender: str) -> dict:
    return await create_authenticated_user(
        client,
        f"barras-{uuid.uuid4().hex[:8]}@test.com",
        "P@ssw0rd123!",
        "Bea",
        "Rras",
        gender=gender,
    )


async def _montar(client: AsyncClient) -> tuple[dict, dict, dict, str]:
    """Una competición con un campo de amarillas de hombre y rojas de mujer, y una invitada."""
    organizador = await _usuario(client, "MALE")
    jugadora = await _usuario(client, "FEMALE")
    otro = await _usuario(client, "MALE")
    competicion = await create_competition(client, organizador["cookies"])
    admin = await create_admin_user(
        client, f"admin-{uuid.uuid4()}@test.com", "P@ssw0rd123!", "Admin", "Barras"
    )
    campo = await create_golf_course(
        client,
        organizador["cookies"],
        {
            "name": f"Campo barras {uuid.uuid4().hex[:8]}",
            "country_code": "ES",
            "course_type": "STANDARD_18",
            "tees": BARRAS,
            "holes": [{"hole_number": i, "par": 4, "stroke_index": i} for i in range(1, 19)],
        },
    )
    await approve_golf_course(client, admin["cookies"], campo["id"])
    set_auth_cookies(client, organizador["cookies"])
    anadido = await client.post(
        f"/api/v1/competitions/{competicion['id']}/golf-courses",
        json={"golf_course_id": campo["id"]},
    )
    assert anadido.status_code == 201, anadido.text
    aceptada = await inscrito_por_invitacion(
        client, organizador["cookies"], competicion["id"], jugadora
    )
    # La competición, a mano de quien la necesite (barras por campo)
    organizador["competition_id"] = competicion["id"]
    return organizador, jugadora, otro, aceptada["enrollment_id"]


async def _cambiar(client: AsyncClient, quien: dict, inscripcion: str, color):
    set_auth_cookies(client, quien["cookies"])
    return await client.put(f"/api/v1/enrollments/{inscripcion}/tee", json={"tee_color": color})


async def test_the_player_changes_to_a_rated_tee(client: AsyncClient):
    """
    Given una jugadora invitada en un campo con rojas de mujer
    When cambia sus barras a rojas
    Then 200 con RED
    """
    _, jugadora, _, inscripcion = await _montar(client)

    respuesta = await _cambiar(client, jugadora, inscripcion, "RED")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tee_color"] == "RED"


async def test_a_tee_no_course_has_for_her_without_pending_is_saved(client: AsyncClient):
    """
    Given un campo sin azules de mujer y nada pendiente
    When la jugadora elige azules
    Then 200: la general es su barra de siempre, como al inscribirse
    """
    _, jugadora, _, inscripcion = await _montar(client)

    respuesta = await _cambiar(client, jugadora, inscripcion, "BLUE")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tee_color"] == "BLUE"


async def test_another_player_cannot_change_it(client: AsyncClient):
    """
    Given una jugadora inscrita
    When otro jugador intenta cambiarle las barras
    Then 403
    """
    _, _, otro, inscripcion = await _montar(client)

    respuesta = await _cambiar(client, otro, inscripcion, "RED")

    assert respuesta.status_code == 403, respuesta.text


async def test_the_organizer_goes_back_to_the_default(client: AsyncClient):
    """
    Given una jugadora que eligió rojas
    When el organizador las devuelve a las de por defecto (null)
    Then 200 sin barras
    """
    organizador, jugadora, _, inscripcion = await _montar(client)
    primera = await _cambiar(client, jugadora, inscripcion, "RED")
    assert primera.status_code == 200, primera.text

    respuesta = await _cambiar(client, organizador, inscripcion, None)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tee_color"] is None


async def test_an_unknown_colour_is_a_validation_error(client: AsyncClient):
    """
    Given un color que no es de las barras
    When la jugadora lo pide
    Then 422 de validación
    """
    _, jugadora, _, inscripcion = await _montar(client)

    respuesta = await _cambiar(client, jugadora, inscripcion, "PURPLE")

    assert respuesta.status_code == 422, respuesta.text


async def test_the_player_in_progress_is_told_who_can_change_it(client: AsyncClient):
    """
    Given una jugadora inscrita y la competición en curso
    When cambia su barra general y la de su campo
    Then las dos, 403 PLAYER_TEE_CHANGE_IN_PROGRESS con el texto de quién puede (G1)
    """
    organizador, jugadora, _, inscripcion = await _montar(client)
    set_auth_cookies(client, jugadora["cookies"])
    barras = await client.get(f"/api/v1/enrollments/{inscripcion}/tees")
    campo = barras.json()["courses"][0]["golf_course_id"]
    await sql_en_la_bd_de_test(
        "UPDATE competitions SET status = 'IN_PROGRESS' WHERE id = :id",
        id=organizador["competition_id"],
    )

    general = await _cambiar(client, jugadora, inscripcion, "RED")
    del_campo = await client.put(
        f"/api/v1/enrollments/{inscripcion}/courses/{campo}/tee", json={"tee_color": "RED"}
    )

    for respuesta in (general, del_campo):
        assert respuesta.status_code == 403, respuesta.text
        assert respuesta.json() == {
            "detail": (
                "With the competition in progress, your tee is changed by your captain "
                "or the organizer."
            ),
            "error_code": "PLAYER_TEE_CHANGE_IN_PROGRESS",
        }


async def test_her_own_withdrawn_enrollment_is_always_not_approved(client: AsyncClient):
    """
    Given una jugadora que se retiró de la competición
    When cambia su barra general y la de su campo (22 nov 2026: «siempre la misma
        respuesta para el mismo error»), y otro jugador lo intenta con la suya
    Then a ella, las dos, 409 ENROLLMENT_NOT_APPROVED; al otro, 403
    """
    _, jugadora, otro, inscripcion = await _montar(client)
    set_auth_cookies(client, jugadora["cookies"])
    campo = (await client.get(f"/api/v1/enrollments/{inscripcion}/tees")).json()["courses"][0][
        "golf_course_id"
    ]
    retirada = await client.post(f"/api/v1/enrollments/{inscripcion}/withdraw")
    assert retirada.status_code == 200, retirada.text

    general = await _cambiar(client, jugadora, inscripcion, "RED")
    del_campo = await client.put(
        f"/api/v1/enrollments/{inscripcion}/courses/{campo}/tee", json={"tee_color": "RED"}
    )
    ajena = await _cambiar(client, otro, inscripcion, "RED")

    for respuesta in (general, del_campo):
        assert respuesta.status_code == 409, respuesta.text
        assert respuesta.json()["error_code"] == "ENROLLMENT_NOT_APPROVED"
    assert ajena.status_code == 403, ajena.text
