"""
Caso de Uso: Completar Competition.

Permite completar/finalizar una competicion (IN_PROGRESS -> COMPLETED).
Solo el creador puede realizar esta accion.

Decidido con Agustín (I1, 22 nov 2026): no se termina con algo sin cerrar. Si
queda un partido de la Ryder sin acabar (SCHEDULED o IN_PROGRESS) o una partida
de stroke play sin acabar (`EstadoPartida.acabada`), 409 PENDING_GAMES con
cuántos de cada. No se toca ningún partido, partida ni ronda.

Quién se comprueba sin bloquear (como BE #309); después, con la competición
bloqueada y releída, el estado y lo pendiente.

Qué garantiza: al terminar no queda nada sin acabar. Lo pendiente se lee con la
competición bloqueada, y lo único que devuelve algo acabado a sin acabar es
reabrir una tarjeta de stroke play (`Partida.reabrir_tarjeta`), que bloquea la
competición antes que la partida y relee su estado: o va antes y esto la ve
pendiente, o va después y ve la competición terminada. Lo que crea partidos o
partidas (generarlos, repartir la franja) también bloquea antes la competición.
Un partido de la Ryder acabado no vuelve a estar en juego, y lo demás, aunque
bloquee solo la partida (anotar, corregir, borrar o validar hoyos, entregar,
retirarse o retirar a alguien), no reabre nada: como mucho la acaba o la pone en
juego, que no cambia que esté pendiente.
"""

import logging

from src.modules.competition.application.dto.competition_dto import (
    CompleteCompetitionRequestDTO,
    CompleteCompetitionResponseDTO,
)
from src.modules.competition.application.exceptions import (
    CompetitionNotFoundError,
    NotCompetitionCreatorError,
    PendingGamesError,
)
from src.modules.competition.application.ports.competition_activity_publisher_interface import (
    CompetitionActivityPublisherInterface,
)
from src.modules.competition.application.ports.tournament_achievements_publisher_interface import (
    TournamentAchievementsPublisherInterface,
)
from src.modules.competition.application.services.avisos_de_actividad import AvisosDeActividad
from src.modules.competition.domain.repositories.competition_unit_of_work_interface import (
    CompetitionUnitOfWorkInterface,
)
from src.modules.competition.domain.value_objects.competition_id import CompetitionId
from src.modules.competition.domain.value_objects.competition_status import CompetitionStatus
from src.modules.user.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


class CompleteCompetitionUseCase:
    """
    Caso de uso para completar/finalizar una competicion.

    Transicion: IN_PROGRESS -> COMPLETED
    Efecto: El torneo ha terminado, estado final

    Restricciones:
    - Solo se puede completar desde estado IN_PROGRESS
    - Solo el creador puede completar
    - La competicion debe existir

    Orquesta:
    1. Buscar la competicion por ID
    2. Verificar que el usuario sea el creador
    3. Completar la competicion (delega validacion de estado a la entidad)
    4. Persistir cambios
    5. Commit de la transaccion
    """

    def __init__(
        self,
        uow: CompetitionUnitOfWorkInterface,
        achievements: TournamentAchievementsPublisherInterface | None = None,
        actividad: CompetitionActivityPublisherInterface | None = None,
    ):
        """
        Constructor.

        Args:
            uow: Unit of Work para gestionar transacciones
            achievements: Publicador del feed de logros (BE #175). Opcional:
                sin el, cerrar el torneo sigue funcionando y no se publica nada.
            actividad: Los avisos de Actividad (BE-2): la clasificacion final
                de cada uno. Sin el, no se avisa
        """
        self._uow = uow
        self._achievements = achievements
        self._actividad = AvisosDeActividad(actividad)

    async def execute(
        self, request: CompleteCompetitionRequestDTO, user_id: UserId, is_admin: bool = False
    ) -> CompleteCompetitionResponseDTO:
        """
        Ejecuta el caso de uso de completar competicion.

        Args:
            request: DTO con el ID de la competicion a completar
            user_id: ID del usuario que solicita completar

        Returns:
            DTO con datos de la competicion completada

        Raises:
            CompetitionNotFoundError: Si la competicion no existe
            NotCompetitionCreatorError: Si el usuario no es el creador
            CompetitionStateError: Si la transicion de estado no es valida
            PendingGamesError: Si queda un partido o una partida sin terminar
        """
        async with self._uow:
            # 1. Buscar la competicion
            competition_id = CompetitionId(request.competition_id)
            # Primero SIN bloqueo, para autorizar: quien no puede no retiene la
            # fila (como BE #309)
            competition = await self._uow.competitions.find_by_id(competition_id)

            if not competition:
                raise CompetitionNotFoundError(
                    f"No existe competición con ID {request.competition_id}"
                )

            # 2. Verificar que el usuario sea el creador (o admin)
            if not is_admin and not competition.is_creator(user_id):
                raise NotCompetitionCreatorError("Solo el creador puede completar la competicion")

            # Luego bloqueada, y el estado y lo pendiente se deciden sobre lo
            # releído (I1, 22 nov 2026): reabrir una tarjeta y cerrar la franja
            # bloquean también la competición antes que sus partidas
            competition = await self._uow.competitions.find_by_id_for_update(competition_id)
            if not competition:
                raise CompetitionNotFoundError(
                    f"No existe competición con ID {request.competition_id}"
                )

            # 3. Completar la competicion (la entidad valida la transicion)
            # 3a. Sin nada sin cerrar (I1), antes de tocar la competición; pero
            # tras el estado: a una que no se puede terminar se le dice eso
            if competition.status.can_transition_to(CompetitionStatus.COMPLETED):
                await self._exigir_que_no_quede_nada(competition_id)
            competition.complete()

            # 4. Persistir cambios
            await self._uow.competitions.update(competition)

        # 5. Publicar los logros del torneo en el feed de los amigos. El puerto
        # pide el id como texto: es el que va al `payload` y al candado
        await self._publicar_logros(str(competition_id.value))

        # 5b. Y la clasificacion final de cada inscrito (BE-2)
        await self._actividad.completed(competition)

        # 6. Retornar DTO de respuesta
        return CompleteCompetitionResponseDTO(
            id=competition.id.value,
            status=competition.status.value,
            completed_at=competition.updated_at,
        )

    async def _exigir_que_no_quede_nada(self, competition_id: CompetitionId) -> None:
        """
        Ningún partido de la Ryder sin acabar (`is_finished`: completado, WO o
        concedido) ni partida de stroke play sin acabar (COMPLETED).

        Raises:
            PendingGamesError: Con cuántos partidos y partidas quedan
        """
        # De una vez para todas las rondas: esto corre con la competición bloqueada
        rondas = [r.id for r in await self._uow.rounds.find_by_competition(competition_id)]
        partidos = sum(
            1
            for partido in await self._uow.matches.find_by_rounds(rondas)
            if not partido.is_finished()
        )
        partidas = sum(
            1
            for partida in await self._uow.partidas.de_la_competicion(competition_id)
            if not partida.estado.acabada()
        )
        if partidos or partidas:
            raise PendingGamesError(partidos, partidas)

    async def _publicar_logros(self, competition_id_raw: str) -> None:
        """
        Publica los logros del torneo sin dejar que un fallo tumbe el cierre.

        El torneo ya esta cerrado y guardado cuando esto corre. El feed es
        accesorio y el resultado del torneo no.
        """
        if self._achievements is None:
            return

        try:
            await self._achievements.publish(competition_id_raw)
        except Exception:
            logger.warning(
                "Could not publish achievements for competition %s",
                competition_id_raw,
                exc_info=True,
            )
