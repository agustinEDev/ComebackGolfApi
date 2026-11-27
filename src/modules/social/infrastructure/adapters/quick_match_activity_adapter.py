"""Adaptador: lo que una partida rapida borrada deja de tener en Actividad."""

import logging
from collections.abc import Sequence

from src.modules.quick_match.application.ports.quick_match_activity_interface import (
    ForgottenActivity,
    QuickMatchActivityInterface,
)
from src.modules.social.application.use_cases.forget_quick_match_activity_use_case import (
    ForgetQuickMatchActivityUseCase,
)
from src.modules.social.application.use_cases.hand_over_new_course_use_case import (
    HandOverNewCourseUseCase,
)
from src.modules.user.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


class QuickMatchActivityAdapter(QuickMatchActivityInterface):
    """
    Une los dos modulos sin que ninguno importe al otro: `quick_match` conoce
    solo su puerto, y `social` sus dos casos de uso.

    Los dos pasos van por sesiones distintas, y no es un detalle: olvidar va por
    la sesion de la PETICION, la misma que borra la partida, y por eso deja
    pasar sus fallos; ceder el «campo nuevo» va por la sesion propia de
    Actividad, con el borrado ya guardado, y aqui se le quita cualquier fallo.
    """

    def __init__(
        self,
        forget_use_case: ForgetQuickMatchActivityUseCase,
        hand_over_use_case: HandOverNewCourseUseCase,
    ):
        self._forget = forget_use_case
        self._hand_over = hand_over_use_case

    async def forget(self, quick_match_id: str, player_ids: Sequence[UserId]) -> ForgottenActivity:
        borrados, con_campo_nuevo = await self._forget.execute(quick_match_id, player_ids)
        return ForgottenActivity(events=borrados, new_course_holders=tuple(con_campo_nuevo))

    async def hand_over_new_course(self, golf_course_id: str, player_ids: Sequence[UserId]) -> None:
        try:
            await self._hand_over.execute(golf_course_id, player_ids)
        except Exception:
            logger.warning(
                "Could not hand over the new course %s after deleting a quick match",
                golf_course_id,
                exc_info=True,
            )
