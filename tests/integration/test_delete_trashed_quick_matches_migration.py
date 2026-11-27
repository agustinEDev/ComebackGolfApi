"""
La migracion que borra las partidas rapidas que ya tenian en la papelera todos
sus jugadores (b2f6d8a4c1e7, 26 nov 2026). La regla esta escrita en SQL y en el
dominio: aqui se comprueba que dicen lo mismo.

  #   partida                                         | tras migrar
  ----|------------------------------------------------|------------------------
  G1  dos con cuenta, la tiraron los dos              | borrada
  G2  dos con cuenta, la tiro uno                     | sigue
  G3  uno con cuenta y un invitado, la tiro el        | borrada
  G4  nadie la tiro                                   | sigue
  G5  dos con cuenta, la tiro el activo; el otro      | borrada
      tiene la cuenta desactivada                     |
  G6  la tiro quien luego desactivo la cuenta; el     | sigue
      activo no                                       |
  G7  en juego, tirada por su unico jugador           | borrada (se permitia)
  G8  en juego, dos con cuenta, la tiro uno           | sigue, y SALE de su
                                                      | papelera: no podria
                                                      | abrirla ni anotar
  G9  terminada, la tiro uno de dos                   | sigue en su papelera
                                                      | (es G2): solo se
                                                      | vacian las vivas

Y con la borrada se van sus golpes, sus eventos de Actividad y sus apuntes; lo
de una partida que sigue, y un logro de torneo, se quedan. El «campo nuevo» de
la borrada deja su apunte —y el que ya tuviera se conserva—, como en la
aplicacion: si estaba oculto, es la unica constancia de que lo estaba, y lo que
hara llegar oculto ese logro a quien lo herede.
"""

import json
import uuid

from sqlalchemy import create_engine, text

from src.modules.golf_course.domain.value_objects.golf_course_id import GolfCourseId
from src.modules.quick_match.domain.entities.quick_match import QuickMatch
from src.modules.quick_match.domain.value_objects.participant_id import ParticipantId
from src.modules.quick_match.domain.value_objects.quick_match_id import QuickMatchId
from src.modules.quick_match.domain.value_objects.quick_match_participant import (
    QuickMatchParticipant,
)
from src.modules.user.domain.value_objects.user_id import UserId
from src.shared.domain.value_objects.scoring_format import ScoringFormat
from tests.integration.test_activity_events_published_at_migration import (
    _alembic,
    base_desechable,  # noqa: F401
)
from tests.integration.test_quick_match_started_at_migration import _campo

ANTERIOR = "a7e3c5d9b1f4"
BORRADO = "b2f6d8a4c1e7"


def _usuario(conn, *, activo: bool = True) -> str:
    user_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, first_name, last_name, email, is_active, created_at, "
            "updated_at) VALUES (:id, 'Ana', 'Garcia', :email, :activo, now(), now())"
        ),
        {"id": user_id, "email": f"{user_id}@example.com", "activo": activo},
    )
    return user_id


def _jugador(user_id: str | None) -> dict:
    """Como los guarda la aplicacion: con cuenta, su `participant_id` es el del usuario."""
    return {
        "participant_id": user_id or str(uuid.uuid4()),
        "user_id": user_id,
        "first_name": None if user_id else "Gon",
        "last_name": None if user_id else "Invitado",
    }


