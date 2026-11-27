"""
El dominio de las cookies, según por dónde llega la petición.

El front lee la cookie de CSRF desde `www`, así que las cookies se emiten para el
dominio entero (`.antiguo.example`). Para servir la misma API por un segundo
dominio (`api.comebackgolf.com`), el dominio deja de ser un valor fijo: se ELIGE,
entre los de `COOKIE_DOMAIN`, el que corresponde al `Host` de la petición. Nunca se
construye a partir del `Host`.

    #   COOKIE_DOMAIN            | Host                                 | dominio
    ----|--------------------------|--------------------------------------|----------------
    D1  uno                      | api.antiguo.example              | el de hoy
    D2  dos                      | api.antiguo.example              | .antiguo.example
    D3  dos                      | api.comebackgolf.com                 | .comebackgolf.com
    D4  dos                      | desconocido (onrender.com, una IP)   | el primero
    D5  dos                      | que solo se parece                   | el primero
    D6  dos                      | con puerto, en mayúsculas, con punto | se normaliza
    D7  vacío (local, Kind)      | cualquiera                           | ninguno
    D8  con espacios y huecos    | —                                    | se ignoran
    D9  login por el nuevo       | las cuatro cookies                   | .comebackgolf.com
    D10 logout por el nuevo      | se borran las tres de la sesión      | .comebackgolf.com
    D11 la pondría un middleware al volver (hoy ninguno lo hace)        | el mismo
    D14 la aplicación de verdad, por el host nuevo                      | .comebackgolf.com
    D15 un Host con otra cosa dentro (barra, arroba, IPv6...)           | el primero
    D16 un dominio y un subdominio suyo en la lista                     | el más específico
    D12 dos peticiones a la vez, una por dominio                        | cada una el suyo
    D13 fuera de una petición (un job)                                  | el primero
"""

import asyncio

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.shared.infrastructure.http.dominio_de_las_cookies import (
    DominioDeLasCookies,
    dominio_para,
    dominios_permitidos,
)
from src.shared.infrastructure.security.cookie_handler import (
    delete_auth_cookie,
    delete_csrf_cookie,
    delete_refresh_token_cookie,
    get_cookie_domain,
    set_auth_cookie,
    set_csrf_cookie,
    set_device_id_cookie,
    set_refresh_token_cookie,
)

DE_HOY = ".antiguo.example"
NUEVO = ".comebackgolf.com"
LOS_DOS = [DE_HOY, NUEVO]
LAS_CUATRO = ["access_token", "refresh_token", "csrf_token", "device_id"]


# ----------------------------------------------------------------------------
# La regla, sola
# ----------------------------------------------------------------------------


def test_d1_un_solo_dominio_es_el_de_hoy():
    """
    Given: COOKIE_DOMAIN con un solo dominio
    When: Llega una petición por el host de siempre
    Then: Ese dominio, como hasta ahora
    """
    assert dominio_para("api.antiguo.example", [DE_HOY]) == DE_HOY


def test_d2_con_dos_el_host_de_siempre_recibe_el_de_siempre():
    """
    Given: Dos dominios configurados
    When: Llega una petición por api.antiguo.example
    Then: El de siempre: producción no cambia
    """
    assert dominio_para("api.antiguo.example", LOS_DOS) == DE_HOY


def test_d3_el_host_nuevo_recibe_el_dominio_nuevo():
    """
    Given: Dos dominios configurados
    When: Llega una petición por api.comebackgolf.com
    Then: El dominio nuevo
    """
    assert dominio_para("api.comebackgolf.com", LOS_DOS) == NUEVO


@pytest.mark.parametrize(
    "host",
    ["comebackgolf-api.onrender.com", "10.244.0.12", "localhost", "", None],
)
def test_d4_un_host_desconocido_recibe_el_primero(host):
    """
    Given: Dos dominios configurados
    When: El Host no es de ninguno (el de onrender.com, una IP, vacío)
    Then: El primero de la lista, sea cual sea
    """
    assert dominio_para(host, LOS_DOS) == DE_HOY
    # Y el primero es el primero de la lista, no uno fijo
    assert dominio_para(host, [NUEVO, DE_HOY]) == NUEVO


