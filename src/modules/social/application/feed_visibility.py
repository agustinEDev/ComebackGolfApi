"""
Lo que una pagina de actividad ya no debe enseñar aunque siga guardado.

Vive aparte porque lo comparten el feed y la actividad de un perfil: las dos
pintan las mismas tarjetas, y la que se quedara atras enseñaria lo que no debe.
"""

from collections.abc import Sequence

from src.modules.social.application.ports.invitation_availability_interface import (
    InvitationAvailabilityInterface,
)
from src.modules.social.application.ports.quick_match_trash_interface import (
    QuickMatchTrashInterface,
)
from src.modules.social.application.ports.tournament_visibility_interface import (
    TournamentVisibilityInterface,
)
from src.modules.social.domain.entities.activity_event import ActivityEvent
from src.modules.social.domain.value_objects.activity_event_type import ActivityEventType
from src.modules.user.domain.value_objects.user_id import UserId

_APUNTADO = ActivityEventType.ENROLLED_IN_TOURNAMENT
# «Te han invitado» y «ya puedes aceptar» (P2, 15 nov 2026): los dos piden aceptarla
_DE_INVITACION = frozenset(
    {ActivityEventType.INVITED_TO_TOURNAMENT, ActivityEventType.INVITATION_ACCEPTABLE_AGAIN}
)


async def sin_apuntados_a_privados(
    eventos: Sequence[ActivityEvent], tournaments: TournamentVisibilityInterface | None
) -> list[ActivityEvent]:
    """
    La pagina sin los «X se ha apuntado» de torneos que ahora son privados
    (tabla del 22 oct 2026, E).

    Al pasar a privado se borran, pero ese borrado puede fallar sin tumbar la
    accion; esto es la red. Se pregunta por todos los torneos de la pagina de
    una vez. Quien llama calcula el cursor ANTES de filtrar: la pagina puede
    quedar corta, pero el cursor sigue tras la ultima fila leida, asi que no se
    pierde ni se repite nada. Si el torneo vuelve a ser publico, lo que ya se
    borro no reaparece.
    """
    if tournaments is None:
        return list(eventos)
    ids = {
        competition_id
        for evento in eventos
        if evento.type == _APUNTADO
        and isinstance(competition_id := evento.payload.get("competition_id"), str)
    }
    if not ids:
        return list(eventos)
    privados = await tournaments.private_ids(sorted(ids))
    return [
        evento
        for evento in eventos
        if not (evento.type == _APUNTADO and evento.payload.get("competition_id") in privados)
    ]


async def sin_invitaciones_cerradas(
    eventos: Sequence[ActivityEvent], invitations: InvitationAvailabilityInterface | None
) -> list[ActivityEvent]:
    """
    La pagina sin los «Te han invitado» (ni los «ya puedes aceptar») de
    invitaciones que ya no se pueden aceptar (revision final, 22 oct 2026).

    Una invitacion caduca sola sin que nadie la guarde como EXPIRED ni retire
    su aviso. El origen del aviso es el id de la invitacion, asi que se pregunta
    por todas las de la pagina de una vez. Como con los torneos privados, quien
    llama calcula el cursor ANTES de filtrar.
    """
    if invitations is None:
        return list(eventos)
    ids = {evento.source_match_id for evento in eventos if evento.type in _DE_INVITACION}
    if not ids:
        return list(eventos)
    cerradas = await invitations.closed_ids(sorted(ids))
    return [
        evento
        for evento in eventos
        if not (evento.type in _DE_INVITACION and evento.source_match_id in cerradas)
    ]


async def sin_partidas_en_la_papelera(
    eventos: Sequence[ActivityEvent],
    trash: QuickMatchTrashInterface | None,
    viewer_id: UserId,
) -> list[ActivityEvent]:
    """
    La pagina sin lo que salio de partidas rapidas tiradas a la papelera: el
    «como acabo» y sus logros (prueba de punta a punta, 22 oct 2026).

    No sale lo de una partida que SU AUTOR tiene en la papelera, a nadie: ni a
    sus amigos ni a el mismo. Y no sale nada de una partida que tiene en la
    papelera QUIEN MIRA, tampoco lo de otro jugador que no la haya tirado: para
    quien la tiro, esa partida ha desaparecido (26 nov 2026; antes el autor
    seguia viendo lo suyo). La papelera es definitiva: no hay como sacarla.

    A un amigo que no la jugo, lo de un jugador que no la ha tirado le sigue
    saliendo. Se pregunta por toda la pagina de una vez y, como con los torneos
    privados, quien llama calcula el cursor ANTES de filtrar.
    """
    if trash is None:
        return list(eventos)
    de_partida = [evento for evento in eventos if evento.comes_from_a_quick_match]
    if not de_partida:
        return list(eventos)
    parejas = {(evento.source_match_id, evento.user_id) for evento in de_partida}
    # Y cada una de esas partidas, por si la tiro quien mira
    parejas |= {(evento.source_match_id, viewer_id) for evento in de_partida}
    en_la_papelera = await trash.trashed_by_author(sorted(parejas, key=_orden))
    return [
        evento
        for evento in eventos
        if not (
            evento.comes_from_a_quick_match
            and (
                (evento.source_match_id, evento.user_id) in en_la_papelera
                or (evento.source_match_id, viewer_id) in en_la_papelera
            )
        )
    ]


def _orden(pareja: tuple[str, UserId]) -> tuple[str, str]:
    return pareja[0], str(pareja[1].value)
