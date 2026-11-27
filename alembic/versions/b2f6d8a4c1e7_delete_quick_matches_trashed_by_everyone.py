"""delete quick matches already trashed by everyone

Desde esta version, una partida rapida se borra de verdad cuando la han tirado
a la papelera todos los participantes que siguen teniendo la cuenta activa
(`QuickMatch.is_trashed_by_everyone`, 26 nov 2026). Hasta ahora la papelera solo
la ocultaba, y hay partidas que ya tenian tirada todos sus jugadores: nadie las
ve ni puede volver a tirarlas, asi que nada dispararia su borrado. Esta pasada
unica las borra, con lo que publicaron en Actividad.

Tambien las que se tiraron estando en juego o sin empezar, que hasta hoy se
permitia (decidido por Agustin con el recuento de produccion delante: 36
partidas, 96 golpes y 1 evento; ningun «campo nuevo», ninguna por una cuenta
desactivada).

Y a las partidas VIVAS que sobreviven —alguien la tiro, pero no todos— les
quita la marca de la papelera. Desde ahora no se puede tirar una partida viva,
quien la tiro ya no la encuentra, y no hay como sacarla: sin esto, ese jugador
se quedaria sin poder abrir ni anotar una partida que sigue en juego. Cuando
acabe podra tirarla, si quiere. En produccion no hay ninguna.

El borrado va en UNA sola sentencia: las tres tablas se deciden con la misma
foto. En tres sentencias, cada una veria la suya, y con la version anterior
todavia sirviendo durante el despliegue una papelera pulsada entre medias
dejaria eventos huerfanos o una partida sin los suyos.

La regla esta escrita DOS veces, aqui en SQL y en el dominio. En una migracion
es inevitable: solo cabe SQL plano, porque el CI las genera en modo offline. El
test `tests/integration/test_delete_trashed_quick_matches_migration.py` las
compara.

Lo que NO hace: ceder el «campo nuevo» de una partida borrada a la siguiente
vuelta del jugador en ese campo, que es lo que hace la aplicacion al borrar. Ese
calculo no cabe en SQL plano. En produccion no hay ninguno que ceder.

Lo que SI hace con ese logro es lo que hace la aplicacion al borrarlo
(`forget_source`): dejar su apunte. Si el jugador lo tenia oculto, el apunte es
la unica constancia de esa eleccion; sin el, el «campo nuevo» de su siguiente
vuelta en ese campo saldria a la vista de sus amigos. El apunte que ya hubiera
se conserva, sumandole lo oculto.

Revision ID: b2f6d8a4c1e7
Revises: a7e3c5d9b1f4
Create Date: 2026-11-26

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2f6d8a4c1e7"
down_revision = "a7e3c5d9b1f4"
branch_labels = None
depends_on = None

# «La han tirado todos los que siguen pudiendo»: alguien la tiro, y esta en la
# papelera de cada participante con cuenta ACTIVA. Un invitado no tiene
# `user_id`; quien perdio o desactivo la cuenta no la retiene. Es
# `QuickMatch.is_trashed_by_everyone`.
#
# Los tipos son los que salen de una partida rapida
# (`ActivityEventType.may_come_from_a_quick_match`). Los exclusivos por fecha
# («campo nuevo», «primer torneo») dejan apunte al borrarse, y sus apuntes no se
# purgan, como en la aplicacion (`forget_source`): `WithdrawnAchievement.of` y
# `merged_with`, en SQL.
#
# SQL literal, sin montarlo con cadenas: se lee y se revisa de un vistazo.


def upgrade() -> None:
    # 1. Las partidas (sus golpes caen con ellas, ON DELETE CASCADE), y con la
    #    misma foto lo que publicaron en Actividad y sus apuntes, que no tienen
    #    clave ajena que se los lleve
    op.execute(
        """
        WITH borradas AS (
            DELETE FROM quick_matches qm
            WHERE jsonb_array_length(qm.hidden_by_participant_ids) > 0
              AND qm.hidden_by_participant_ids @> COALESCE(
                  (
                      SELECT jsonb_agg(p->>'user_id')
                      FROM jsonb_array_elements(qm.participants) AS p
                      JOIN users u ON u.id::text = p->>'user_id'
                      WHERE u.is_active
                  ),
                  '[]'::jsonb
              )
            RETURNING qm.id::text AS id
        ),
        eventos AS (
            DELETE FROM activity_events e
            USING borradas b
            WHERE e.source_match_id = b.id
              AND e.type IN (
                  'BIRDIE', 'EAGLE_OR_BETTER', 'FIRST_TOURNAMENT', 'HOLE_IN_ONE',
                  'NEW_COURSE', 'PERSONAL_BEST', 'QUICK_MATCH_FINISHED'
              )
              AND e.payload->>'from_tournament' IS DISTINCT FROM 'true'
            RETURNING e.user_id, e.source_match_id, e.type, e.published_at,
                      e.visible_to_friends, e.payload
        ),
        exclusivos AS (
            INSERT INTO withdrawn_hidden_achievements (
                user_id, source_match_id, type, published_at, hidden, hidden_holes,
                golf_course_id
            )
            SELECT ev.user_id, ev.source_match_id, ev.type, ev.published_at,
                   NOT ev.visible_to_friends, NULL::jsonb,
                   CASE WHEN ev.type = 'NEW_COURSE'
                        THEN ev.payload->>'golf_course_id' END
            FROM eventos ev
            WHERE ev.type IN ('NEW_COURSE', 'FIRST_TOURNAMENT')
            ON CONFLICT (user_id, source_match_id, type) DO UPDATE SET
                published_at = LEAST(
                    withdrawn_hidden_achievements.published_at, EXCLUDED.published_at
                ),
                hidden = withdrawn_hidden_achievements.hidden OR EXCLUDED.hidden,
                golf_course_id = COALESCE(
                    EXCLUDED.golf_course_id, withdrawn_hidden_achievements.golf_course_id
                )
            RETURNING 1
        ),
        apuntes AS (
            DELETE FROM withdrawn_hidden_achievements w
            USING borradas b
            WHERE w.source_match_id = b.id
              AND w.type IN (
                  'BIRDIE', 'EAGLE_OR_BETTER', 'HOLE_IN_ONE', 'PERSONAL_BEST',
                  'QUICK_MATCH_FINISHED'
              )
            RETURNING 1
        )
        SELECT
            (SELECT count(*) FROM borradas) AS partidas,
            (SELECT count(*) FROM eventos) AS eventos,
            (SELECT count(*) FROM exclusivos) AS exclusivos_apuntados,
            (SELECT count(*) FROM apuntes) AS apuntes
        """
    )
    # 2. Las vivas que quedan salen de la papelera de quien las tiro: ya no se
    #    puede tirar una partida viva, y nadie podria devolversela
    op.execute(
        """
        UPDATE quick_matches
        SET hidden_by_participant_ids = '[]'::jsonb
        WHERE status IN ('PENDING', 'IN_PROGRESS')
          AND jsonb_array_length(hidden_by_participant_ids) > 0
        """
    )


def downgrade() -> None:
    # No hay vuelta: lo borrado no se puede reconstruir, ni se sabe quien tenia
    # tirada cada partida viva. Se deja vacio a proposito, para que bajar de
    # version no falle; quien lo necesite lo tiene en la copia de seguridad
    # anterior al despliegue.
    pass
