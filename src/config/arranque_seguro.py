"""
Lo que la app comprueba al arrancar fuera de desarrollo (F-06 y F-12, auditoría OWASP
del 9 nov 2026).

Fuera de un desarrollo declarado (`ENVIRONMENT=development`: local, Kind y los tests)
no arranca con:

- `TESTING=true`: apaga el CSRF de los tests de integración y deja a quien llama
  elegir su red con `X-Test-Client-ID`.
- `SECRET_KEY` vacía, de ejemplo (las que vienen en settings.py, `.env.example`,
  docker y k8s) o de menos de 32 bytes: firma los JWT, el CSRF y los contadores.

Como en `contrasenas.py` y `rate_limit.py`, un ENVIRONMENT ausente o desconocido
cuenta como producción. Y `development` con `RENDER` definida (Render la pone) no
arranca: un desarrollo declarado por error en Render se saltaría todo lo anterior. La comprobación va en el `lifespan` y no al importar: el CI
genera el OpenAPI importando `main` sin ninguna variable (job «API contract»).
"""

import os
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from src.config.migraciones import VARIABLE_DE_LAS_MIGRACIONES

# postgres://, postgresql:// y con driver (postgresql+psycopg2://), como entrypoint.sh
_URL_DE_POSTGRES = re.compile(r"^postgres(ql)?(\+[a-zA-Z0-9_-]+)?://")

ENTORNO_DE_DESARROLLO = "development"
LONGITUD_MINIMA_DE_LA_CLAVE = 32  # bytes: 256 bits para el HMAC-SHA256 de los JWT

# Los valores de ejemplo de los ficheros del repositorio: cualquiera puede leerlos
CLAVES_DE_EJEMPLO = frozenset(
    {
        "your-secret-key-change-in-production",  # settings.py y los .env.example
        "your-secret-key-change-me",  # k8s/api-secret.yaml
        "your_secret_key_here",  # docker/scripts
        "MISSING_SECRET_KEY",  # docker/docker-compose.yml
        "your-super-secret-key-min-32-chars",  # docs
        "your-local-secret-key",  # docs
    }
)


# Un dominio de cookie: con o sin punto inicial, al menos dos etiquetas y sin esquema,
# puerto ni ruta. No sabe de sufijos públicos: `.co.uk` pasa, y el navegador lo descarta
_DOMINIO_DE_COOKIE = re.compile(
    r"^\.?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE
)


def en_desarrollo_declarado(entorno: Mapping[str, str] = os.environ) -> bool:
    """Si ENVIRONMENT dice expresamente `development`; ausente o raro, producción."""
    return (entorno.get("ENVIRONMENT") or "").strip().lower() == ENTORNO_DE_DESARROLLO


def testing_activado(entorno: Mapping[str, str] = os.environ) -> bool:
    """Si TESTING dice `true`, el valor con el que el código cambia de comportamiento."""
    return (entorno.get("TESTING") or "").strip().lower() == "true"


def modo_de_tests(entorno: Mapping[str, str] = os.environ) -> bool:
    """
    La suite de tests: TESTING=true Y ENVIRONMENT=development (ADR-047). Solo así se
    salta el CSRF de los tests de integración y vale X-Test-Client-ID.
    """
    return testing_activado(entorno) and en_desarrollo_declarado(entorno)


def dominios_de_cookie(entorno: Mapping[str, str] = os.environ) -> list[str]:
    """
    Los dominios de `COOKIE_DOMAIN`, separados por comas y en su orden (ADR-054).

    Returns:
        La lista sin huecos ni repetidos; vacía si no hay ninguno (local, Kind)
    """
    return en_lista(entorno.get("COOKIE_DOMAIN"))


def retornos_de_google(entorno: Mapping[str, str] = os.environ) -> list[str]:
    """Las direcciones de retorno de `GOOGLE_REDIRECT_URI`, una por front (ADR-054)."""
    return en_lista(entorno.get("GOOGLE_REDIRECT_URI"))


def direcciones_del_front(entorno: Mapping[str, str] = os.environ) -> list[str]:
    """Las direcciones de `FRONTEND_URL`, una por front y la principal la primera (ADR-055)."""
    return en_lista(entorno.get("FRONTEND_URL"))


def en_lista(valor: str | None) -> list[str]:
    """Un valor separado por comas, sin huecos ni repetidos y en su orden."""
    vistos: list[str] = []
    for trozo in (valor or "").split(","):
        limpio = trozo.strip()
        if limpio and limpio not in vistos:
            vistos.append(limpio)
    return vistos


def _es_una_url_de_front(url: str) -> bool:
    """http(s), con host, sin usuario ni contraseña y sin espacios ni otros separadores."""
    if any(c.isspace() or c == ";" for c in url):
        return False
    try:
        partes = urlsplit(url)
    except ValueError:
        # `http://[::1/cb`: urlsplit lanza, y aquí solo se promete RuntimeError
        return False
    return (
        partes.scheme in {"http", "https"}
        and bool(partes.hostname)
        and partes.username is None
        and partes.password is None
    )


