"""
La ruta de generar partidos con un emparejamiento a mano fuera de su equipo
(tabla del 21 nov 2026, D): 422 PAIRING_PLAYER_NOT_IN_TEAM con un texto fijo. Y
con uno sin inscripción (J1, 22 nov 2026): el 400 del bloqueo, con quién.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.modules.competition.application.dto.round_match_dto import GenerateMatchesBodyDTO
from src.modules.competition.application.exceptions import PairingPlayerNotInTeamError
from src.modules.competition.application.services.bloqueos_al_generar import (
    PairedPlayersNotEnrolledError,
)
from src.modules.competition.domain.value_objects.match_generation_block import (
    MISSING_ENROLLMENT,
    NOT_ENOUGH_PLAYERS,
    BlockedPlayer,
    MatchGenerationBlock,
)
from src.modules.competition.infrastructure.api.v1 import round_match_routes
from src.modules.user.application.dto.user_dto import UserResponseDTO
from src.modules.user.domain.value_objects.user_id import UserId


@pytest.mark.asyncio
async def test_generate_with_a_pairing_out_of_its_team_answers_422_with_a_fixed_text():
    """
    Given un caso de uso que rechaza un emparejamiento fuera de su equipo
    When llega a la ruta de generar partidos
    Then 422 PAIRING_PLAYER_NOT_IN_TEAM, sin el texto de la excepción
    """
    caso = AsyncMock()
    caso.execute.side_effect = PairingPlayerNotInTeamError("texto interno con datos")
    quien = UserResponseDTO.model_construct(id=uuid4(), email="o@test.com", is_admin=False)

    respuesta = await round_match_routes.generate_matches.__wrapped__(
        MagicMock(), uuid4(), GenerateMatchesBodyDTO(manual_pairings=[]), quien, caso
    )

    assert respuesta.status_code == 422
    assert json.loads(respuesta.body) == {
        "detail": "Each paired player must be on their own team's side.",
        "error_code": "PAIRING_PLAYER_NOT_IN_TEAM",
    }


@pytest.mark.asyncio
async def test_generate_with_a_paired_player_not_enrolled_answers_400_with_its_block():
    """
    Given un caso de uso que rechaza a un emparejado a mano sin inscripción, con su
        motivo sin apuntar en la sesión (J1, 22 nov 2026)
    When llega a la ruta de generar partidos
    Then 400 MATCH_GENERATION_BLOCKED con el motivo NOT_ENOUGH_PLAYERS y quién, sin
        el texto de la excepción
    """
    sin_inscripcion = UserId(uuid4())
    error = PairedPlayersNotEnrolledError(
        [BlockedPlayer(user_id=sin_inscripcion, name="Bea", missing=MISSING_ENROLLMENT)]
    )
    motivo = MatchGenerationBlock(
        reason=NOT_ENOUGH_PLAYERS, players=tuple(error.players), at=datetime(2026, 11, 22)
    )
    setattr(error, "_motivo_apuntado", motivo)  # noqa: B010 - como el caso de uso
    caso = AsyncMock()
    caso.execute.side_effect = error
    quien = UserResponseDTO.model_construct(id=uuid4(), email="o@test.com", is_admin=False)

    respuesta = await round_match_routes.generate_matches.__wrapped__(
        MagicMock(), uuid4(), GenerateMatchesBodyDTO(manual_pairings=[]), quien, caso
    )

    assert respuesta.status_code == 400
    cuerpo = json.loads(respuesta.body)
    assert cuerpo["error_code"] == "MATCH_GENERATION_BLOCKED"
    assert cuerpo["match_generation_block"]["reason"] == "NOT_ENOUGH_PLAYERS"
    assert [p["user_id"] for p in cuerpo["match_generation_block"]["players"]] == [
        str(sin_inscripcion.value)
    ]
    assert "No se pueden generar los partidos: no tienen" not in cuerpo["detail"]
