"""
Tests de los correos que manda la aplicación (BE #389).

Todos comparten una plantilla con la imagen de la app. Se comprueba lo
que llega a Mailgun —asunto, texto plano y HTML— sustituyendo el envío, sin
red: el enlace de cada botón, que nada del usuario entra sin escapar y que el
HTML no depende de un <style> que Gmail borra.
"""

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import AsyncMock

import pytest

from src.config.settings import settings
from src.shared.domain.services.instante_utc import ahora_en_utc
from src.shared.infrastructure.email.email_service import EmailService

WEB = "https://www.antiguo.example"
MOTIVO_DE_EJEMPLO = "aviso"


@pytest.fixture
def correo(monkeypatch):
    """El servicio con el envío sustituido: guarda lo que se mandaría."""
    monkeypatch.setattr(settings, "FRONTEND_URL", WEB)
    servicio = EmailService()
    servicio._send_email = AsyncMock(return_value=True)
    return servicio


def _enviado(servicio):
    """(destinatario, asunto, texto, html) del único envío."""
    servicio._send_email.assert_called_once()
    args, kwargs = servicio._send_email.call_args
    valores = list(args) + [kwargs[k] for k in ("to", "subject", "text", "html") if k in kwargs]
    return tuple(valores)


def _botones(html_body):
    """Los enlaces de los botones, en orden."""
    return re.findall(r'<a [^>]*data-boton[^>]*href="([^"]+)"', html_body)


