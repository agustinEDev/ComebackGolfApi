"""
Las barras de una inscripción que no está aprobada (decisión de Agustín, 22 nov 2026:
«siempre la misma respuesta para el mismo error»).

Su propia titular recibe siempre el 409 de no aprobada (ENROLLMENT_NOT_APPROVED) al
cambiar su barra general o la de un campo, sea cual sea el estado de la competición
y antes de las demás comprobaciones de estado. Cualquier otra persona, el 403 de
permisos primero: no se le dice nada de una inscripción ajena.

| Quién          | Competición                                  | Ruta            | Resultado |
|----------------|----------------------------------------------|-----------------|-----------|
| Su titular     | ACTIVE, CLOSED, IN_PROGRESS, COMPLETED,      | general o campo | 409       |
|                | CANCELLED                                    |                 |           |
| Otro jugador   | las mismas                                   | general o campo | 403       |

Con la inscripción invitada, solicitada, rechazada, cancelada o retirada.
"""

import pytest

from src.modules.competition.application.dto.enrollment_dto import (
    ChangeEnrollmentCourseTeeRequestDTO,
    ChangeEnrollmentTeeRequestDTO,
)
from src.modules.competition.application.exceptions import (
    EnrollmentNotApprovedError,
    NotCompetitionCreatorError,
)
from src.modules.competition.application.use_cases.change_enrollment_course_tee_use_case import (
    ChangeEnrollmentCourseTeeUseCase,
)
from src.modules.competition.domain.value_objects.enrollment_status import EnrollmentStatus
from src.modules.golf_course.domain.value_objects.tee_color import TeeColor
from tests.unit.modules.competition.application.use_cases.test_change_enrollment_tee_use_case import (
    _Mundo,
)

pytestmark = pytest.mark.asyncio

ESTADOS_DE_LA_COMPETICION = ["ACTIVE", "CLOSED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
NO_APROBADAS = [
    EnrollmentStatus.INVITED,
    EnrollmentStatus.REQUESTED,
    EnrollmentStatus.REJECTED,
    EnrollmentStatus.CANCELLED,
    EnrollmentStatus.WITHDRAWN,
]


async def _llevar_a(mundo: _Mundo, estado: str) -> None:
    if estado in ("CLOSED", "IN_PROGRESS", "COMPLETED"):
        await mundo.cerrar()
    if estado in ("IN_PROGRESS", "COMPLETED"):
        await mundo.empezar()
    if estado == "COMPLETED":
        await mundo.terminar()
    if estado == "CANCELLED":
        await mundo.cancelar()


async def _cambiar(mundo: _Mundo, ruta: str, inscripcion, quien):
    if ruta == "general":
        return await mundo.caso().execute(
            ChangeEnrollmentTeeRequestDTO(
                enrollment_id=inscripcion.id.value, tee_color=TeeColor.RED
            ),
            quien,
        )
    return await ChangeEnrollmentCourseTeeUseCase(
        mundo.uow, golf_course_repository=mundo.campos, user_repository=mundo.usuarios
    ).execute(
        ChangeEnrollmentCourseTeeRequestDTO(
            enrollment_id=inscripcion.id.value,
            golf_course_id=next(iter(mundo.campos.por_id)).value,
            tee_color=TeeColor.RED,
        ),
        quien,
    )


@pytest.mark.parametrize("ruta", ["general", "campo"])
@pytest.mark.parametrize("estado", ESTADOS_DE_LA_COMPETICION)
@pytest.mark.parametrize("no_aprobada", NO_APROBADAS)
async def test_her_own_enrollment_not_approved_is_always_409(ruta, estado, no_aprobada):
    """
    Given una inscripción no aprobada y la competición en cada uno de sus estados
    When su propia titular cambia su barra general o la de un campo
    Then siempre 409 ENROLLMENT_NOT_APPROVED, y nada se bloquea
    """
    mundo = await _Mundo().montar()
    inscripcion = await mundo.inscripcion_en(no_aprobada)
    await _llevar_a(mundo, estado)
    bloqueos = []
    original = mundo.uow.competitions.find_by_id_for_update

    async def espia(competition_id):
        bloqueos.append(competition_id)
        return await original(competition_id)

    mundo.uow.competitions.find_by_id_for_update = espia

    with pytest.raises(EnrollmentNotApprovedError) as error:
        await _cambiar(mundo, ruta, inscripcion, inscripcion.user_id)

    assert error.value.error_code == "ENROLLMENT_NOT_APPROVED"
    assert bloqueos == []


@pytest.mark.parametrize("ruta", ["general", "campo"])
@pytest.mark.parametrize("estado", ESTADOS_DE_LA_COMPETICION)
async def test_someone_else_gets_the_403_first(ruta, estado):
    """
    Given la inscripción retirada de otra jugadora y la competición en cada estado
    When otro jugador intenta cambiar sus barras
    Then el 403 de permisos: no se le dice que no está aprobada
    """
    mundo = await _Mundo().montar()
    inscripcion = await mundo.inscripcion_en(EnrollmentStatus.WITHDRAWN)
    await _llevar_a(mundo, estado)

    with pytest.raises(NotCompetitionCreatorError):
        await _cambiar(mundo, ruta, inscripcion, mundo.otro)
