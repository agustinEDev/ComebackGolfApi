"""
El cableado del borrado de una partida rapida (26 nov 2026): olvidar lo que
publico va por la sesion de la PETICION, la misma que borra la partida. Con la
sesion propia de Actividad serian dos transacciones, y un fallo entre las dos
dejaria en el feed tarjetas de una partida que ya no existe.

Y el caso de uso de la papelera lleva ese adaptador: sin el no podria borrar.
"""

from types import SimpleNamespace

from src.config.dependencies import get_hide_quick_match_use_case, get_quick_match_activity


def test_forgetting_runs_on_the_request_session_and_handing_over_on_the_activity_one():
    de_la_peticion = object()
    historial = object()
    de_actividad = SimpleNamespace(history=historial, social=object())
    rapidas, torneos = object(), object()

    adaptador = get_quick_match_activity(
        social_uow=de_la_peticion,  # type: ignore[arg-type]
        uows=de_actividad,  # type: ignore[arg-type]
        round_achievements=rapidas,  # type: ignore[arg-type]
        tournament_achievements=torneos,  # type: ignore[arg-type]
    )

    assert adaptador._forget._social_uow is de_la_peticion  # type: ignore[attr-defined]
    assert adaptador._forget._social_uow is not de_actividad.social  # type: ignore[attr-defined]
    cesion = adaptador._hand_over  # type: ignore[attr-defined]
    assert (cesion._history, cesion._quick_matches, cesion._tournaments) == (
        historial,
        rapidas,
        torneos,
    )


def test_the_trash_use_case_carries_the_activity_adapter():
    actividad = object()

    caso = get_hide_quick_match_use_case(
        uow=object(),  # type: ignore[arg-type]
        user_uow=object(),  # type: ignore[arg-type]
        activity=actividad,  # type: ignore[arg-type]
    )

    assert caso._activity is actividad
