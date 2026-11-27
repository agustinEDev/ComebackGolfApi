"""
A qué sitio llevan los correos (ADR-055).

La API se sirve por dos dominios mientras dura el cambio de marca. Un correo sobre la
propia cuenta lleva al sitio desde el que se actúa: quien pide restablecer la
contraseña en uno no tiene en el otro ni su sesión ni su aplicación instalada. Los
que recibe otra persona, y los que no nacen de una petición, llevan al principal.

  #   correo                | llega por                    | enlaces e imagen
  ----|-----------------------|------------------------------|---------------------
  S1  de la propia cuenta   | api.comebackgolf.com         | www.comebackgolf.com
  S2  de la propia cuenta   | api.antiguo.example      | www.antiguo.example
  S3  cualquiera            | sin petición (programado)    | el principal
  S4  cualquiera            | un host que no es de ninguno | el principal
  S5  cualquiera            | uno solo configurado         | ese
  S6  en segundo plano      | lanzado en una petición      | el de esa petición
  S8  restablecer contraseña| su enlace sale del mismo sitio
  S9  el principal es el PRIMERO de FRONTEND_URL, no el del primer dominio de cookie
  S10 a otra persona (invitación, amistad, hándicaps) | cualquiera | el principal
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.config.aviso_en_segundo_plano import CorreoEnSegundoPlano
from src.config.dependencies.usuarios import get_request_password_reset_use_case
from src.config.settings import settings
from src.shared.infrastructure.email import email_layout
from src.shared.infrastructure.email.email_service import EmailService
from src.shared.infrastructure.http.dominio_de_las_cookies import (
    _host_de_la_peticion,
    web_de_la_peticion,
)

VIEJO = "https://www.antiguo.example"
NUEVO = "https://www.comebackgolf.com"


@pytest.fixture
def dos_sitios(monkeypatch):
    """La configuración de producción durante el cambio: el viejo, el principal."""
    monkeypatch.setenv("COOKIE_DOMAIN", ".antiguo.example,.comebackgolf.com")
    monkeypatch.setattr(settings, "FRONTEND_URL", f"{VIEJO},{NUEVO}")


def _llega_por(host):
    """
    Simula la petición en curso: pone su Host, como el middleware.

    Dentro de un test asíncrono no hay que quitarlo: cada uno corre en su tarea, con
    su copia del contexto.
    """
    return _host_de_la_peticion.set(host)


async def _correo_de_verificacion():
    servicio = EmailService()
    servicio._send_email = AsyncMock(return_value=True)
    await servicio.send_verification_email("a@b.com", "Ana", "tok123")
    llamada = servicio._send_email.call_args
    _, _, texto, html = [*llamada.args, *llamada.kwargs.values()]
    return texto, html


def _sitios_de(html):
    """Los sitios a los que apunta el correo: enlaces e imagen."""
    return set(re.findall(r'(?:href|src)="(https?://[^/"]+)', html))


@pytest.mark.parametrize(
    ("host", "sitio"),
    [
        ("api.comebackgolf.com", NUEVO),  # S1
        ("api.antiguo.example", VIEJO),  # S2
        (None, VIEJO),  # S3
        ("otra.cosa.example", VIEJO),  # S4
        ("api.comebackgolf.com:443", NUEVO),
        ("API.ComebackGolf.com", NUEVO),
        # Un Host que solo acaba como uno de la lista no es de ese sitio
        ("api.comebackgolf.com.atacante.example", VIEJO),
    ],
)
@pytest.mark.asyncio
async def test_el_correo_apunta_al_sitio_de_la_peticion(dos_sitios, host, sitio):
    """
    Given: Los dos sitios configurados y una petición que llega por ese Host
    When: Se manda un correo de la propia cuenta (la verificación)
    Then: Sus enlaces, su texto plano y su imagen son del sitio de la petición; sin
          petición o con un Host que no es de ninguno, del principal
    """
    _llega_por(host)

    texto, html = await _correo_de_verificacion()

    assert _sitios_de(html) == {sitio}
    assert f"{sitio}/verify-email?token=tok123" in texto
    assert f'src="{sitio}/images/correo/cabecera-guante.png"' in html


@pytest.mark.parametrize("host", ["api.comebackgolf.com", "api.antiguo.example", None])
@pytest.mark.asyncio
async def test_con_un_solo_sitio_todo_va_a_ese(monkeypatch, host):
    """
    Given: Una sola dirección en FRONTEND_URL, como hasta hoy (S5)
    When: Se manda el correo, llegue la petición por donde llegue
    Then: Todo apunta a esa
    """
    monkeypatch.setenv("COOKIE_DOMAIN", ".antiguo.example,.comebackgolf.com")
    monkeypatch.setattr(settings, "FRONTEND_URL", VIEJO)
    _llega_por(host)

    _, html = await _correo_de_verificacion()

    assert _sitios_de(html) == {VIEJO}


@pytest.mark.asyncio
async def test_un_correo_en_segundo_plano_conserva_el_sitio_de_su_peticion(dos_sitios):
    """
    Given: Una petición por el sitio nuevo que lanza su correo en segundo plano (S6)
    When: El correo se arma cuando la petición ya ha acabado y quitado su Host
    Then: Sigue apuntando al sitio de aquella petición
    """
    salida = {}

    async def _envia():
        salida["texto"], salida["html"] = await _correo_de_verificacion()

    marca = _host_de_la_peticion.set("api.comebackgolf.com")
    CorreoEnSegundoPlano().lanza("prueba", _envia)
    _host_de_la_peticion.reset(marca)
    while "html" not in salida:
        await asyncio.sleep(0)

    assert _sitios_de(salida["html"]) == {NUEVO}


@pytest.mark.parametrize("host", [None, "otra.cosa.example"])
@pytest.mark.asyncio
async def test_el_principal_es_el_primero_de_las_direcciones(monkeypatch, host):
    """
    Given: El día del cambio: se da la vuelta a FRONTEND_URL y COOKIE_DOMAIN sigue igual (S9)
    When: Se manda un correo sin petición o con un Host que no es de ningún sitio
    Then: Apunta al sitio nuevo, el primero de FRONTEND_URL, y no al del primer dominio
          de cookie
    """
    monkeypatch.setenv("COOKIE_DOMAIN", ".antiguo.example,.comebackgolf.com")
    monkeypatch.setattr(settings, "FRONTEND_URL", f"{NUEVO},{VIEJO}")
    _llega_por(host)

    _, html = await _correo_de_verificacion()

    assert _sitios_de(html) == {NUEVO}


async def _correos_a_otra_persona():
    """Los correos cuyo destinatario no es quien provoca la petición, con su HTML."""
    servicio = EmailService()
    servicio._send_email = AsyncMock(return_value=True)
    envios = {
        "invitacion": lambda: servicio.send_invitation_email(
            "b@b.com", "Bea", "Ana", "Copa", None, datetime.now(UTC) + timedelta(days=7)
        ),
        "amistad": lambda: servicio.send_friend_request_email("b@b.com", "Bea", "Ana"),
    }
    htmls = {}
    for nombre, envia in envios.items():
        await envia()
        llamada = servicio._send_email.call_args
        htmls[nombre] = [*llamada.args, *llamada.kwargs.values()][3]
        servicio._send_email.reset_mock()
    return htmls


@pytest.mark.parametrize("host", ["api.comebackgolf.com", "api.antiguo.example", None])
@pytest.mark.asyncio
async def test_un_correo_a_otra_persona_lleva_al_sitio_principal(dos_sitios, host):
    """
    Given: Los dos sitios, el viejo el principal, y quien invita actúa desde cualquiera (S10)
    When: Se manda una invitación o una solicitud de amistad
    Then: Lleva al principal: quien invita no decide por dónde entra el invitado
    """
    _llega_por(host)

    for nombre, html in (await _correos_a_otra_persona()).items():
        assert _sitios_de(html) == {VIEJO}, nombre


def test_el_enlace_de_restablecer_sale_del_mismo_sitio(dos_sitios):
    """
    Given: Una petición de restablecer la contraseña por el sitio nuevo (S8)
    When: La raíz de composición arma el caso de uso, que es quien escribe ese enlace
    Then: Recibe la dirección del sitio nuevo
    """
    marca = _llega_por("api.comebackgolf.com")
    try:
        caso = get_request_password_reset_use_case(
            uow=object(), email_service=object(), security_audit=object()
        )
    finally:
        _host_de_la_peticion.reset(marca)

    assert caso._frontend_url == NUEVO


@pytest.mark.parametrize(
    ("configurado", "sale"),
    [
        (f"{NUEVO}/", NUEVO),  # sin la barra final: los enlaces la ponen
        (f" {VIEJO} , {NUEVO} ", VIEJO),
        ("", ""),
    ],
)
def test_la_direccion_sale_limpia(monkeypatch, configurado, sale):
    """
    Given: FRONTEND_URL con barra final, con espacios o vacía
    When: Se pide la dirección del front
    Then: Sale sin barra final, la primera, o vacía si no hay ninguna
    """
    monkeypatch.delenv("COOKIE_DOMAIN", raising=False)

    assert web_de_la_peticion(configurado) == sale


def _luminancia(color):
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def _contraste(letra, fondo):
    clara, oscura = sorted((_luminancia(letra), _luminancia(fondo)), reverse=True)
    return (clara + 0.05) / (oscura + 0.05)


@pytest.mark.parametrize(
    ("letra", "fondo", "que"),
    [
        (email_layout.TITULAR, email_layout.ARENA, "el título sobre la tarjeta"),
        (email_layout.TEXTO, email_layout.ARENA, "el texto sobre la tarjeta"),
        (email_layout.APAGADO, email_layout.ARENA, "el texto pequeño sobre la tarjeta"),
        (email_layout.BOSQUE, email_layout.ARENA, "la etiqueta y el enlace de respaldo"),
        (email_layout.APAGADO, email_layout.FONDO, "el pie sobre la página"),
        (email_layout.TITULAR, email_layout.FONDO, "el título del recuadro"),
        (email_layout.TEXTO, email_layout.FONDO, "las líneas del recuadro"),
        (email_layout.BOSQUE_PROFUNDO, email_layout.LIMA, "el botón principal"),
        (email_layout.TITULAR, email_layout.SALVIA, "el nombre si la cabecera no carga"),
        (email_layout.AVISO_LETRA, email_layout.AVISO_FONDO, "el aviso"),
        (email_layout.BOSQUE_PROFUNDO, email_layout.SALVIA, "el botón secundario"),
        # En oscuro, con los colores de la app
        (email_layout.OSCURO_TINTA, email_layout.OSCURO_TARJETA, "oscuro: el título"),
        (email_layout.OSCURO_TEXTO, email_layout.OSCURO_TARJETA, "oscuro: el texto"),
        (email_layout.OSCURO_APAGADO, email_layout.OSCURO_TARJETA, "oscuro: el texto pequeño"),
        (email_layout.OSCURO_APAGADO, email_layout.OSCURO_FONDO, "oscuro: el pie"),
        (email_layout.LIMA, email_layout.OSCURO_TARJETA, "oscuro: la etiqueta y el enlace"),
        (email_layout.OSCURO_TINTA, email_layout.OSCURO_REALCE, "oscuro: recuadro y secundario"),
        (email_layout.OSCURO_TEXTO, email_layout.OSCURO_REALCE, "oscuro: líneas del recuadro"),
        (email_layout.LIMA, email_layout.OSCURO_REALCE, "oscuro: el nombre sin imagen"),
        (
            email_layout.OSCURO_AVISO_LETRA,
            email_layout.OSCURO_AVISO_FONDO,
            "oscuro: el aviso",
        ),
    ],
)
def test_cada_letra_se_lee_sobre_su_fondo(letra, fondo, que):
    """
    Given: Cada pareja de letra y fondo de la plantilla (D5)
    When: Se calcula su contraste
    Then: Llega a AA para texto normal (4,5), también el pequeño
    """
    assert _contraste(letra, fondo) >= 4.5, (que, round(_contraste(letra, fondo), 2))