def _es_una_direccion_del_front(url: str) -> bool:
    """
    Una dirección de `FRONTEND_URL`: https, solo el sitio. A ella se le pega la ruta de
    cada enlace, así que con ruta propia, consulta o fragmento saldrían rotos; y por
    http los que llevan token viajarían en claro.
    """
    if not _es_una_url_de_front(url):
        return False
    partes = urlsplit(url)
    try:
        partes.port  # noqa: B018 - lanza si el puerto no es un número válido
    except ValueError:
        return False
    return (
        partes.scheme == "https"
        and partes.path in {"", "/"}
        and not partes.query
        and not partes.fragment
        and "?" not in url
        and "#" not in url
        and all(c.isascii() and c.isprintable() and c not in "\"'<>" for c in url)
    )


def comprueba_la_configuracion_de_seguridad(entorno: Mapping[str, str] = os.environ) -> None:
    """
    No deja arrancar fuera de desarrollo con TESTING, con una SECRET_KEY mala ni con
    COOKIE_DOMAIN, GOOGLE_REDIRECT_URI o FRONTEND_URL mal escritos.

    El mensaje dice el motivo, nunca la clave.

    Raises:
        RuntimeError: con el motivo; la app no arranca
    """
    # En cualquier entorno: si está puesta, es la que usarán las migraciones (DB-01). El
    # mensaje no la muestra: lleva la contraseña del dueño de la base
    migraciones = (entorno.get(VARIABLE_DE_LAS_MIGRACIONES) or "").strip()
    if migraciones and not _URL_DE_POSTGRES.match(migraciones):
        raise RuntimeError(
            f"{VARIABLE_DE_LAS_MIGRACIONES} no es una URL de PostgreSQL; no se arranca"
        )
    if en_desarrollo_declarado(entorno):
        # Render pone RENDER en todos sus servicios: un desarrollo ahí es un error de
        # configuración que se saltaría todo lo demás (revisión de la fase 2)
        if (entorno.get("RENDER") or "").strip():
            raise RuntimeError("ENVIRONMENT=development con RENDER definida; no se arranca")
        return
    # Cada entrada de COOKIE_DOMAIN tiene que ser un dominio y nada más (ADR-054). Una mal
    # escrita —con `https://`, con puerto, separadas con `;`— no fallaba: salía tal cual
    # en `Domain=`, el navegador descartaba la cookie y nadie podía entrar, sin un error
    # en ningún sitio. El mensaje no lleva el valor: puede ser un secreto pegado en la
    # variable equivocada, y esto acaba en el log y en Sentry
    if not all(_DOMINIO_DE_COOKIE.match(d) for d in dominios_de_cookie(entorno)):
        raise RuntimeError(
            "COOKIE_DOMAIN lleva una entrada que no es un dominio; van separados por"
            " comas, como .ejemplo.com; no se arranca"
        )
    # Y cada retorno de Google, una URL http(s) con su host y sin credenciales: con la
    # lista mal escrita Google rechazaba el canje y el error parecía un código caducado
    if not all(_es_una_url_de_front(u) for u in retornos_de_google(entorno)):
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI lleva una entrada que no es una URL http(s); van"
            " separadas por comas; no se arranca"
        )
    # Y cada dirección del front: de ellas salen los enlaces de los correos (ADR-055). Una
    # mal escrita mandaba a todos un botón que no abría nada
    if not all(_es_una_direccion_del_front(u) for u in direcciones_del_front(entorno)):
        raise RuntimeError(
            "FRONTEND_URL lleva una entrada que no es una dirección https sin ruta; van"
            " separadas por comas, como https://www.ejemplo.com; no se arranca"
        )
    if testing_activado(entorno):
        raise RuntimeError("TESTING=true fuera de desarrollo: apaga el CSRF; no se arranca")
    clave = (entorno.get("SECRET_KEY") or "").strip()
    if not clave:
        raise RuntimeError("SECRET_KEY sin configurar fuera de desarrollo; no se arranca")
    if clave in CLAVES_DE_EJEMPLO:
        raise RuntimeError("SECRET_KEY es un valor de ejemplo del repositorio; no se arranca")
    if len(clave.encode()) < LONGITUD_MINIMA_DE_LA_CLAVE:
        raise RuntimeError(
            f"SECRET_KEY de menos de {LONGITUD_MINIMA_DE_LA_CLAVE} bytes fuera de desarrollo;"
            " no se arranca"
        )


def main() -> int:
    """
    `python -m src.config.arranque_seguro`: lo ejecuta entrypoint.sh ANTES de migrar
    (/code-review de la fase 2). Si la comprobación fallara solo en el lifespan, la base
    de datos ya estaría migrada y la versión anterior seguiría sirviendo con el esquema
    nuevo. Sale con 1 y el motivo (nunca la clave) si la configuración no vale.
    """
    import sys  # noqa: PLC0415 - solo al ejecutarse como script

    try:
        comprueba_la_configuracion_de_seguridad(os.environ)
    except RuntimeError as error:
        print(f"Configuración insegura: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
