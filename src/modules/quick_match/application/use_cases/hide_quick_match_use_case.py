"""Caso de Uso: tirar una partida rapida a la papelera, y borrarla si ya la tiraron todos."""

from src.modules.quick_match.application.dto.quick_match_dto import (
    HideQuickMatchRequestDTO,
    HideQuickMatchResponseDTO,
)
from src.modules.quick_match.application.exceptions import QuickMatchNotFoundError
from src.modules.quick_match.application.mappers.quick_match_mapper import QuickMatchDTOMapper
from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    QuickMatchActivityInterface,
)
from src.modules.quick_match.application.services.trashed_quick_match_remover import (
    TrashedQuickMatchRemover,
)
from src.modules.quick_match.domain.exceptions.quick_match_violations import (
    NotQuickMatchParticipantViolation,
)
from src.modules.quick_match.domain.repositories.quick_match_unit_of_work_interface import (
    QuickMatchUnitOfWorkInterface,
)
from src.modules.quick_match.domain.value_objects.participant_id import ParticipantId
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.user.domain.repositories.user_unit_of_work_interface import (
    UserUnitOfWorkInterface,
)
from src.modules.user.domain.value_objects.user_id import UserId


class HideQuickMatchUseCase:
    """
    Tira una partida rapida a la papelera de quien lo pide, y la borra de
    verdad cuando ya la han tirado todos (26 nov 2026).

    La papelera es personal: cualquier participante (no solo el creador) puede
    tirarla para si, y solo afecta a su vista. Pero cuando la han tirado todos
    los que siguen teniendo la cuenta activa (`QuickMatch.is_trashed_by_everyone`),
    ya no la ve nadie: se borra con sus golpes y con lo que publico en
    Actividad, en una sola transaccion.
    """

    def __init__(
        self,
        uow: QuickMatchUnitOfWorkInterface,
        user_uow: UserUnitOfWorkInterface,
        activity: QuickMatchActivityInterface,
    ):
        self._uow = uow
        self._user_uow = user_uow
        # Obligatorio: sin el, un borrado dejaria en Actividad eventos de una
        # partida que ya no existe, y nadie se enteraria
        self._activity = activity
        self._remover = TrashedQuickMatchRemover(uow, user_uow, activity)

    async def execute(self, request: HideQuickMatchRequestDTO) -> HideQuickMatchResponseDTO:
        requester_id = UserId(request.requester_id)
        requester_participant_id = ParticipantId(requester_id.value)

        async with self._uow:
            quick_match = await self._uow.quick_matches.find_by_id_for_update(
                QuickMatchId(request.quick_match_id)
            )
            if not quick_match:
                raise QuickMatchNotFoundError(f"Quick match not found: {request.quick_match_id}")

            try:
                quick_match.hide_for(requester_participant_id)
            except NotQuickMatchParticipantViolation:
                # A quien no es de la partida, lo mismo que si no existiera: con
                # otro mensaje sabria que ese id es de una partida de verdad
                raise QuickMatchNotFoundError(
                    f"Quick match not found: {request.quick_match_id}"
                ) from None

            usuarios = await self._remover.players_of(quick_match)
            # La respuesta se monta ANTES de borrar, con los usuarios ya
            # cargados: despues no hay partida de la que leer
            foto = await QuickMatchDTOMapper.to_response_dto(
                quick_match, self._user_uow, usuarios, requester_id=requester_id
            )

            borrada = await self._remover.remove_if_trashed_by_everyone(quick_match, usuarios)
            if borrada is None:
                await self._uow.quick_matches.update(quick_match)

        if borrada is None:
            return HideQuickMatchResponseDTO(**foto.model_dump())

        await self._remover.after_commit(
            borrada, triggered_by=f"the last one being {requester_id.value}"
        )
        return HideQuickMatchResponseDTO(**foto.model_dump(), deleted=True)