async def _todos_los_correos(servicio, guarda=None):
    """
    Manda cada correo de la app (la invitación, con y sin cuenta) y devuelve su HTML.

    Con `guarda`, apunta además en esa lista lo enviado de cada uno: destinatario,
    asunto, texto plano y HTML.
    """
    htmls = {}
    if guarda is not None:

        async def _apunta(*args, **kwargs):
            guarda.append(tuple(v for v in [*args, *kwargs.values()] if isinstance(v, str)))
            return True

        servicio._send_email.side_effect = _apunta

    await servicio.send_verification_email("a@b.com", "Ana", "tok123")
    htmls["verificacion"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    await servicio.send_password_reset_email("a@b.com", f"{WEB}/reset-password/tok", "Ana")
    htmls["restablecer"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    await servicio.send_password_changed_notification("a@b.com", "Ana")
    htmls["cambiada"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    await servicio.send_invitation_email(
        "a@b.com", "Ana", "Pablo", "Copa", None, ahora_en_utc() + timedelta(days=7)
    )
    htmls["invitacion"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    # Sin cuenta y con mensaje: el botón secundario de registrarse y la cita
    await servicio.send_invitation_email(
        "a@b.com", None, "Pablo", "Copa", "¡Vente!", ahora_en_utc() + timedelta(days=7)
    )
    htmls["invitacion_sin_cuenta"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    await servicio.send_friend_request_email("a@b.com", "Ana", "Pablo")
    htmls["amistad"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    # El sexto, desde el 7 oct 2026 (#251): el nombre de la función se quedó
    await servicio.send_handicaps_pending_email("a@b.com", "Ana", "Copa", "c-1", ["Luis"])
    htmls["handicaps"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    # Al jugador al que la RFEG no encontró (H3, 15 nov 2026)
    await servicio.send_handicap_not_found_email("a@b.com", "Ana", "Copa")
    htmls["rfeg_no_encontrado"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    await servicio.send_scheduled_handicaps_update_skipped_email(
        "a@b.com", "Ana", "Copa", "c-1", "Hay una jornada en marcha."
    )
    htmls["programada"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    # El de la sesión cerrada por seguridad (F-02, caso A4)
    await servicio.send_session_closed_for_security_notice(
        "a@b.com", "Ana", "iPhone · Safari", "10 nov 2026, 12:30 (hora de España)", "España"
    )
    htmls["sesion_cerrada"] = _enviado(servicio)[3]
    servicio._send_email.reset_mock()

    otros = {
        "confirmar_cambio": servicio.send_email_change_confirmation("n@b.com", "Ana", "tok"),
        "cambio_pedido": servicio.send_email_change_requested_notice("a@b.com", "Ana", "n@b.com"),
        "google": servicio.send_google_account_notice("a@b.com", "Ana", True),
        "intento_de_registro": servicio.send_register_attempt_notice("a@b.com", "Ana"),
        "cuenta_asegurada": servicio.send_account_secured_notice("a@b.com", "Ana", "google"),
        "correo_cambiado": servicio.send_email_changed_notice("a@b.com", "Ana", "n@b.com"),
        "nuevo_inicio": servicio.send_new_login_notification(
            "a@b.com", "Ana", "Safari en iPhone", "6 nov 2026, 10:30", "España"
        ),
        "intentos_fallidos": servicio.send_failed_logins_notification(
            to_email="a@b.com",
            user_name="Ana",
            motivo=MOTIVO_DE_EJEMPLO,
            cuando="6 nov 2026, 10:30",
            pais="España",
            fallos=5,
            minutos=30,
        ),
    }
    for nombre, envio in otros.items():
        await envio
        htmls[nombre] = _enviado(servicio)[3]
        servicio._send_email.reset_mock()
    return htmls


class TestEveryEmailWearsTheAppsBranding:
    """Una sola plantilla con la cara de la app para todos."""

    @pytest.mark.asyncio
    async def test_all_open_with_the_brand_header_image(self, correo):
        # D1: la cabecera es una imagen del front sobre una celda salvia; si el
        # programa de correo no la carga, en su sitio se lee el nombre
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            celdas = [n for n in _nodos(cuerpo, "td") if "data-cabecera" in n.attrs]
            assert len(celdas) == 1, nombre
            celda = celdas[0]
            assert celda.attrs.get("bgcolor") == _fondo(celda) == SALVIA, nombre
            assert f"color:{BOSQUE_PROFUNDO};" in celda.estilo, nombre
            clara, envoltorio = celda.hijos
            base = f"{WEB}/images/correo/cabecera-{DIBUJOS[nombre]}"
            assert clara.etiqueta == "img", nombre
            assert clara.attrs["alt"] == "Comeback Golf", nombre
            assert clara.attrs["src"] == f"{base}.png", nombre
            assert clara.attrs["class"] == "o-claro", nombre
            assert "display:block;" in clara.estilo, nombre
            assert "width:100%;" in clara.estilo and "height:auto;" in clara.estilo, nombre
            # La oscura va oculta EN LÍNEA: quien no entienda el <style> (Gmail) no la
            # pinta, y Outlook de escritorio, que ignora display:none, tiene mso-hide
            assert envoltorio.etiqueta == "div", nombre
            assert envoltorio.attrs["class"] == "o-oscuro", nombre
            for regla in ("display:none;", "max-height:0;", "overflow:hidden;", "mso-hide:all;"):
                assert regla in envoltorio.estilo, (nombre, regla)
            (oscura,) = envoltorio.hijos
            assert oscura.attrs["src"] == f"{base}-oscuro.png", nombre
            assert oscura.attrs["alt"] == "Comeback Golf", nombre
            # Y fuera de Outlook: el comentario condicional la envuelve entera
            assert re.search(
                r'<!--\[if !mso\]><!--><div class="o-oscuro"[^>]*><img [^>]*></div>'
                r"<!--<!\[endif\]-->",
                cuerpo,
            ), nombre
            assert cuerpo.count("<!--[if") == 1, nombre
            # Son las únicas imágenes: nada más depende de que se carguen
            assert len(_nodos(cuerpo, "img")) == 2, nombre

    @pytest.mark.asyncio
    async def test_the_drawings_cover_every_email(self, correo):
        # D2: el reparto aprobado el 25 nov 2026, correo a correo
        assert set(DIBUJOS) == set(await _todos_los_correos(correo))

    @pytest.mark.asyncio
    async def test_the_old_name_is_gone_from_subject_text_and_html(self, correo):
        # D3: ni en el asunto ni en el texto plano ni en el HTML
        await _todos_los_correos(correo, guarda=(envios := []))
        assert len(envios) >= len(DIBUJOS)
        for envio in envios:
            for parte in envio:
                # Con sus mayúsculas: en minúsculas es el dominio de los enlaces
                assert not re.search(r"Ryder ?Cup ?Friends|\bRCF\b", parte), parte[:120]

    @pytest.mark.asyncio
    async def test_no_email_depends_on_its_style_block(self, correo):
        # Gmail no aplica el oscuro y otros clientes borran los <style>: el correo en
        # claro va entero en línea. El único <style> solo añade el oscuro: todo lo que
        # dice va dentro de `prefers-color-scheme: dark` o no cambia ningún color
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            assert cuerpo.count("<style") == 1, nombre
            estilo = re.search(r"<style>(.*?)</style>", cuerpo, re.S).group(1)
            fuera, dentro = estilo.split("@media (prefers-color-scheme:dark){", 1)
            assert fuera == (
                ":root{color-scheme:light dark;}"
                "a[x-apple-data-detectors]{color:inherit!important;"
                "text-decoration:none!important;}"
            ), nombre
            assert dentro.endswith("}"), nombre

    @pytest.mark.asyncio
    async def test_the_dark_rules_say_exactly_this(self, correo):
        # El oscuro entero, regla a regla: una que falte o cambie de color deja un
        # texto oscuro sobre oscuro, y eso solo se vería en un iPhone
        cuerpo = (await _todos_los_correos(correo))["invitacion_sin_cuenta"]
        assert _reglas_del_oscuro(cuerpo) == {
            ".o-pagina": f"background:{O_FONDO}!important;",
            ".o-tarjeta": f"background:{O_TARJETA}!important;border:1px solid {O_LINEA}!important;",
            ".o-cabecera": f"background:{O_REALCE}!important;color:{LIMA}!important;",
            ".o-realce": f"background:{O_REALCE}!important;",
            ".o-tinta": f"color:{O_TINTA}!important;",
            ".o-texto": f"color:{O_TEXTO}!important;",
            ".o-apagado": f"color:{O_APAGADO}!important;",
            ".o-marca": f"color:{LIMA}!important;",
            ".o-cita": f"border-color:{LIMA}!important;",
            ".o-linea": f"border-color:{O_LINEA}!important;",
            ".o-aviso": "background:#3a3222!important;border-color:#6b5a2e!important;"
            "color:#f0c36a!important;",
            ".o-aviso .o-tinta": "color:#f0c36a!important;",
            # La cabecera: fuera la clara, dentro la oscura
            ".o-claro": "display:none!important;",
            ".o-oscuro": "display:block!important;max-height:none!important;"
            "overflow:visible!important;",
        }

    @pytest.mark.asyncio
    async def test_every_class_in_use_has_its_dark_rule(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            reglas = _reglas_del_oscuro(cuerpo)
            usadas = {c for n in _arbol(cuerpo).todos() for c in n.attrs.get("class", "").split()}
            assert usadas, nombre
            assert {f".{c}" for c in usadas} <= set(reglas), nombre

    @pytest.mark.asyncio
    async def test_everything_coloured_inline_turns_dark(self, correo):
        # Lo contrario: todo lo que lleva un color en línea cambia en oscuro. Solo se
        # libra el botón principal, lima con letra oscura en los dos modos
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            for nodo in _arbol(cuerpo).todos():
                pinta = re.search(
                    r"(?:^|;)(?:color|background|border|border-(?:top|left|color)):", nodo.estilo
                )
                if not pinta or nodo.etiqueta == "img":
                    continue
                es_del_principal = _fondo(nodo) == LIMA or any(
                    _fondo(a) == LIMA for a in nodo.ancestros()
                )
                if es_del_principal:
                    assert "class" not in nodo.attrs, (nombre, nodo.etiqueta)
                    continue
                assert nodo.attrs.get("class", "").startswith("o-"), (
                    nombre,
                    nodo.etiqueta,
                    nodo.estilo[:60],
                )

    @pytest.mark.asyncio
    async def test_every_bold_turns_dark(self, correo):
        # La negrita hereda en claro el color de su párrafo y no lleva ninguno en
        # línea; en oscuro tiene que resaltar con la tinta, no quedarse atrás
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            negritas = _nodos(cuerpo, "strong")
            assert negritas, nombre
            for negrita in negritas:
                assert negrita.attrs.get("class") == "o-tinta", nombre

    @pytest.mark.asyncio
    async def test_the_footer_says_the_current_year(self, correo):
        anio = str(ahora_en_utc().year)
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            assert f"© {anio} Comeback Golf" in cuerpo, nombre
            assert "2025" not in cuerpo or anio == "2025", nombre

    @pytest.mark.asyncio
    async def test_every_email_has_an_english_block_with_its_own_button(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            assert "English" in cuerpo, nombre
            assert len(_botones(cuerpo)) >= 2, nombre


class TestEveryEmailRepeatsItsLink:
    """El enlace a mano bajo el botón, por si no se puede pulsar (CodeRabbit en
    la PR #390: la #389 lo pide en todos, y solo lo llevaban dos)."""

    @pytest.mark.asyncio
    async def test_all_repeat_the_main_link_below_the_button(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            principal = _botones(cuerpo)[0]
            respaldo = [p for p in _nodos(cuerpo, "p") if "¿No funciona el botón?" in p.texto]
            assert len(respaldo) == 1, nombre
            enlaces = [n for n in respaldo[0].todos() if n.etiqueta == "a"]
            assert len(enlaces) == 1, nombre
            assert enlaces[0].attrs["href"] == principal, nombre
            assert enlaces[0].texto == principal, nombre
            # Se abre fuera, como el botón
            assert enlaces[0].attrs.get("target") == "_blank", nombre


@dataclass
class _Nodo:
    etiqueta: str
    attrs: dict[str, str]
    padre: "_Nodo | None" = None
    hijos: list["_Nodo"] = field(default_factory=list)
    texto: str = ""

    @property
    def estilo(self) -> str:
        return self.attrs.get("style") or ""

    def todos(self):
        yield self
        for hijo in self.hijos:
            yield from hijo.todos()

    def ancestros(self):
        nodo = self.padre
        while nodo is not None:
            yield nodo
            nodo = nodo.padre


_VACIAS = {"meta", "img", "br", "hr", "link", "input"}


class _Arbol(HTMLParser):
    """Un árbol mínimo del HTML, sin cerrar nada por su cuenta: un <p> dentro
    de otro <p> se queda dentro, y así se ve."""

    def __init__(self, html_body):
        super().__init__(convert_charrefs=True)
        self.raiz = _Nodo("#raiz", {})
        self._actual = self.raiz
        self.feed(html_body)
        self.close()

    def handle_starttag(self, tag, attrs):
        nodo = _Nodo(tag, {k: v or "" for k, v in attrs}, padre=self._actual)
        self._actual.hijos.append(nodo)
        if tag not in _VACIAS:
            self._actual = nodo

    def handle_endtag(self, tag):
        if tag in _VACIAS:
            return
        # Estricto: un </td> o </table> que falte descuadra el cierre y falla
        assert self._actual.etiqueta == tag, f"</{tag}> cierra <{self._actual.etiqueta}>"
        self._actual = self._actual.padre

    def close(self):
        super().close()
        assert self._actual is self.raiz, f"<{self._actual.etiqueta}> sin cerrar"

    def handle_data(self, data):
        self._actual.texto += data


def _arbol(html_body):
    return _Arbol(html_body).raiz


def _nodos(html_body, etiqueta):
    return [n for n in _arbol(html_body).todos() if n.etiqueta == etiqueta]


def _anclas_de_boton(html_body):
    return [n for n in _nodos(html_body, "a") if "data-boton" in n.attrs]


def _fondo(nodo):
    encontrado = re.search(r"(?:^|;)background:(#[0-9a-fA-F]{3,6})", nodo.estilo)
    return encontrado.group(1) if encontrado else None


BOSQUE_PROFUNDO = "#222d24"
LIMA = "#ddf478"
# El oscuro: los colores de la app en oscuro
O_FONDO, O_TARJETA, O_REALCE = "#222d24", "#273328", "#354638"
O_TINTA, O_TEXTO, O_APAGADO, O_LINEA = "#e8ddce", "#d3d9cf", "#b7bdb2", "#56655a"


def _reglas_del_oscuro(html_body):
    """{selector: declaraciones} de lo que hay dentro del `prefers-color-scheme: dark`."""
    estilo = re.search(r"<style>(.*?)</style>", html_body, re.S).group(1)
    dentro = estilo.split("@media (prefers-color-scheme:dark){", 1)[1]
    assert dentro.endswith("}")
    reglas = re.findall(r"([^{}]+)\{([^{}]*)\}", dentro[:-1])
    # Nada suelto entre regla y regla
    assert "".join(f"{s}{{{d}}}" for s, d in reglas) == dentro[:-1]
    return dict(reglas)


FONDO_DE_PAGINA = "#f8f7f2"
ARENA = "#e8ddce"
SALVIA = "#dce3d7"

# El dibujo de la cabecera de cada correo (Agustín, 25 nov 2026)
DIBUJOS = {
    "verificacion": "guante",
    "restablecer": "gorra",
    "confirmar_cambio": "gorra",
    "google": "gorra",
    "cambiada": "bunker",
    "cambio_pedido": "bunker",
    "intento_de_registro": "bunker",
    "cuenta_asegurada": "bunker",
    "correo_cambiado": "bunker",
    "nuevo_inicio": "bunker",
    "sesion_cerrada": "bunker",
    "intentos_fallidos": "bunker",
    "invitacion": "carrito",
    "invitacion_sin_cuenta": "carrito",
    "handicaps": "tarjeta",
    "rfeg_no_encontrado": "tarjeta",
    "programada": "tarjeta",
    "amistad": "palos",
}


class TestTheLayoutSurvivesAnyMailClient:
    """En Mail de iOS con modo oscuro el aviso del 21 oct perdió la cabecera
    verde y el botón: el fondo puesto solo por CSS desaparecía. Se pide modo
    claro, el color va también en `bgcolor` y los botones son de tabla."""

    @pytest.mark.asyncio
    async def test_the_head_declares_both_modes(self, correo):
        # `light dark`: Mail de Apple usa los colores del correo —los claros en línea o
        # los oscuros del <style>— en vez de invertirlos por su cuenta, que es lo que
        # borró la cabecera el 21 oct
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            cabeza = cuerpo.split("</head>")[0]
            assert '<meta name="color-scheme" content="light dark">' in cabeza, nombre
            assert '<meta name="supported-color-schemes" content="light dark">' in cabeza, nombre
            assert "<style>:root{color-scheme:light dark;}" in cabeza, nombre
            # No es una propiedad CSS: solo va en su meta
            assert cuerpo.count("supported-color-schemes") == 1, nombre
            # Mail de iOS no convierte en enlace las fechas y las horas
            assert (
                '<meta name="format-detection" content="telephone=no,date=no,address=no,email=no">'
                in cabeza
            ), nombre

    @pytest.mark.asyncio
    async def test_every_coloured_background_also_carries_bgcolor(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            con_fondo = [n for n in _arbol(cuerpo).todos() if _fondo(n)]
            for nodo in con_fondo:
                assert nodo.attrs.get("bgcolor") == _fondo(nodo), (
                    nombre,
                    nodo.etiqueta,
                    nodo.estilo,
                )
            colores = {_fondo(n) for n in con_fondo}
            # Página, tarjeta y cabecera, como mínimo
            assert {FONDO_DE_PAGINA, ARENA, SALVIA} <= colores, (nombre, colores)
            cuerpo_html = _nodos(cuerpo, "body")[0]
            assert cuerpo_html.attrs.get("bgcolor") == FONDO_DE_PAGINA, nombre

    @pytest.mark.asyncio
    async def test_the_boxes_carry_bgcolor_too(self, correo):
        htmls = await _todos_los_correos(correo)
        cajas = {
            "recuadro": (htmls["invitacion"], FONDO_DE_PAGINA),
            "aviso": (htmls["cambiada"], "#fff7ed"),
        }
        for caja, (cuerpo, color) in cajas.items():
            celdas = [n for n in _nodos(cuerpo, "td") if _fondo(n) == color]
            assert celdas, caja
            assert all(c.attrs.get("bgcolor") == color for c in celdas), caja

    @pytest.mark.asyncio
    async def test_primary_buttons_are_bulletproof(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            ancla = _anclas_de_boton(cuerpo)[0]
            self._es_a_prueba_de_balas(ancla, fondo=LIMA, nombre=nombre)
            # Lima con letra oscura también en oscuro: sin clases que lo cambien
            assert "class" not in ancla.attrs and "class" not in ancla.padre.attrs, nombre

    @pytest.mark.asyncio
    async def test_secondary_buttons_are_bulletproof_and_turn_dark(self, correo):
        htmls = await _todos_los_correos(correo)
        for nombre, cuerpo in htmls.items():
            secundarios = _anclas_de_boton(cuerpo)[1:]
            assert secundarios, nombre
            for ancla in secundarios:
                self._es_a_prueba_de_balas(ancla, fondo=FONDO_DE_PAGINA, nombre=nombre)
                assert ancla.padre.attrs.get("class") == "o-realce", nombre
                assert ancla.attrs.get("class") == "o-tinta", nombre
                assert ancla.hijos[0].attrs.get("class") == "o-tinta", nombre
        # Registrarse + el inglés
        assert len(_anclas_de_boton(htmls["invitacion_sin_cuenta"])) == 3

    @staticmethod
    def _es_a_prueba_de_balas(ancla, *, fondo, nombre):
        celda = ancla.padre
        # El color lo pone la celda, por atributo y por estilo
        assert celda.etiqueta == "td", nombre
        assert celda.attrs.get("bgcolor") == fondo, nombre
        assert _fondo(celda) == fondo, nombre
        # Rectangular y sin borde (Agustín, 25 nov 2026)
        assert "border" not in celda.estilo, nombre
        tabla = celda.padre.padre
        assert tabla.etiqueta == "table", nombre
        assert "margin:6px 0 14px;" in tabla.estilo, nombre
        # El enlace solo es texto, en bloque para que no sobre color bajo la letra, y
        # en UNA línea
        assert "background" not in ancla.estilo, nombre
        assert "display:block;" in ancla.estilo, nombre
        assert "white-space:nowrap;" in ancla.estilo, nombre
        assert "text-align:center;" in ancla.estilo, nombre
        assert f"color:{BOSQUE_PROFUNDO};" in ancla.estilo, nombre
        relleno = re.search(r"(?:^|;)padding:([^;]+);", ancla.estilo)
        assert relleno, nombre
        # Outlook de escritorio ignora el relleno del <a>: lo pide en la celda
        assert f"mso-padding-alt:{relleno.group(1)};" in celda.estilo, nombre
        assert ancla.attrs.get("target") == "_blank", nombre
        # Y el color, otra vez en un span alrededor del texto
        assert len(ancla.hijos) == 1, nombre
        span = ancla.hijos[0]
        assert span.etiqueta == "span", nombre
        assert span.estilo == f"color:{BOSQUE_PROFUNDO};", nombre
        assert span.texto.strip(), nombre
        assert not ancla.texto.strip(), nombre

    @pytest.mark.asyncio
    async def test_a_single_button_takes_the_width_of_its_text(self, correo):
        # A la izquierda y sin ocupar la columna: una tabla sin ancho
        htmls = await _todos_los_correos(correo)
        ancla = _anclas_de_boton(htmls["verificacion"])[0]
        tabla = ancla.padre.padre.padre
        assert "width" not in tabla.attrs
        assert "padding:13px 18px;" in ancla.estilo

    @pytest.mark.asyncio
    async def test_two_buttons_share_the_row_in_halves(self, correo):
        # Los dos correos con botón secundario: en paralelo, a partes iguales, para
        # que quepan en fila y en una línea también en el móvil más estrecho
        htmls = await _todos_los_correos(correo)
        con_pareja = {n for n, c in htmls.items() if "data-pareja" in c}
        assert con_pareja == {"invitacion_sin_cuenta", "intento_de_registro"}
        for nombre in con_pareja:
            principal, secundario = _anclas_de_boton(htmls[nombre])[:2]
            fila = principal.padre.padre
            assert secundario.padre.padre is fila, nombre
            tabla = fila.padre
            assert tabla.attrs.get("width") == "100%", nombre
            # Reparto fijo: solo el hueco lleva ancho, y las dos celdas se quedan el
            # resto a medias (con 50 % + 8 px + 50 % Outlook ensanchaba la tabla)
            assert "table-layout:fixed;" in tabla.estilo, nombre
            assert [c.attrs.get("width") for c in fila.hijos] == [None, "8", None], nombre
            for ancla in (principal, secundario):
                assert "font-size:13px;" in ancla.estilo, nombre
                assert "padding:13px 2px;" in ancla.estilo, nombre
                # A 320 px quedan 116 px por celda. Medidos a 13 px en negrita, el más
                # ancho de hoy es «Nueva contraseña», 112 px; «Ver la invitación», con
                # una letra más, 98. Las letras no miden el ancho: el tope solo avisa
                # de que un texto nuevo hay que medirlo antes de ponerlo en pareja
                texto = ancla.hijos[0].texto.strip()
                assert len(texto) <= 17, (nombre, texto)

    @pytest.mark.asyncio
    async def test_no_single_button_is_wider_than_a_narrow_phone(self, correo):
        # Un botón solo no parte su texto: más largo que la tarjeta en un móvil de
        # 320 px (246 px útiles) la ensancharía. El más largo de hoy, «Restablecer mi
        # contraseña» (25 letras), mide 216 px con su relleno
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            for ancla in _anclas_de_boton(cuerpo):
                texto = ancla.hijos[0].texto.strip()
                assert len(texto) <= 26, (nombre, texto)

    @pytest.mark.asyncio
    async def test_no_paragraph_sits_inside_another(self, correo):
        for nombre, cuerpo in (await _todos_los_correos(correo)).items():
            for p in _nodos(cuerpo, "p"):
                assert all(a.etiqueta != "p" for a in p.ancestros()), nombre


class TestTheButtonsGoWhereTheySay:
    """Cada botón lleva a una pantalla que existe."""

    async def test_verification_goes_to_verify_email_with_its_token(self, correo):
        await correo.send_verification_email("a@b.com", "Ana", "tok123")
        _, _, texto, cuerpo = _enviado(correo)
        assert _botones(cuerpo)[0] == f"{WEB}/verify-email?token=tok123"
        assert f"{WEB}/verify-email?token=tok123" in texto

    @pytest.mark.asyncio
    async def test_reset_puts_the_link_in_the_button_and_the_fallback(self, correo):
        enlace = f"{WEB}/reset-password/abc"
        await correo.send_password_reset_email("a@b.com", enlace, "Ana")
        _, _, texto, cuerpo = _enviado(correo)
        assert _botones(cuerpo)[0] == enlace
        # El enlace a mano, por si el botón no funciona
        assert cuerpo.count(enlace) >= 3
        # Vale una hora (fase 3, C2)
        assert "1 hora" in cuerpo and "1 hour" in cuerpo
        assert "24 horas" not in cuerpo and "24 hours" not in cuerpo
        assert enlace in texto

    @pytest.mark.asyncio
    async def test_password_changed_with_google_unlinked_says_so_in_both_languages(self, correo):
        """
        Given: Un restablecimiento que le quitó el Google a la cuenta
        When: Sale el correo de contraseña cambiada
        Then: Dice, en texto y en HTML, en los dos idiomas, que se desvinculó y cómo
              volver a vincularlo (Agustín, 8 nov 2026)
        """
        await correo.send_password_changed_notification("a@b.com", "Ana", google_unlinked=True)
        _, _, texto, cuerpo = _enviado(correo)
        legible = html.unescape(cuerpo)
        for frase in (
            "También hemos desvinculado tu cuenta de Google. Si la usabas para entrar, "
            "vuelve a vincularla desde tu perfil.",
            "We also unlinked your Google account. If you used it to sign in, link it "
            "again from your profile.",
        ):
            assert frase in texto
            assert frase in legible

    @pytest.mark.asyncio
    async def test_password_changed_without_google_unlinked_does_not_mention_google(self, correo):
        """
        Given: Un cambio de contraseña sin Google quitado
        When: Sale el correo
        Then: Ni una palabra de Google
        """
        await correo.send_password_changed_notification("a@b.com", "Ana")
        _, _, texto, cuerpo = _enviado(correo)
        assert "Google" not in texto
        assert "Google" not in cuerpo

    @pytest.mark.asyncio
    async def test_password_changed_offers_to_reset_it(self, correo):
        await correo.send_password_changed_notification("a@b.com", "Ana")
        _, _, _, cuerpo = _enviado(correo)
        assert _botones(cuerpo)[0] == f"{WEB}/forgot-password"

    @pytest.mark.asyncio
    async def test_the_invitation_opens_the_players_invitations(self, correo):
        # Llevaba a /invitations, que no existe: el invitado veía una página en blanco
        await correo.send_invitation_email(
            "a@b.com", "Ana", "Pablo", "Copa", None, datetime(2026, 10, 3, tzinfo=UTC)
        )
        _, _, texto, cuerpo = _enviado(correo)
        assert _botones(cuerpo)[0] == f"{WEB}/player/invitations"
        assert f"{WEB}/player/invitations" in texto
        assert f'"{WEB}/invitations"' not in cuerpo

    @pytest.mark.asyncio
    async def test_an_invitee_without_account_also_gets_the_register_button(self, correo):
        await correo.send_invitation_email(
            "a@b.com", None, "Pablo", "Copa", None, datetime(2026, 10, 3, tzinfo=UTC)
        )
        _, _, _, cuerpo = _enviado(correo)
        assert f"{WEB}/register" in _botones(cuerpo)

    @pytest.mark.asyncio
    async def test_a_registered_invitee_gets_no_register_button(self, correo):
        await correo.send_invitation_email(
            "a@b.com", "Ana", "Pablo", "Copa", None, datetime(2026, 10, 3, tzinfo=UTC)
        )
        _, _, _, cuerpo = _enviado(correo)
        assert f"{WEB}/register" not in _botones(cuerpo)

    @pytest.mark.asyncio
    async def test_the_friend_request_opens_the_friends_screen(self, correo):
        await correo.send_friend_request_email("a@b.com", "Ana", "Pablo")
        _, _, _, cuerpo = _enviado(correo)
        assert _botones(cuerpo)[0] == f"{WEB}/friends"


class TestNothingFromTheUserEntersUnescaped:
    """Nombres y mensajes los escribe la gente: nunca entran como HTML."""

    async def test_a_name_with_an_ampersand_is_escaped_in_the_verification(self, correo):
        await correo.send_verification_email("a@b.com", "Tom & Jerry's", "t")
        _, _, _, cuerpo = _enviado(correo)
        assert "Tom &amp; Jerry&#x27;s" in cuerpo
        assert "Tom & Jerry's" not in cuerpo

    @pytest.mark.asyncio
    async def test_a_name_with_an_ampersand_is_escaped_when_the_password_changes(self, correo):
        await correo.send_password_changed_notification("a@b.com", "Tom & Jerry")
        _, _, _, cuerpo = _enviado(correo)
        assert "Tom &amp; Jerry" in cuerpo

    @pytest.mark.asyncio
    async def test_the_personal_message_cannot_inject_markup(self, correo):
        await correo.send_invitation_email(
            "a@b.com",
            "Ana",
            "Pablo",
            "Copa & Cena",
            '<script>alert("x")</script>',
            datetime(2026, 10, 3, tzinfo=UTC),
        )
        _, _, _, cuerpo = _enviado(correo)
        assert "<script>" not in cuerpo
        assert "&lt;script&gt;" in cuerpo
        assert "Copa &amp; Cena" in cuerpo


class TestTheInvitationContent:
    """Lo que dice la invitación."""

    @pytest.mark.asyncio
    async def test_the_quote_appears_only_with_a_personal_message(self, correo):
        caduca = datetime(2026, 10, 3, tzinfo=UTC)
        await correo.send_invitation_email("a@b.com", "Ana", "Pablo", "Copa", None, caduca)
        sin_mensaje = _enviado(correo)[3]
        correo._send_email.reset_mock()
        await correo.send_invitation_email(
            "a@b.com", "Ana", "Pablo", "Copa", "Te esperamos", caduca
        )
        con_mensaje = _enviado(correo)[3]

        assert "data-cita" not in sin_mensaje
        assert "data-cita" in con_mensaje
        assert "Te esperamos" in con_mensaje

    @pytest.mark.asyncio
    async def test_it_says_who_invites_to_what_and_until_when(self, correo):
        await correo.send_invitation_email(
            "a@b.com", "Ana", "Pablo Noche", "Copa", None, datetime(2026, 10, 3, tzinfo=UTC)
        )
        _, asunto, texto, cuerpo = _enviado(correo)
        assert "Pablo Noche te invita a jugar" in cuerpo
        assert "Copa" in cuerpo
        assert "03/10/2026" in cuerpo
        assert "Copa" in asunto
        assert "03/10/2026" in texto


def _frase_que_presenta(html_body):
    """El texto, sin etiquetas, del único párrafo que presenta la competición."""
    (parrafo,) = [
        p for p in re.findall(r"<p [^>]*>(.*?)</p>", html_body, re.S) if "te invita:" in p
    ]
    return html.unescape(re.sub(r"<[^>]+>", "", parrafo))


class TestTheInvitationDoesNotRepeatItsTitle:
    """El título ya dice «Carlos te invita a jugar»: la primera frase solo presenta
    la competición. Antes lo repetía, y sin nombre del invitado quedaba «Hola, Carlos
    te ha invitado», que parecía saludar a quien invita (Agustín, 25 nov 2026)."""

    @pytest.mark.asyncio
    async def test_without_the_invitee_name_it_only_introduces_the_competition(self, correo):
        await correo.send_invitation_email(
            "b@b.com", None, "Carlos Ruiz", "Copa", None, ahora_en_utc() + timedelta(days=7)
        )
        cuerpo = _enviado(correo)[3]

        assert _frase_que_presenta(cuerpo) == "Esta es la competición a la que te invita:"
        assert "Carlos Ruiz te invita a jugar" in cuerpo
        assert "te ha invitado" not in cuerpo

    @pytest.mark.asyncio
    async def test_with_the_invitee_name_it_greets_them(self, correo):
        await correo.send_invitation_email(
            "b@b.com", "Bea", "Carlos Ruiz", "Copa", None, ahora_en_utc() + timedelta(days=7)
        )
        cuerpo = _enviado(correo)[3]

        assert _frase_que_presenta(cuerpo) == (
            "Hola Bea, esta es la competición a la que te invita:"
        )


class TestTheHandicapNotFoundEmail:
    """
    Al jugador español al que la RFEG no encontró (H3, 15 nov 2026), con el
    texto aprobado: «No hemos encontrado tu hándicap en la RFEG para {competición}.
    Revisa que tu nombre y apellidos en tu perfil sean los de tu licencia, y
    vuelve a pedirlo desde tu perfil.»
    """

    @pytest.mark.asyncio
    async def test_it_says_the_approved_text_and_opens_the_profile(self, correo):
        """
        Given un jugador no encontrado en «Medal de octubre»
        When se le escribe
        Then lleva el texto aprobado, en castellano y en inglés, y abre la edición
             de su perfil, donde se pide a la RFEG
        """
        await correo.send_handicap_not_found_email("luis@b.com", "Luis", "Medal de octubre")

        destinatario, asunto, texto, cuerpo = _enviado(correo)
        assert destinatario == '"Luis" <luis@b.com>'
        assert "Medal de octubre" in asunto
        aprobado = (
            "No hemos encontrado tu hándicap en la RFEG para Medal de octubre. Revisa que "
            "tu nombre y apellidos en tu perfil sean los de tu licencia, y vuelve a "
            "pedirlo desde tu perfil."
        )
        assert aprobado in texto
        assert "No hemos encontrado tu hándicap en la RFEG para" in cuerpo
        assert "We could not find your handicap in the RFEG" in texto
        assert _botones(cuerpo)[0] == f"{WEB}/profile/edit"

    @pytest.mark.asyncio
    async def test_names_are_escaped(self, correo):
        """Given nombres con HTML When se le escribe Then no van tal cual."""
        await correo.send_handicap_not_found_email("luis@b.com", "<b>Luis</b>", "<i>Copa</i>")

        _, _, _, cuerpo = _enviado(correo)
        assert "<b>Luis</b>" not in cuerpo
        assert "<i>Copa</i>" not in cuerpo


class TestTheHandicapsPendingEmail:
    """El aviso al organizador de hándicaps sin actualizar con la RFEG (#251)."""

    @pytest.mark.asyncio
    async def test_it_opens_the_competition_and_names_who_is_pending(self, correo):
        await correo.send_handicaps_pending_email(
            "org@b.com", "Ana", "Medal de octubre", "c-1", ["Luis Pérez", "Eva Gil"]
        )
        destinatario, asunto, texto, cuerpo = _enviado(correo)
        assert destinatario == '"Ana" <org@b.com>'
        assert "Medal de octubre" in asunto
        assert _botones(cuerpo)[0] == f"{WEB}/competitions/c-1"
        assert f"{WEB}/competitions/c-1" in texto
        for nombre in ("Luis Pérez", "Eva Gil"):
            assert nombre in cuerpo and nombre in texto

    @pytest.mark.asyncio
    async def test_it_says_the_text_approved_on_16_nov(self, correo):
        """
        Given una lista con un no encontrado y un extranjero
        When se escribe al organizador
        Then lleva el texto aprobado el 16 nov 2026, en castellano y en inglés, con
             el mismo asunto y el mismo botón de siempre
        """
        await correo.send_handicaps_pending_email(
            "org@b.com", "Ana", "Medal de octubre", "c-1", ["Luis Pérez", "John Smith"]
        )

        _, asunto, texto, cuerpo = _enviado(correo)
        es = (
            "Estos jugadores no se han podido actualizar con la RFEG en Medal de octubre: "
            "Luis Pérez, John Smith. A los que no se encontraron, o no tienen licencia "
            "española, ponles el hándicap a mano desde la ficha de la competición. Si la "
            "RFEG no respondió, vuelve a intentarlo con «Actualizar hándicaps»."
        )
        en = (
            "These players could not be updated with the RFEG in Medal de octubre: "
            "Luis Pérez, John Smith. For those who weren't found, or don't have a Spanish "
            "licence, set their handicap by hand from the competition page. If the RFEG "
            'didn\'t respond, try again with "Update handicaps".'
        )
        assert es in texto
        assert en in texto
        assert "no se pudo actualizar" not in texto
        assert "ponles el hándicap a mano desde la ficha de la competición" in cuerpo
        assert "set their handicap by hand from the competition page" in cuerpo
        assert asunto == (
            "Hándicaps sin actualizar en Medal de octubre | "
            "Handicaps not updated in Medal de octubre"
        )
        assert _botones(cuerpo)[0] == f"{WEB}/competitions/c-1"

    @pytest.mark.asyncio
    async def test_player_names_are_escaped(self, correo):
        await correo.send_handicaps_pending_email(
            "org@b.com", "Ana", "Copa & Cena", "c-1", ["<b>Luis</b>"]
        )
        _, _, _, cuerpo = _enviado(correo)
        assert "<b>Luis</b>" not in cuerpo
        assert "Copa &amp; Cena" in cuerpo

    @pytest.mark.asyncio
    async def test_it_does_not_say_it_was_the_close(self, correo):
        """También la manda una actualización con el botón: no siempre fue al cerrar (#251)."""
        await correo.send_handicaps_pending_email("org@b.com", "Ana", "Copa", "c-1", ["Luis"])
        _, _, texto, cuerpo = _enviado(correo)
        for contenido in (texto, cuerpo):
            assert "cerrar las inscripciones" not in contenido
            assert "enrollments closed" not in contenido


class TestTheScheduledUpdateSkippedEmail:
    """La programada no se lanzó: a su hora la ventana estaba cerrada (#251)."""

    @pytest.mark.asyncio
    async def test_it_says_why_and_opens_the_competition(self, correo):
        await correo.send_scheduled_handicaps_update_skipped_email(
            "org@b.com", "Ana", "Medal de octubre", "c-1", "Hay una jornada en marcha."
        )
        destinatario, asunto, texto, cuerpo = _enviado(correo)
        assert destinatario == '"Ana" <org@b.com>'
        assert "Medal de octubre" in asunto
        assert "Hay una jornada en marcha." in cuerpo and "Hay una jornada en marcha." in texto
        assert _botones(cuerpo)[0] == f"{WEB}/competitions/c-1"

    @pytest.mark.asyncio
    async def test_the_reason_is_escaped(self, correo):
        await correo.send_scheduled_handicaps_update_skipped_email(
            "org@b.com", "Ana", "Copa", "c-1", "<b>x</b>"
        )
        _, _, _, cuerpo = _enviado(correo)
        assert "<b>x</b>" not in cuerpo


@pytest.mark.parametrize(
    ("motivo", "fallos", "minutos", "dice", "en_ingles"),
    [
        ("red", 10, 30, "10 veces desde España", "10 times from España"),
        ("aviso", 25, 0, "Todavía no hemos bloqueado nada", "Nothing is blocked yet"),
        ("respaldo", 50, 30, "bloqueado 30 minutos la entrada", "paused for 30 minutes"),
        ("dia", 150, 1440, "bloqueado 24 horas la entrada", "paused for 24 hours"),
    ],
)
async def test_el_correo_de_intentos_fallidos_dice_lo_que_paso(
    correo, motivo, fallos, minutos, dice, en_ingles
):
    """
    Given: El correo de intentos fallidos de cada motivo (BE #732)
    When: Se envía
    Then: Cuenta lo que pasó con sus números, en castellano y en inglés, y el botón
          lleva a cambiar la contraseña
    """
    await correo.send_failed_logins_notification(
        to_email="ana@example.com",
        user_name="Ana",
        motivo=motivo,
        cuando="6 nov 2026, 10:30 (hora de España)",
        pais="España",
        fallos=fallos,
        minutos=minutos,
    )

    _, asunto, texto, html = _enviado(correo)
    assert "Intentos fallidos" in asunto
    assert dice in texto and dice in html
    assert en_ingles in texto
    assert _botones(html)[0] == f"{WEB}/profile/edit"


class TestCorreosDelCambioDeCorreo:
    """Los dos correos del cambio de correo pendiente (#749)."""

    @pytest.mark.asyncio
    async def test_the_confirmation_goes_to_the_new_address_with_its_link(self, correo):
        """El enlace de confirmar, al correo nuevo: botón, 24 horas y la página del front."""
        await correo.send_email_change_confirmation("ana@trabajo.com", "Ana", "tok-123")

        destinatario, _, texto, cuerpo = _enviado(correo)
        enlace = f"{WEB}/confirm-email-change?token=tok-123"
        assert destinatario == "ana@trabajo.com"
        assert _botones(cuerpo)[0] == enlace
        assert enlace in texto
        assert "24 horas" in cuerpo and "24 hours" in cuerpo

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("vinculado", "frase"), [(True, "vinculado"), (False, "desvinculado")])
    async def test_the_google_notice_says_what_happened(self, correo, vinculado, frase):
        """El aviso de Google (BE #753): qué pasó y qué hacer si no fue el dueño"""
        await correo.send_google_account_notice("ana@gmail.com", "Ana", vinculado)

        destinatario, _, texto, cuerpo = _enviado(correo)
        assert destinatario == "ana@gmail.com"
        assert f"Google {frase}" in cuerpo and f"Google {frase}" in texto
        assert _botones(cuerpo)[0] == f"{WEB}/forgot-password"
        # Vinculado: restablecer la contraseña también quita ese Google (BE #753)
        quita = "también quitará ese Google"
        assert (quita in cuerpo and quita in texto) is vinculado

    @pytest.mark.asyncio
    async def test_the_verification_email_tells_who_did_not_sign_up_to_ignore_it(self, correo):
        """
        Given: un correo de verificación
        When: lo recibe quien no creó la cuenta
        Then: se le dice que lo ignore, sin invitarle a quedarse la cuenta (Agustín, 8 nov 2026)
        """
        await correo.send_verification_email("ana@gmail.com", "Ana", "tok")

        _, _, texto, cuerpo = _enviado(correo)
        for aviso in (
            "¿No has creado tú esta cuenta? Ignora este correo",
            "Just ignore this email",
        ):
            assert aviso in cuerpo and aviso in texto
        # El aviso en ámbar del cuerpo, no solo el pie (revisión)
        assert "Ignora este correo y no pulses el botón." in cuerpo
        # El inglés lo dice en su bloque, junto a su botón; el pie no lo repite (/code-review)
        assert "Just ignore this email and don't click the button." in html.unescape(cuerpo)
        assert cuerpo.count("¿No has creado tú esta cuenta?") == 1
        for invitacion in (
            "quedártela",
            "será tuya",
            "take it over",
            "Olvidé mi contraseña",
            "forgot-password",
        ):
            assert invitacion not in cuerpo and invitacion not in texto

    @pytest.mark.asyncio
    async def test_the_change_notice_uses_the_configured_contact(self, correo, monkeypatch):
        """El buzón de contacto, el de la configuración (code-review): no uno fijo"""
        from src.config.settings import settings

        monkeypatch.setattr(settings, "CONTACT_EMAIL", "soporte@example.com")

        await correo.send_email_changed_notice("ana@gmail.com", "Ana", "ana@trabajo.com")

        _, _, texto, cuerpo = _enviado(correo)
        assert "soporte@example.com" in cuerpo and "soporte@example.com" in texto

    @pytest.mark.asyncio
    async def test_the_secured_notice_by_google_says_the_password_is_gone(self, correo):
        """La toma por Google (BE #753): sin contraseña, y cómo tener una"""
        await correo.send_account_secured_notice("ana@gmail.com", "Ana", "google")

        destinatario, _, texto, cuerpo = _enviado(correo)
        assert destinatario == "ana@gmail.com"
        assert "quitamos la contraseña" in cuerpo and "quitamos la contraseña" in texto
        assert _botones(cuerpo)[0] == f"{WEB}/forgot-password"

    @pytest.mark.asyncio
    async def test_the_secured_notice_by_reset_keeps_the_new_password(self, correo):
        """La toma al restablecer: la contraseña es la que acaba de elegir"""
        await correo.send_account_secured_notice("ana@gmail.com", "Ana", "reset")

        _, _, texto, cuerpo = _enviado(correo)
        assert "quitamos la contraseña" not in cuerpo and "quitamos la contraseña" not in texto
        assert "la que acabas de elegir" in cuerpo and "la que acabas de elegir" in texto

    @pytest.mark.asyncio
    async def test_the_change_notice_tells_the_old_address_whom_to_write(self, correo):
        """
        El aviso tras confirmar (BE #753): al correo de antes, el nuevo tapado y a quién
        escribir si no fue el dueño
        """
        await correo.send_email_changed_notice("ana@gmail.com", "Ana", "ana@trabajo.com")

        destinatario, _, texto, cuerpo = _enviado(correo)
        assert destinatario == "ana@gmail.com"
        assert "a***@trabajo.com" in cuerpo and "a***@trabajo.com" in texto
        assert "ana@trabajo.com" not in cuerpo and "ana@trabajo.com" not in texto
        assert "hola@comebackgolf.com" in cuerpo and "hola@comebackgolf.com" in texto

    @pytest.mark.asyncio
    async def test_the_notice_goes_to_the_old_address_with_the_new_one_masked(self, correo):
        """
        El aviso, al correo de antes: el nuevo tapado (lo puede leer quien no es su
        dueño) y el botón para cambiar la contraseña
        """
        await correo.send_email_change_requested_notice("ana@gmail.com", "Ana", "ana@trabajo.com")

        destinatario, _, texto, cuerpo = _enviado(correo)
        assert destinatario == "ana@gmail.com"
        assert "a***@trabajo.com" in cuerpo and "a***@trabajo.com" in texto
        assert "ana@trabajo.com" not in cuerpo and "ana@trabajo.com" not in texto
        assert _botones(cuerpo)[0] == f"{WEB}/forgot-password"


class TestTheSessionClosedForSecurityNotice:
    """El aviso de la sesión cerrada por seguridad (F-02, caso A4)."""

    @pytest.mark.asyncio
    async def test_it_says_what_happened_in_both_languages(self, correo):
        """
        Qué pasó (cerramos la sesión de ese dispositivo), dónde y cuándo, en los dos
        idiomas, y el botón a sus dispositivos
        """
        await correo.send_session_closed_for_security_notice(
            "ana@gmail.com",
            "Ana",
            "iPhone · Safari",
            "10 nov 2026, 12:30 (hora de España)",
            "España",
        )

        destinatario, asunto, texto, cuerpo = _enviado(correo)
        assert destinatario == "ana@gmail.com"
        assert "Hemos cerrado tu sesión en un dispositivo por seguridad" in asunto
        assert "We signed you out of a device for security" in asunto
        for parte in (texto, cuerpo):
            assert "iPhone · Safari · España" in parte
            assert "10 nov 2026, 12:30 (hora de España)" in parte
            assert "cambia tu contraseña" in parte
            assert "change your password" in parte
        assert _botones(cuerpo)[0] == f"{WEB}/profile/devices"
        assert f"{WEB}/profile/devices" in texto

    @pytest.mark.asyncio
    async def test_without_a_country_it_is_not_mentioned(self, correo):
        await correo.send_session_closed_for_security_notice(
            "ana@gmail.com", "Ana", "iPhone · Safari", "hoy", None
        )

        _, _, texto, cuerpo = _enviado(correo)
        assert "iPhone · Safari" in cuerpo and "None" not in cuerpo and "None" not in texto

    @pytest.mark.asyncio
    async def test_the_name_is_escaped(self, correo):
        await correo.send_session_closed_for_security_notice(
            "ana@gmail.com", "<b>Ana</b>", "iPhone", "hoy", None
        )

        _, _, _, cuerpo = _enviado(correo)
        assert "<b>Ana</b>" not in cuerpo
