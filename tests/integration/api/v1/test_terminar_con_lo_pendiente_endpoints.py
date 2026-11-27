"""
Terminar una competición con un partido sin cerrar, por la API (I1, 22 nov 2026).

| Caso                                        | Respuesta                                     |
|---------------------------------------------|-----------------------------------------------|
| La Ryder en curso con su partido en juego   | 409 PENDING_GAMES (1 partido, 0 partidas)     |
| El mismo partido, concedido                 | 200 COMPLETED                                 |
"""

import pytest
from httpx import AsyncClient

from tests.conftest import set_auth_cookies
from tests.integration.api.v1.test_scoring_endpoints import setup_match_in_progress

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_a_match_in_play_stops_it_until_it_is_closed(client: AsyncClient):
    """
    Given la Ryder en curso con su único partido en juego
    When el organizador la termina, y después concede el partido y vuelve a terminarla
    Then primero 409 PENDING_GAMES con 1 partido y 0 partidas, y la competición sigue
        en curso; cerrado el partido, 200 COMPLETED
    """
    ctx = await setup_match_in_progress(client)
    set_auth_cookies(client, ctx["creator"]["cookies"])
    ruta = f"/api/v1/competitions/{ctx['competition_id']}/complete"

    con_pendiente = await client.post(ruta)

    assert con_pendiente.status_code == 409, con_pendiente.text
    assert con_pendiente.json() == {
        "detail": (
            "Finish or close what is still pending first: 1 Ryder match(es) and "
            "0 stroke play group(s)."
        ),
        "error_code": "PENDING_GAMES",
        "pending_matches": 1,
        "pending_groups": 0,
    }
    ficha = await client.get(f"/api/v1/competitions/{ctx['competition_id']}")
    assert ficha.json()["status"] == "IN_PROGRESS"

    concedido = await client.put(
        f"/api/v1/competitions/matches/{ctx['match_id']}/concede",
        json={"conceding_team": "A", "reason": "Se rinde"},
    )
    assert concedido.status_code == 200, concedido.text
    terminada = await client.post(ruta)

    assert terminada.status_code == 200, terminada.text
    assert terminada.json()["status"] == "COMPLETED"