@pytest.mark.parametrize(
    "host",
    [
        "api.comebackgolf.com.atacante.net",
        "malocomebackgolf.com",
        "comebackgolf.com.es",
        "api-comebackgolf.com",
        "comebackgolf.comx",
    ],
)
def test_d5_un_host_que_solo_se_parece_no_encaja(host):
    """
    Given: Dos dominios configurados
    When: El Host solo se parece a uno de ellos
    Then: No encaja: recibe el primero
    """
    assert dominio_para(host, LOS_DOS) == DE_HOY


@pytest.mark.parametrize(
    "host",
    [
        "api.comebackgolf.com:443",
        "API.ComeBackGolf.COM",
        "api.comebackgolf.com.",
        "comebackgolf.com",
        "www.comebackgolf.com",
        " api.comebackgolf.com ",
    ],
)
def test_d6_el_host_se_normaliza_antes_de_comparar(host):
    """
    Given: Dos dominios configurados
    When: El Host llega con puerto, en mayúsculas, con punto final o con espacios
    Then: Encaja igual con el suyo
    """
    assert dominio_para(host, LOS_DOS) == NUEVO


def test_d6_lo_devuelto_es_el_de_la_lista_no_el_host():
    """
    Given: Un Host en mayúsculas y con puerto
    When: Se elige su dominio
    Then: Sale el valor configurado, el mismo objeto: nunca se construye con el Host
    """
    assert dominio_para("API.ComeBackGolf.COM:8443", LOS_DOS) is LOS_DOS[1]


@pytest.mark.parametrize(
    "lista",
    [
        [".ejemplo.com", ".pruebas.ejemplo.com"],
        [".pruebas.ejemplo.com", ".ejemplo.com"],
    ],
)
def test_d16_de_dos_que_encajan_gana_el_mas_especifico(lista):
    """
    Given: Un dominio y un subdominio suyo en la lista, en cualquier orden
    When: Llega una petición por un host del subdominio, y otra por uno del padre
    Then: Cada una recibe el más específico de los suyos. Con el padre, las cookies de
          pruebas irían también a la API de producción y pisarían las suyas
    """
    assert dominio_para("api.pruebas.ejemplo.com", lista) == ".pruebas.ejemplo.com"
    assert dominio_para("api.ejemplo.com", lista) == ".ejemplo.com"


@pytest.mark.parametrize("host", ["api.comebackgolf.com", "localhost", None])
def test_d7_sin_dominios_configurados_no_hay_dominio(host):
    """
    Given: COOKIE_DOMAIN vacío (local, Kind)
    When: Llega una petición por cualquier host
    Then: Sin dominio
    """
    assert dominio_para(host, []) is None


@pytest.mark.parametrize(
    ("valor", "esperados"),
    [
        (None, []),
        ("", []),
        ("   ", []),
        (DE_HOY, [DE_HOY]),
        (f"{DE_HOY},{NUEVO}", LOS_DOS),
        (f" {DE_HOY} , , {NUEVO} ,", LOS_DOS),
        (f"{DE_HOY},{DE_HOY}", [DE_HOY]),
    ],
)
def test_d8_la_lista_ignora_espacios_huecos_y_repetidos(monkeypatch, valor, esperados):
    """
    Given: COOKIE_DOMAIN con espacios, huecos o repetidos
    When: Se lee la lista
    Then: Solo los dominios, una vez cada uno y en su orden
    """
    if valor is None:
        monkeypatch.delenv("COOKIE_DOMAIN", raising=False)
    else:
        monkeypatch.setenv("COOKIE_DOMAIN", valor)

    assert dominios_permitidos() == esperados


# ----------------------------------------------------------------------------
# Con peticiones de verdad
# ----------------------------------------------------------------------------


