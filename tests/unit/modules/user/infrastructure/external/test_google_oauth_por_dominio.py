"""
La dirección de retorno de Google, según el sitio desde el que se entra (ADR-054).

Google rechaza el canje del código si la `redirect_uri` no es la misma con la que el
front lo pidió. Con la API servida por dos dominios hay dos fronts, cada uno con la
suya, así que `GOOGLE_REDIRECT_URI` es una lista y se ELIGE la del sitio de la petición,
igual que el dominio de las cookies. Nunca se construye a partir del Host.

    #   GOOGLE_REDIRECT_URI | la petición llega por        | redirect_uri que va a Google
    ----|---------------------|------------------------------|------------------------------
    G1  una                 | cualquier host               | esa, como hasta ahora
    G2  dos                 | api.antiguo.example      | la de www.antiguo.example
    G3  dos                 | api.comebackgolf.com         | la de www.comebackgolf.com
    G4  dos                 | un host desconocido          | la del dominio por defecto
    G5  dos, y ninguna es del dominio de la petición         | la primera
    G6  sin COOKIE_DOMAIN (local, Kind)                      | la primera
    G7  con espacios y huecos en la lista                    | se ignoran
    G8  fuera de una petición                                | la del dominio por defecto
    G10 dominio y subdominio en COOKIE_DOMAIN, un retorno por front  | la de cada front
    G9  una entrada que no es una URL http(s) con host       | no arranca (fuera de
                                                             | desarrollo), sin el valor
                                                             | en el mensaje
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.arranque_seguro import comprueba_la_configuracion_de_seguridad
from src.config.settings import settings
from src.modules.user.infrastructure.external.google_oauth_service import (
    HTTP_OK,
    GoogleOAuthService,
)
from src.shared.infrastructure.http.dominio_de_las_cookies import (
    DominioDeLasCookies,
    url_del_sitio_de_la_peticion,
)

VIEJA = "https://www.antiguo.example/auth/google/callback"
NUEVA = "https://www.comebackgolf.com/auth/google/callback"
LAS_DOS = f"{VIEJA},{NUEVA}"
DOMINIOS = ".antiguo.example,.comebackgolf.com"
CLIENTE = "src.modules.user.infrastructure.external.google_oauth_service.httpx.AsyncClient"


def _cliente() -> AsyncMock:
    """Un httpx falso: token y userinfo buenos."""
    token = MagicMock(status_code=HTTP_OK, text="{}")
    token.json.return_value = {"access_token": "ya29.token"}
    userinfo = MagicMock(status_code=HTTP_OK)
    userinfo.json.return_value = {
        "sub": "google-1",
        "email": "ana@gmail.com",
        "email_verified": True,
        "given_name": "Ana",
        "family_name": "Lopez",
    }
    cliente = AsyncMock()
    cliente.post.return_value = token
    cliente.get.return_value = userinfo
    cliente.__aenter__ = AsyncMock(return_value=cliente)
    cliente.__aexit__ = AsyncMock(return_value=None)
    return cliente


async def _redirect_que_va_a_google(host: str | None) -> str:
    """Canjea un código llegando por ese host y devuelve la redirect_uri enviada."""
    cliente = _cliente()

    async def aplicacion(scope, receive, send):
        with patch(CLIENTE, return_value=cliente):
            await GoogleOAuthService().exchange_code_for_user_info("code", "v" * 43)

    if host is None:
        await aplicacion({}, None, None)
    else:
        scope = {"type": "http", "headers": [(b"host", host.encode())]}
        await DominioDeLasCookies(aplicacion)(scope, None, None)
    return cliente.post.call_args.kwargs["data"]["redirect_uri"]


@pytest.fixture
def configura(monkeypatch):
    def _configura(retornos: str, dominios: str | None = DOMINIOS) -> None:
        monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", retornos)
        if dominios is None:
            monkeypatch.delenv("COOKIE_DOMAIN", raising=False)
        else:
            monkeypatch.setenv("COOKIE_DOMAIN", dominios)

    return _configura


@pytest.mark.parametrize("host", ["api.antiguo.example", "api.comebackgolf.com", "localhost:8000"])
async def test_g1_con_una_sola_va_esa_por_cualquier_host(configura, host):
    """
    Given: GOOGLE_REDIRECT_URI con una sola dirección
    When: Se canjea un código por cualquier host
    Then: Va esa, como hasta ahora
    """
    configura(VIEJA)

    assert await _redirect_que_va_a_google(host) == VIEJA


async def test_g2_por_el_host_de_siempre_va_la_de_siempre(configura):
    """
    Given: Dos direcciones de retorno
    When: Se canjea por api.antiguo.example
    Then: Va la de www.antiguo.example
    """
    configura(LAS_DOS)

    assert await _redirect_que_va_a_google("api.antiguo.example") == VIEJA


async def test_g3_por_el_host_nuevo_va_la_del_sitio_nuevo(configura):
    """
    Given: Dos direcciones de retorno
    When: Se canjea por api.comebackgolf.com
    Then: Va la de www.comebackgolf.com
    """
    configura(LAS_DOS)

    assert await _redirect_que_va_a_google("api.comebackgolf.com") == NUEVA


async def test_g3_no_depende_del_orden_de_la_lista(configura):
    """
    Given: Las dos direcciones en el orden contrario
    When: Se canjea por cada host
    Then: Cada uno recibe la de su sitio
    """
    configura(f"{NUEVA},{VIEJA}")

    assert await _redirect_que_va_a_google("api.comebackgolf.com") == NUEVA
    assert await _redirect_que_va_a_google("api.antiguo.example") == VIEJA


@pytest.mark.parametrize(
    "host", ["comebackgolf-api.onrender.com", "10.0.0.1", "api.comebackgolf.com.atacante.net"]
)
async def test_g4_por_un_host_desconocido_va_la_del_dominio_por_defecto(configura, host):
    """
    Given: Dos direcciones, la nueva primero
    When: Se canjea por un host que no es de ningún dominio
    Then: Va la del dominio por defecto, que es el primero de COOKIE_DOMAIN y no la primera URL
    """
    configura(f"{NUEVA},{VIEJA}")

    assert await _redirect_que_va_a_google(host) == VIEJA


@pytest.mark.parametrize(
    "retornos",
    [
        "https://www.pruebas.ejemplo.com/cb,https://www.ejemplo.com/cb",
        "https://www.ejemplo.com/cb,https://www.pruebas.ejemplo.com/cb",
    ],
)
async def test_g10_con_un_dominio_y_un_subdominio_cada_front_recibe_la_suya(configura, retornos):
    """
    Given: Un dominio y un subdominio suyo en COOKIE_DOMAIN, y un retorno por cada
           front, en cualquier orden
    When: Se canjea por la API del padre y por la del subdominio
    Then: Cada una manda la de su front. La del subdominio también «cuelga» del padre:
          puesta la primera, se la llevaba la petición del padre y Google rechazaba el
          canje (CodeRabbit en BE #934)
    """
    configura(retornos, dominios=".ejemplo.com,.pruebas.ejemplo.com")

    assert await _redirect_que_va_a_google("api.ejemplo.com") == "https://www.ejemplo.com/cb"
    assert (
        await _redirect_que_va_a_google("api.pruebas.ejemplo.com")
        == "https://www.pruebas.ejemplo.com/cb"
    )


async def test_g5_si_ninguna_es_del_dominio_va_la_primera(configura):
    """
    Given: Direcciones que no cuelgan de ningún dominio de cookie
    When: Se canjea un código
    Then: Va la primera
    """
    configura("https://app.otro.com/cb,https://app.otro.net/cb")

    assert await _redirect_que_va_a_google("api.comebackgolf.com") == "https://app.otro.com/cb"


@pytest.mark.parametrize("host", ["localhost:8000", "api.comebackgolf.com"])
async def test_g6_sin_dominios_de_cookie_va_la_primera(configura, host):
    """
    Given: Sin COOKIE_DOMAIN (local, Kind)
    When: Se canjea por cualquier host
    Then: Va la primera
    """
    configura(f"http://localhost:5173/auth/google/callback,{NUEVA}", dominios=None)

    assert await _redirect_que_va_a_google(host) == "http://localhost:5173/auth/google/callback"


async def test_g7_la_lista_ignora_espacios_y_huecos(configura):
    """
    Given: La lista con espacios y huecos
    When: Se canjea por el host nuevo
    Then: Va la del sitio nuevo, limpia
    """
    configura(f" {VIEJA} , , {NUEVA} ,")

    assert await _redirect_que_va_a_google("api.comebackgolf.com") == NUEVA


async def test_g8_fuera_de_una_peticion_va_la_del_dominio_por_defecto(configura):
    """
    Given: Dos direcciones
    When: Se canjea fuera de una petición
    Then: Va la del dominio por defecto
    """
    configura(f"{NUEVA},{VIEJA}")

    assert await _redirect_que_va_a_google(None) == VIEJA


def test_la_que_se_devuelve_es_la_de_la_lista_tal_cual(monkeypatch):
    """
    Given: Una lista de direcciones
    When: Se elige la del sitio
    Then: Sale el valor configurado, el mismo objeto; con la lista vacía, nada
    """
    monkeypatch.setenv("COOKIE_DOMAIN", DOMINIOS)
    urls = [VIEJA, NUEVA]

    assert url_del_sitio_de_la_peticion(urls) is urls[0]
    assert url_del_sitio_de_la_peticion([]) is None


PRODUCCION = {"ENVIRONMENT": "production", "SECRET_KEY": "k" * 48}


@pytest.mark.parametrize(
    "valor",
    [
        "www.comebackgolf.com/auth/google/callback",
        "ftp://www.comebackgolf.com/cb",
        "javascript:alert(1)",
        "https:///auth/google/callback",
        f"{VIEJA};{NUEVA}",
        f"{VIEJA} {NUEVA}",
        f"{VIEJA},no-es-una-url",
        "https://usuario:clave@www.comebackgolf.com/cb",
        "https://usuario@www.comebackgolf.com/cb",
        "http://[::1/cb",
    ],
)
def test_g9_una_entrada_que_no_es_una_url_no_deja_arrancar(valor):
    """
    Given: GOOGLE_REDIRECT_URI con una entrada que no es una URL http(s) limpia
    When: Se comprueba la configuración fuera de desarrollo
    Then: RuntimeError: no arranca, y el mensaje no lleva el valor
    """
    with pytest.raises(RuntimeError, match="GOOGLE_REDIRECT_URI") as error:
        comprueba_la_configuracion_de_seguridad({**PRODUCCION, "GOOGLE_REDIRECT_URI": valor})

    assert valor not in str(error.value)


@pytest.mark.parametrize(
    "valor", [None, "", VIEJA, LAS_DOS, "http://localhost:5173/auth/google/callback"]
)
def test_g9_una_lista_buena_arranca(valor):
    """
    Given: GOOGLE_REDIRECT_URI vacío, con una o con varias URLs
    When: Se comprueba la configuración
    Then: Arranca
    """
    entorno = dict(PRODUCCION) if valor is None else {**PRODUCCION, "GOOGLE_REDIRECT_URI": valor}

    comprueba_la_configuracion_de_seguridad(entorno)


def test_g9_en_desarrollo_no_se_comprueba():
    """
    Given: Un desarrollo declarado con la lista mal escrita
    When: Se comprueba la configuración
    Then: Arranca: en local se prueba con lo que haga falta
    """
    comprueba_la_configuracion_de_seguridad(
        {"ENVIRONMENT": "development", "GOOGLE_REDIRECT_URI": "no-es-una-url"}
    )


async def test_g9_una_url_ilegible_en_desarrollo_no_revienta_el_canje(configura):
    """
    Given: En desarrollo (no se valida al arrancar), una entrada que urlsplit no lee
    When: Se canjea un código
    Then: No lanza: esa no encaja y va la primera
    """
    configura(f"{VIEJA},http://[::1/cb")

    assert await _redirect_que_va_a_google("api.comebackgolf.com") == VIEJA
