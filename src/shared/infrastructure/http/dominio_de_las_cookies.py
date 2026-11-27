"""
El dominio de las cookies, según por dónde llega la petición (ADR-054).

El front lee la cookie de CSRF desde `www` (double-submit), así que las cookies se
emiten para el dominio entero (`Domain=.comebackgolf.com`) y no solo para `api`.
Con un valor fijo la API solo podía servirse por un dominio: por un segundo
(`api.comebackgolf.com`) el navegador rechazaba las cookies, que nombraban otro.

`COOKIE_DOMAIN` es ahora una lista, y de ella se ELIGE el dominio al que pertenece el
`Host` de la petición. Nunca se construye a partir del `Host`: lo que no encaja con
ninguno recibe el primero, que es el de siempre. Un `Host` falsificado no gana nada:
solo puede hacer que la respuesta nombre otro dominio de la lista, y el navegador
descarta una cookie cuyo `Domain` no es el del sitio que la envía.

El `Host` se guarda en una variable de contexto mientras dura la petición, porque las
funciones que ponen y borran cookies solo reciben la respuesta. La pone un middleware
ASGI puro. Hoy las cookies las ponen solo las rutas; va por fuera de todos los
registrados con `add_middleware`, para que uno que mañana escriba la suya al volver
también la vea. Los dos de `@app.middleware` (cabeceras de seguridad y depuración) lo
envuelven a él: una cookie escrita ahí recibiría el dominio por defecto. Cada petición
tiene la suya aunque coincidan en el tiempo.
"""

import re
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from src.config.arranque_seguro import dominios_de_cookie, en_lista

_NOMBRE_DE_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")

_host_de_la_peticion: ContextVar[str | None] = ContextVar("host_de_la_peticion", default=None)


def dominios_permitidos() -> list[str]:
    """Los de `COOKIE_DOMAIN`, ya validados al arrancar (`arranque_seguro`)."""
    return dominios_de_cookie()


def dominio_para(host: str | None, permitidos: list[str]) -> str | None:
    """
    El dominio de cookie que corresponde a un `Host`.

    Args:
        host: La cabecera Host tal como llegó (con puerto, en mayúsculas...), o nada
        permitidos: Los dominios configurados, el de por defecto el primero

    Returns:
        El de la lista al que pertenece el host; el primero si no pertenece a
        ninguno; None si no hay ninguno configurado
    """
    if not permitidos:
        return None
    # El más específico de los que encajan, no el primero: con `.ejemplo.com` y
    # `.pruebas.ejemplo.com` en la lista, `api.pruebas.ejemplo.com` es del segundo. Con el
    # primero sus cookies irían también a la API del dominio padre y pisarían las suyas
    suyos = [d for d in permitidos if _es_del_dominio(host, d)]
    if suyos:
        return max(suyos, key=lambda d: len(d.strip().lstrip(".")))
    return permitidos[0]


def _es_del_dominio(host: str | None, dominio: str) -> bool:
    """Si ese host es el dominio o uno de sus subdominios."""
    nombre = _sin_puerto(host or "").strip().rstrip(".").lower()
    # Solo un nombre de host de verdad: con otra cosa dentro (una barra, una arroba,
    # un segundo puerto) no se compara nada, aunque acabe como uno de la lista
    if not _NOMBRE_DE_HOST.fullmatch(nombre):
        return False
    raiz = dominio.strip().lstrip(".").lower()
    return bool(raiz) and (nombre == raiz or nombre.endswith(f".{raiz}"))


def dominio_de_la_peticion() -> str | None:
    """El dominio de cookie de la petición en curso; fuera de una, el de por defecto."""
    return dominio_para(_host_de_la_peticion.get(), dominios_permitidos())


def url_del_sitio_de_la_peticion(urls: list[str]) -> str | None:
    """
    De varias URLs de front, la del sitio por el que llegó la petición.

    Para lo que tiene una por front, como el retorno de Google: se elige la que está
    bajo el dominio de cookie de la petición. Tampoco sale del `Host`.

    Args:
        urls: Las configuradas, una por front

    Returns:
        La que cuelga del dominio de la petición; la primera si ninguna lo hace o no
        hay dominios configurados; None si la lista está vacía
    """
    if not urls:
        return None
    permitidos = dominios_permitidos()
    dominio = dominio_para(_host_de_la_peticion.get(), permitidos)
    if dominio:
        for url in urls:
            # El dominio de la URL se decide como el de la petición: el más específico
            # de los suyos. Con solo «cuelga del dominio», la de un subdominio listado
            # (pruebas) valía también para el padre y, puesta la primera, se la llevaba
            host = _host_de_la_url(url)
            if _es_del_dominio(host, dominio) and dominio_para(host, permitidos) == dominio:
                return url
    return urls[0]


def web_de_la_peticion(direcciones: str) -> str:
    """
    La dirección del front desde el que actúa quien hizo la petición (ADR-055).

    De ella salen los enlaces de los correos sobre la propia cuenta: quien pide
    restablecer la contraseña en un sitio recibe el enlace a ese sitio, no al otro,
    donde su sesión y su aplicación instalada no están. Se elige de la lista
    configurada, nunca se construye con el `Host`: una cabecera falsificada no puede
    llevar un enlace con token a un dominio ajeno.

    Args:
        direcciones: `FRONTEND_URL` tal cual: una dirección o varias separadas por comas,
            la principal la primera

    Returns:
        La del sitio de la petición, sin barra final; la principal si no hay petición
        (avisos programados) o el `Host` no es de ningún sitio; cadena vacía si no hay
        ninguna
    """
    urls = en_lista(direcciones)
    host = _host_de_la_peticion.get()
    # Solo si el Host es de verdad de uno de los sitios. Si no, la principal es la
    # primera de ESTA lista, no la del primer dominio de cookie: el día del cambio se
    # le da la vuelta a `FRONTEND_URL` y nada más
    if not any(_es_del_dominio(host, d) for d in dominios_permitidos()):
        return web_principal(direcciones)
    return (url_del_sitio_de_la_peticion(urls) or "").rstrip("/")


def web_principal(direcciones: str) -> str:
    """
    La dirección principal del front: la primera de `FRONTEND_URL` (ADR-055).

    Para los correos que recibe otra persona (una invitación, una solicitud de amistad)
    y los que no nacen de una petición: su destinatario no tiene por qué usar el sitio
    de quien los provocó.

    Args:
        direcciones: `FRONTEND_URL` tal cual

    Returns:
        La primera, sin barra final; cadena vacía si no hay ninguna
    """
    urls = en_lista(direcciones)
    return urls[0].rstrip("/") if urls else ""


def _host_de_la_url(url: str) -> str | None:
    """El host de una URL, o nada si no se deja leer (en desarrollo no se valida)."""
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _sin_puerto(host: str) -> str:
    """`api.ejemplo.com:443` → `api.ejemplo.com`. Una IPv6 entre corchetes no encaja con nada."""
    return host.rsplit(":", 1)[0]


class DominioDeLasCookies:
    """Middleware ASGI: recuerda el Host de la petición mientras dura."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Args:
            app: La aplicación envuelta
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pone el Host en el contexto y lo quita al acabar, pase lo que pase."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        marca = _host_de_la_peticion.set(_host(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            _host_de_la_peticion.reset(marca)


def _host(scope: Scope) -> str | None:
    """La cabecera Host del scope, o nada."""
    for nombre, valor in scope.get("headers", []):
        if nombre == b"host":
            return valor.decode("latin-1")
    return None