class _RotaElCsrf(BaseHTTPMiddleware):
    """
    Un middleware que pone una cookie al volver, fuera del endpoint. Hoy no hay ninguno
    (las cookies las ponen solo las rutas); es la razón de que el del dominio vaya por
    fuera de los demás.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path == "/rota":
            set_csrf_cookie(response, "csrf-rotado")
        return response


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/entra")
    def entra(response: Response):
        set_auth_cookie(response, "acceso")
        set_refresh_token_cookie(response, "refresco")
        set_csrf_cookie(response, "csrf")
        set_device_id_cookie(response, "dispositivo")
        return {}

    @app.post("/sale")
    async def sale(response: Response):
        delete_auth_cookie(response)
        delete_refresh_token_cookie(response)
        delete_csrf_cookie(response)
        return {}

    @app.get("/rota")
    def rota():
        return {}

    @app.get("/lento")
    async def lento(response: Response):
        # Cede el turno: la otra petición entra por el otro dominio mientras tanto
        await asyncio.sleep(0.05)
        set_auth_cookie(response, "acceso")
        return {}

    app.add_middleware(_RotaElCsrf)
    app.add_middleware(DominioDeLasCookies)
    return app


def _dominios(response) -> dict[str, str | None]:
    """De cada cookie de la respuesta, el Domain con el que salió."""
    salida: dict[str, str | None] = {}
    for cabecera in response.headers.get_list("set-cookie"):
        nombre = cabecera.split("=", 1)[0]
        dominio = next(
            (
                trozo.split("=", 1)[1]
                for trozo in cabecera.split("; ")
                if trozo.lower().startswith("domain=")
            ),
            None,
        )
        salida[nombre] = dominio
    return salida


@pytest.fixture
def dos_dominios(monkeypatch):
    monkeypatch.setenv("COOKIE_DOMAIN", f"{DE_HOY},{NUEVO}")


@pytest.mark.parametrize(
    ("host", "dominio"),
    [
        ("api.comebackgolf.com", NUEVO),
        ("api.antiguo.example", DE_HOY),
        ("comebackgolf-api.onrender.com", DE_HOY),
    ],
)
def test_d9_al_entrar_las_cuatro_cookies_llevan_el_dominio_del_host(dos_dominios, host, dominio):
    """
    Given: Dos dominios configurados
    When: Se entra por cada host
    Then: Las cuatro cookies salen con el dominio de ese host
    """
    respuesta = TestClient(_app(), base_url=f"https://{host}").post("/entra")

    assert _dominios(respuesta) == dict.fromkeys(LAS_CUATRO, dominio)


@pytest.mark.parametrize(
    ("host", "dominio"),
    [("api.comebackgolf.com", NUEVO), ("api.antiguo.example", DE_HOY)],
)
def test_d10_al_salir_las_de_la_sesion_se_borran_con_el_dominio_del_host(
    dos_dominios, host, dominio
):
    """
    Given: Dos dominios configurados
    When: Se sale por cada host
    Then: Las tres de la sesión se borran con el dominio de ese host; con otro el navegador no las borraría. La del dispositivo dura un año y no se borra al salir
    """
    respuesta = TestClient(_app(), base_url=f"https://{host}").post("/sale")

    assert _dominios(respuesta) == dict.fromkeys(LAS_CUATRO[:3], dominio)


def test_d11_la_cookie_que_pone_un_middleware_lleva_el_mismo_dominio(dos_dominios):
    """
    Given: Un middleware que pone una cookie al volver
    When: Llega una petición por el host nuevo
    Then: Esa cookie lleva también el dominio nuevo
    """
    respuesta = TestClient(_app(), base_url="https://api.comebackgolf.com").get("/rota")

    assert _dominios(respuesta) == {"csrf_token": NUEVO}


async def test_d12_dos_peticiones_a_la_vez_no_se_cruzan(dos_dominios):
    """
    Given: Veinte peticiones a la vez, la mitad por cada host
    When: Cada una pone su cookie tras ceder el turno
    Then: Cada una recibe el dominio de su host
    """
    app = _app()

    async def pide(host: str) -> dict[str, str | None]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=f"https://{host}"
        ) as cliente:
            return _dominios(await cliente.get("/lento"))

    hosts = ["api.comebackgolf.com", "api.antiguo.example"] * 10
    resultados = await asyncio.gather(*(pide(h) for h in hosts))

    assert resultados == [{"access_token": NUEVO if "comeback" in h else DE_HOY} for h in hosts]


def test_d13_fuera_de_una_peticion_es_el_primero(dos_dominios):
    """
    Given: Dos dominios configurados
    When: Se pregunta el dominio fuera de una petición (un job)
    Then: El primero
    """
    assert get_cookie_domain() == DE_HOY


async def test_d13_tras_una_peticion_no_queda_su_dominio_puesto(dos_dominios):
    """
    El dominio de una petición no se le queda a lo que venga después en la misma
    tarea. Se llama al middleware a mano: con un cliente de pruebas la petición corre
    en otra tarea y el contexto no vuelve, se quite o no.
    """
    dentro: list[str | None] = []

    async def aplicacion(scope, receive, send):
        dentro.append(get_cookie_domain())

    scope = {"type": "http", "headers": [(b"host", b"api.comebackgolf.com")]}
    await DominioDeLasCookies(aplicacion)(scope, None, None)

    assert dentro == [NUEVO]
    assert get_cookie_domain() == DE_HOY


async def test_d13_tampoco_si_la_peticion_revienta(dos_dominios):
    """
    Given: Una petición por el host nuevo
    When: La aplicación lanza una excepción
    Then: Su dominio no se queda puesto para lo que venga después
    """

    async def aplicacion(scope, receive, send):
        raise RuntimeError("revienta")

    scope = {"type": "http", "headers": [(b"host", b"api.comebackgolf.com")]}
    with pytest.raises(RuntimeError):
        await DominioDeLasCookies(aplicacion)(scope, None, None)

    assert get_cookie_domain() == DE_HOY


async def test_lo_que_no_es_http_pasa_sin_tocar(dos_dominios):
    """El arranque (`lifespan`) no trae cabeceras: pasa tal cual."""
    visto: list[str] = []

    async def aplicacion(scope, receive, send):
        visto.append(scope["type"])

    await DominioDeLasCookies(aplicacion)({"type": "lifespan"}, None, None)

    assert visto == ["lifespan"]


def test_d7_sin_configurar_las_cookies_salen_sin_dominio(monkeypatch):
    """
    Given: COOKIE_DOMAIN sin definir
    When: Se entra por cualquier host
    Then: Las cuatro cookies salen sin atributo Domain
    """
    monkeypatch.delenv("COOKIE_DOMAIN", raising=False)

    respuesta = TestClient(_app(), base_url="https://api.comebackgolf.com").post("/entra")

    assert _dominios(respuesta) == dict.fromkeys(LAS_CUATRO)


@pytest.mark.parametrize(
    "host",
    [
        "evil.com/.comebackgolf.com",
        "evil.com#.comebackgolf.com",
        "x@api.comebackgolf.com",
        "api.comebackgolf.com:evil:443",
        "evil.com .comebackgolf.com",
        "[::1]",
        "[::1]:8000",
        "api.comebackgolf.com\x00",
        "ápi.comebackgolf.com",
        "-.comebackgolf.com",
    ],
)
def test_d15_un_host_con_otra_cosa_dentro_no_se_compara(host):
    """Aunque acabe como uno de la lista: solo vale un nombre de host de verdad."""
    assert dominio_para(host, LOS_DOS) == DE_HOY


@pytest.mark.parametrize(
    "cabeceras",
    [
        [],
        [(b"host", b"")],
        [(b"host", b"\xff\xfe.comebackgolf.com")],
        [(b"host", b"api.antiguo.example"), (b"host", b"api.comebackgolf.com")],
    ],
)
async def test_d15_sin_host_repetido_o_con_bytes_raros_no_revienta(dos_dominios, cabeceras):
    """Ausente, vacío, con bytes que no son ASCII o repetido (manda el primero)."""
    dentro: list[str | None] = []

    async def aplicacion(scope, receive, send):
        dentro.append(get_cookie_domain())

    await DominioDeLasCookies(aplicacion)({"type": "http", "headers": cabeceras}, None, None)

    assert dentro == [DE_HOY]


@pytest.mark.parametrize(
    ("host", "dominio"),
    [("api.comebackgolf.com", NUEVO), ("api.antiguo.example", DE_HOY)],
)
def test_d14_la_aplicacion_de_verdad_borra_la_cookie_con_el_dominio_del_host(
    dos_dominios, host, dominio
):
    """
    Given: La aplicación real, con toda su pila de middlewares
    When: Un refresco con una cookie que no vale, por cada host
    Then: El 401 borra la cookie (sobre una respuesta hecha a mano) con el dominio de
          ese host. Es la única prueba que cubre a la vez que el middleware está
          registrado, la pila real y una respuesta que no es la del endpoint
    """
    from main import app

    cliente = TestClient(app, base_url=f"https://{host}")
    cliente.cookies.set("refresh_token", "no-vale")

    respuesta = cliente.post("/api/v1/auth/refresh-token")

    assert respuesta.status_code == 401
    assert _dominios(respuesta) == {"refresh_token": dominio}


def test_la_aplicacion_lleva_el_middleware_registrado():
    """
    Given: La aplicación real
    When: Se miran sus middlewares
    Then: El del dominio de las cookies está registrado
    """
    from main import app

    assert DominioDeLasCookies in [m.cls for m in app.user_middleware]