def _partida(conn, campo, jugadores, tiraron, estado="COMPLETED") -> str:
    match_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO quick_matches (id, creator_id, golf_course_id, scoring_format, status, "
            "participants, scorer_ids, hidden_by_participant_ids, "
            "stats_excluded_by_participant_ids, play_mode, created_at, updated_at) "
            "VALUES (:id, :u, :c, 'STABLEFORD', :s, CAST(:p AS jsonb), '[]', CAST(:h AS jsonb), "
            "'[]', 'HANDICAP', now(), now())"
        ),
        {
            "id": match_id,
            "u": jugadores[0],
            "c": campo,
            "s": estado,
            "p": json.dumps([_jugador(j) for j in jugadores]),
            "h": json.dumps(tiraron),
        },
    )
    conn.execute(
        text(
            "INSERT INTO quick_match_hole_scores (id, quick_match_id, hole_number, "
            "participant_id, score, recorded_by_participant_id, created_at, updated_at) "
            "VALUES (:id, :m, 1, :p, 4, :p, now(), now())"
        ),
        {"id": str(uuid.uuid4()), "m": match_id, "p": jugadores[0]},
    )
    return match_id


def _evento(
    conn, user_id: str, tipo: str, origen: str, payload: dict | None = None, visible: bool = True
) -> None:
    conn.execute(
        text(
            "INSERT INTO activity_events (id, user_id, type, occurred_at, source_match_id, "
            "payload, visible_to_friends) VALUES (:id, :u, :t, now(), :o, CAST(:p AS jsonb), :v)"
        ),
        {
            "id": str(uuid.uuid4()),
            "u": user_id,
            "t": tipo,
            "o": origen,
            "p": json.dumps(payload or {}),
            "v": visible,
        },
    )


def _apunte(conn, user_id: str, tipo: str, origen: str) -> None:
    conn.execute(
        text(
            "INSERT INTO withdrawn_hidden_achievements (user_id, source_match_id, type, "
            "withdrawn_at) VALUES (:u, :o, :t, now())"
        ),
        {"u": user_id, "o": origen, "t": tipo},
    )


def _segun_el_dominio(jugadores, tiraron, activos) -> bool:
    """Lo que diria `QuickMatch.is_trashed_by_everyone` de esa misma partida."""
    creador, *resto = jugadores
    partida = QuickMatch.create(
        id=QuickMatchId.generate(),
        creator_id=UserId(creador),
        golf_course_id=GolfCourseId(uuid.uuid4()),
        scoring_format=ScoringFormat.STABLEFORD,
    )
    for otro in resto:
        partida.add_participant(
            QuickMatchParticipant.for_user(UserId(otro))
            if otro
            else QuickMatchParticipant.for_guest("Gon", "Invitado")
        )
    partida.start([partida.creator_participant_id])
    partida.complete()
    for quien in tiraron:
        partida.hide_for(ParticipantId(uuid.UUID(quien)))
    return partida.is_trashed_by_everyone([ParticipantId(uuid.UUID(a)) for a in activos])


