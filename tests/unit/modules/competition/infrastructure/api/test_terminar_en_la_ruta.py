"""
`POST /competitions/{id}/complete` con algo sin cerrar (I1, 22 nov 2026): 409
PENDING_GAMES con un texto fijo que dice cuántos quedan, sin ids.
"""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.modules.competition.application.exceptions import PendingGamesError
from src.modules.competition.infrastructure.api.v1 import competition_state_routes
from src.modules.user.application.dto.user_dto import UserResponseDTO


@pytest.mark.asyncio
async def test_complete_with_pending_games_answers_409_with_how_many():
    """
    Given un caso de uso que no termina: quedan 2 partidos y 1 partida
    When llega la petición de terminar
    Then 409 PENDING_GAMES con cuántos en el texto y en sus campos, y no se
        pide la vista de la competición
    """
    caso = AsyncMock()
    caso.execute.side_effect = PendingGamesError(2, 1)
    vista = AsyncMock()
    quien = UserResponseDTO.model_construct(id=uuid4(), email="o@test.com", is_admin=False)

    respuesta = await competition_state_routes.complete_competition.__wrapped__(
        MagicMock(), uuid4(), quien, caso, vista
    )

    assert respuesta.status_code == 409
    assert json.loads(respuesta.body) == {
        "detail": (
            "Finish or close what is still pending first: 2 Ryder match(es) and "
            "1 stroke play group(s)."
        ),
        "error_code": "PENDING_GAMES",
        "pending_matches": 2,
        "pending_groups": 1,
    }
    vista.de.assert_not_awaited()
