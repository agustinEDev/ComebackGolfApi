"""
`EstadoPartida.acabada()` (revisión del 22 nov 2026): una sola regla de «partida
acabada» para terminar la competición y para cerrar la franja.
"""

import pytest

from src.modules.competition.domain.value_objects.estado_partida import EstadoPartida


@pytest.mark.parametrize(
    ("estado", "acabada"),
    [
        (EstadoPartida.SCHEDULED, False),
        (EstadoPartida.IN_PROGRESS, False),
        (EstadoPartida.COMPLETED, True),
    ],
)
def test_acabada_only_when_completed(estado, acabada):
    """
    Given una partida en cada uno de sus estados
    When se pregunta si está acabada
    Then solo COMPLETED lo está
    """
    assert estado.acabada() is acabada