def test_only_the_matches_everyone_trashed_are_deleted(base_desechable):  # noqa: F811
    _alembic(base_desechable, "upgrade", ANTERIOR)
    engine = create_engine(base_desechable)
    with engine.begin() as conn:
        ana, bea = _usuario(conn), _usuario(conn)
        inactiva = _usuario(conn, activo=False)
        campo = conn.execute(text("SELECT id FROM golf_courses LIMIT 1")).scalar() or _campo(
            conn, ana
        )
        casos = {
            "G1": ([ana, bea], [ana, bea], "COMPLETED"),
            "G2": ([ana, bea], [ana], "COMPLETED"),
            "G3": ([ana, None], [ana], "COMPLETED"),
            "G4": ([ana, bea], [], "COMPLETED"),
            "G5": ([ana, inactiva], [ana], "COMPLETED"),
            "G6": ([ana, inactiva], [inactiva], "COMPLETED"),
            "G7": ([ana], [ana], "IN_PROGRESS"),
            "G8": ([ana, bea], [ana], "IN_PROGRESS"),
        }
        ids = {
            caso: _partida(conn, campo, jugadores, tiraron, estado)
            for caso, (jugadores, tiraron, estado) in casos.items()
        }
        for caso in ("G1", "G2"):
            _evento(conn, ana, "QUICK_MATCH_FINISHED", ids[caso])
            _evento(conn, bea, "BIRDIE", ids[caso])
            _apunte(conn, ana, "BIRDIE", ids[caso])
        _apunte(conn, ana, "NEW_COURSE", ids["G1"])
        # Un «campo nuevo» que su jugadora tenia OCULTO, y sin apunte previo: al
        # borrarse tiene que quedar constancia, o el de su siguiente vuelta alli
        # saldria a la vista (CodeRabbit, PR #939)
        _evento(conn, ana, "NEW_COURSE", ids["G3"], {"golf_course_id": "campo-x"}, visible=False)
        # Y uno a la vista: su apunte dice que NO estaba oculto
        _evento(conn, ana, "NEW_COURSE", ids["G5"], {"golf_course_id": "campo-y"})
        # Un logro de torneo que, por lo que sea, lleva el id de una borrada: no es suyo
        _evento(conn, ana, "NEW_COURSE", ids["G1"], {"from_tournament": True})
    engine.dispose()

    _alembic(base_desechable, "upgrade", BORRADO)

    engine = create_engine(base_desechable)
    with engine.connect() as conn:
        quedan = {r[0] for r in conn.execute(text("SELECT id::text FROM quick_matches"))}
        golpes = {
            r[0]
            for r in conn.execute(text("SELECT quick_match_id::text FROM quick_match_hole_scores"))
        }
        eventos = {
            (r[0], r[1])
            for r in conn.execute(text("SELECT source_match_id, type FROM activity_events"))
        }
        apuntes = {
            (r[0], r[1])
            for r in conn.execute(
                text("SELECT source_match_id, type FROM withdrawn_hidden_achievements")
            )
        }
        de_campo_nuevo = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                text(
                    "SELECT source_match_id, hidden, golf_course_id "
                    "FROM withdrawn_hidden_achievements WHERE type = 'NEW_COURSE'"
                )
            )
        }
        papeleras = {
            r[0]: json.loads(r[1])
            for r in conn.execute(
                text("SELECT id::text, hidden_by_participant_ids::text FROM quick_matches")
            )
        }
    engine.dispose()

    borradas = {caso for caso, match_id in ids.items() if match_id not in quedan}
    assert borradas == {"G1", "G3", "G5", "G7"}
    # Lo mismo que dice el dominio de cada una
    activos = [ana, bea]
    for caso, (jugadores, tiraron, estado) in casos.items():
        if estado != "COMPLETED":
            continue  # el dominio ya no deja tirar una partida viva
        assert _segun_el_dominio(jugadores, tiraron, activos) is (caso in borradas), caso
    # Con ellas, sus golpes
    assert golpes == {ids[c] for c in ("G2", "G4", "G6", "G8")}
    # Y lo que publicaron; lo de la que sigue y el logro de torneo, no
    assert eventos == {
        (ids["G2"], "QUICK_MATCH_FINISHED"),
        (ids["G2"], "BIRDIE"),
        (ids["G1"], "NEW_COURSE"),
    }
    # Los apuntes de la borrada tambien, salvo el de su «campo nuevo»
    assert apuntes == {
        (ids["G2"], "BIRDIE"),
        (ids["G1"], "NEW_COURSE"),
        (ids["G3"], "NEW_COURSE"),
        (ids["G5"], "NEW_COURSE"),
    }
    # El que estaba oculto deja dicho que lo estaba, y en que campo; el que no, que no
    assert de_campo_nuevo[ids["G3"]] == (True, "campo-x")
    assert de_campo_nuevo[ids["G5"]] == (False, "campo-y")
    # G8: la viva que sigue sale de la papelera de quien la tiro. Las acabadas, no
    assert papeleras[ids["G8"]] == []
    assert papeleras[ids["G2"]] == [ana]
    assert papeleras[ids["G6"]] == [inactiva]


def test_going_down_does_not_fail(base_desechable):  # noqa: F811
    _alembic(base_desechable, "upgrade", BORRADO)

    _alembic(base_desechable, "downgrade", ANTERIOR)
