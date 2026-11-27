"""
La plantilla común de los correos (BE #389).

Todos los correos de la aplicación comparten esta cara, la de Comeback Golf:
una cabecera salvia con el logo y, detrás y muy tenue, un dibujo de la marca
que cambia con el asunto del correo; debajo, sobre arena, un título que dice lo
que pasa, un único botón grande en lima y, fuera de la tarjeta, el pie. El
español va primero y completo; el inglés, debajo y más corto, con su propio
botón.

**La cabecera es una imagen ya compuesta**, que sirve el front
(`/images/correo/cabecera-<dibujo>.png`, y su gemela `-oscuro.png` para el modo
oscuro): logo y dibujo van superpuestos, y eso los clientes de correo no lo
saben hacer. Va en `/images/`, la única carpeta
que el front sirve a otros orígenes. Si no la cargan, la celda sigue siendo
salvia y en su sitio se lee el nombre.

**Hecha para clientes de correo, no para navegadores.** Tablas y estilos en
línea: Gmail borra los bloques <style>, y Outlook no entiende flex ni grid.

**El claro es la base y el oscuro se añade encima.** Todos los colores van en
línea y además en `bgcolor`, y los botones son de tabla: así se ve en claro en
cualquier cliente, también donde se borran los <style> (el aviso del 21 oct 2026
llegó a Mail de iOS sin cabecera y con el botón invisible porque el fondo iba
solo por CSS y el cliente invertía los colores por su cuenta). El oscuro, con
los colores de la app, va en un único <style> con `prefers-color-scheme` y solo
lo aplica quien lo entiende (Mail de Apple); el correo se declara `light dark`
para que ese cliente use nuestros colores en vez de inventarlos. Gmail lo
ignora y sigue en claro.

**Nada del usuario entra como HTML.** Cada pieza escapa el texto que recibe;
solo `Html` —lo que la propia plantilla ya ha construido— pasa tal cual. Así
un nombre con «&» o un mensaje con «<script>» no pueden romper el correo ni
colarse en él, se escriba el correo que se escriba.
"""

import html as _html
from dataclasses import dataclass
from enum import StrEnum

from src.shared.domain.services.instante_utc import ahora_en_utc

# La paleta de la marca, la misma que los tokens del front
BOSQUE_PROFUNDO = "#222d24"
BOSQUE = "#354638"
LIMA = "#ddf478"
FONDO = "#f8f7f2"
ARENA = "#e8ddce"
SALVIA = "#dce3d7"
TEXTO = "#3a463c"
TITULAR = BOSQUE_PROFUNDO
# El texto pequeño: sobre arena y sobre el fondo llega a AA (lo vigila un test)
APAGADO = "#566159"
LINEA = "#cfc4b3"
AVISO_FONDO, AVISO_BORDE, AVISO_LETRA = "#fff7ed", "#fed7aa", "#7c2d12"

# El oscuro, con los colores de la app en oscuro (los tokens `--cbg-*` del front)
OSCURO_FONDO = "#222d24"
OSCURO_TARJETA = "#273328"
OSCURO_REALCE = "#354638"
OSCURO_TINTA = "#e8ddce"
OSCURO_TEXTO = "#d3d9cf"
OSCURO_APAGADO = "#b7bdb2"
OSCURO_LINEA = "#56655a"
OSCURO_AVISO_FONDO, OSCURO_AVISO_BORDE, OSCURO_AVISO_LETRA = "#3a3222", "#6b5a2e", "#f0c36a"

# El único <style>. Sin él el correo se ve en claro, entero: aquí solo va el oscuro
# (cada clase `o-*` cambia un color que el elemento ya lleva en línea) y que Mail de
# iOS no subraye por su cuenta fechas y horas como si fueran enlaces
ESTILO = (
    "<style>:root{color-scheme:light dark;}"
    "a[x-apple-data-detectors]{color:inherit!important;text-decoration:none!important;}"
    "@media (prefers-color-scheme:dark){"
    f".o-pagina{{background:{OSCURO_FONDO}!important;}}"
    f".o-tarjeta{{background:{OSCURO_TARJETA}!important;border:1px solid {OSCURO_LINEA}!important;}}"
    f".o-cabecera{{background:{OSCURO_REALCE}!important;color:{LIMA}!important;}}"
    f".o-realce{{background:{OSCURO_REALCE}!important;}}"
    f".o-tinta{{color:{OSCURO_TINTA}!important;}}"
    f".o-texto{{color:{OSCURO_TEXTO}!important;}}"
    f".o-apagado{{color:{OSCURO_APAGADO}!important;}}"
    f".o-marca{{color:{LIMA}!important;}}"
    f".o-cita{{border-color:{LIMA}!important;}}"
    f".o-linea{{border-color:{OSCURO_LINEA}!important;}}"
    f".o-aviso{{background:{OSCURO_AVISO_FONDO}!important;"
    f"border-color:{OSCURO_AVISO_BORDE}!important;color:{OSCURO_AVISO_LETRA}!important;}}"
    f".o-aviso .o-tinta{{color:{OSCURO_AVISO_LETRA}!important;}}"
    ".o-claro{display:none!important;}"
    ".o-oscuro{display:block!important;max-height:none!important;overflow:visible!important;}"
    "}</style>"
)
_LETRA = "'Helvetica Neue', Helvetica, Arial, sans-serif"
MARCA = "Comeback Golf"


class Dibujo(StrEnum):
    """El dibujo de la cabecera: uno por familia de correos."""

    GUANTE = "guante"  # la bienvenida
    GORRA = "gorra"  # gestiones de la cuenta, pedidas por su dueño
    BUNKER = "bunker"  # avisos de seguridad: «¿no has sido tú?»
    CARRITO = "carrito"  # invitación a un torneo
    TARJETA = "tarjeta"  # hándicaps
    PALOS = "palos"  # amistad

    # Cada uno tiene sus dos PNG en el front, el claro y el `-oscuro` (`public/images/correo/`), que lo comprueba en
    # `cabecerasDeCorreo.test.js`: un dibujo nuevo aquí se añade también allí


class Html(str):
    """Fragmento ya construido por la plantilla: no se vuelve a escapar."""


def _seguro(texto: str) -> str:
    return texto if isinstance(texto, Html) else _html.escape(texto)


def negrita(texto: str) -> Html:
    return Html(f'<strong class="o-tinta">{_seguro(texto)}</strong>')


def frase(*partes: str) -> Html:
    """Une trozos de una frase: el texto se escapa, lo marcado como Html no."""
    return Html("".join(_seguro(p) for p in partes))


@dataclass(frozen=True)
class Boton:
    texto: str
    enlace: str


def _celda(fondo: str, estilo: str = "") -> str:
    """
    Los atributos de una celda con color: `bgcolor` y `background` salen del
    mismo valor. Mail de iOS en modo oscuro quita el fondo puesto solo por CSS.
    """
    return f'bgcolor="{fondo}" style="background:{fondo};{estilo}"'


def parrafo(*partes: str, pequeno: bool = False) -> Html:
    tamano = "13px" if pequeno else "15px"
    color, clase = (APAGADO, "o-apagado") if pequeno else (TEXTO, "o-texto")
    return Html(
        f'<p class="{clase}" style="margin:0 0 14px;font-family:{_LETRA};font-size:{tamano};'
        f'line-height:1.6;color:{color};">{frase(*partes)}</p>'
    )


def recuadro(titulo: str, *lineas: str) -> Html:
    """Lo importante del correo —la competición, el plazo— en su caja."""
    filas = "".join(
        f'<div class="o-texto" style="font-family:{_LETRA};font-size:13px;line-height:1.6;'
        f'color:{TEXTO};">'
        f"{_seguro(linea)}</div>"
        for linea in lineas
    )
    return Html(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 14px;border-collapse:separate;">'
        f'<tr><td class="o-realce" {_celda(FONDO, "border-radius:16px;padding:16px 18px;")}>'
        f'<div class="o-tinta" style="font-family:{_LETRA};font-size:18px;font-weight:800;'
        f'line-height:1.3;color:{TITULAR};margin:0 0 4px;">{_seguro(titulo)}</div>'
        f"{filas}</td></tr></table>"
    )


def cita(texto: str, autor: str) -> Html:
    """El mensaje personal de quien invita."""
    return Html(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" data-cita '
        'style="margin:0 0 14px;">'
        f'<tr><td class="o-cita" style="border-left:3px solid {BOSQUE};padding:4px 0 4px 14px;">'
        f'<div class="o-tinta" style="font-family:{_LETRA};font-size:15px;font-style:italic;'
        f"line-height:1.5;"
        f'color:{TITULAR};">«{_seguro(texto)}»</div>'
        f'<div class="o-apagado" style="font-family:{_LETRA};font-size:12px;color:{APAGADO};'
        f'margin-top:4px;">'
        f"{_seguro(autor)}</div></td></tr></table>"
    )


def aviso(*partes: str) -> Html:
    """Algo que requiere atención —«¿no has sido tú?»—, en ámbar."""
    return Html(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 14px;">'
        '<tr><td class="o-aviso" '
        + _celda(
            AVISO_FONDO,
            f"border:1px solid {AVISO_BORDE};border-radius:16px;padding:14px 16px;"
            f"font-family:{_LETRA};font-size:14px;line-height:1.55;color:{AVISO_LETRA};",
        )
        + f">{frase(*partes)}</td></tr></table>"
    )


def _celda_de_boton(boton: Boton, principal: bool, relleno: str, letra_px: int = 14) -> str:
    """
    La celda de un botón «a prueba de balas»: el color lo pone la celda (`bgcolor` y
    estilo) y el enlace solo es texto, con su color también en un <span>. Un <a> con
    fondo propio desaparecía en el modo oscuro de Mail. Rectangular y sin borde; el
    texto, siempre en una línea (Agustín, 25 nov 2026).
    """
    if principal:
        # Lima con letra oscura, igual en claro que en oscuro
        fondo, clase_celda, clase_letra = LIMA, "", ""
    else:
        # Sobre la arena de la tarjeta, el mismo claro del recuadro: la salvia apenas
        # se distinguía de ella (1,02:1) y el botón parecía texto suelto
        fondo, clase_celda, clase_letra = FONDO, ' class="o-realce"', ' class="o-tinta"'
    letra = BOSQUE_PROFUNDO
    # Outlook de escritorio no respeta el relleno del <a>: mso-padding-alt se lo da a
    # la celda y el botón conserva su tamaño
    celda = _celda(fondo, f"mso-padding-alt:{relleno};")
    return (
        f'<td align="center"{clase_celda} {celda}>'
        f'<a data-boton{clase_letra} href="{_html.escape(boton.enlace, quote=True)}" '
        f'target="_blank" style="display:block;padding:{relleno};font-family:{_LETRA};'
        f"font-size:{letra_px}px;font-weight:700;text-align:center;white-space:nowrap;"
        f'color:{letra};text-decoration:none;">'
        f'<span{clase_letra} style="color:{letra};">{_seguro(boton.texto)}</span></a>'
        "</td>"
    )


def _boton(boton: Boton, principal: bool) -> str:
    """Un botón solo: a la izquierda, con el ancho de su texto."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="margin:6px 0 14px;"><tr>'
        f"{_celda_de_boton(boton, principal, '13px 18px')}"
        "</tr></table>"
    )


def _pareja_de_botones(principal: Boton, secundario: Boton) -> str:
    """
    Dos botones en paralelo, a partes iguales del ancho: así caben en fila y en una
    línea también en el móvil más estrecho.

    Con `table-layout:fixed` y solo el hueco con ancho, las dos celdas se reparten el
    resto a medias. A 320 px cada una deja 116 px para el texto: a 13 px en negrita,
    «Nueva contraseña» mide 112. Un texto más largo no cabe: lo limita un test.
    """
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" data-pareja '
        'style="margin:6px 0 14px;table-layout:fixed;"><tr>'
        f"{_celda_de_boton(principal, True, '13px 2px', 13)}"
        '<td width="8" style="width:8px;font-size:0;line-height:0;">&nbsp;</td>'
        f"{_celda_de_boton(secundario, False, '13px 2px', 13)}"
        "</tr></table>"
    )


def _respaldo(enlace: str) -> str:
    """El enlace a mano, por si el botón no se puede pulsar."""
    seguro = _html.escape(enlace, quote=True)
    return (
        f'<p class="o-apagado" style="margin:0 0 6px;font-family:{_LETRA};font-size:12px;'
        f"line-height:1.5;"
        f'color:{APAGADO};">¿No funciona el botón? Copia este enlace · '
        f"Button not working? Copy this link:<br>"
        f'<a class="o-marca" href="{seguro}" target="_blank" '
        f'style="color:{BOSQUE};word-break:break-all;">'
        f"{seguro}</a></p>"
    )


@dataclass(frozen=True)
class Ingles:
    """El bloque en inglés: una frase y su botón."""

    texto: Html
    boton: Boton


def correo(
    *,
    web: str,
    resumen: str,
    etiqueta: str,
    dibujo: Dibujo,
    titulo: str,
    cuerpo: list[Html],
    boton: Boton,
    ingles: Ingles,
    pie: str,
    otros_botones: list[Boton] | None = None,
    con_respaldo: bool = True,
) -> str:
    """
    Arma el correo entero.

    Args:
        web: La dirección del frontend, de donde sale la imagen de la cabecera
        resumen: La línea que el cliente de correo enseña junto al asunto
        etiqueta: La palabra de encima del título («Invitación»)
        dibujo: El dibujo de la cabecera, según de qué va el correo
        titulo: Lo que pasa, en una frase
        cuerpo: Los párrafos y cajas del español, ya construidos
        boton: La acción principal
        ingles: El bloque corto en inglés
        pie: Por qué le llega el correo, en los dos idiomas
        otros_botones: Acciones secundarias bajo la principal (registrarse)
        con_respaldo: Si se repite el enlace a mano bajo el botón. Sí por
            defecto: un botón que el cliente de correo no deja pulsar no
            puede ser el único camino
    """
    clara = _html.escape(f"{web}/images/correo/cabecera-{dibujo.value}.png", quote=True)
    oscura = _html.escape(f"{web}/images/correo/cabecera-{dibujo.value}-oscuro.png", quote=True)
    imagen = "display:block;width:100%;max-width:560px;height:auto;border:0;"
    anio = ahora_en_utc().year
    otros = otros_botones or []
    # Con un solo secundario, en paralelo con el principal; con más, uno bajo otro
    if len(otros) == 1:
        botones = _pareja_de_botones(boton, otros[0])
    else:
        botones = _boton(boton, principal=True) + "".join(_boton(b, principal=False) for b in otros)
    respaldo = _respaldo(boton.enlace) if con_respaldo else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<meta name="format-detection" content="telephone=no,date=no,address=no,email=no">
{ESTILO}
<title>{_seguro(titulo)}</title>
</head>
<body class="o-pagina" {_celda(FONDO, "margin:0;padding:0;")}>
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_seguro(resumen)}</div>
<table class="o-pagina" role="presentation" width="100%" cellpadding="0" cellspacing="0" {_celda(FONDO)}>
<tr><td align="center" style="padding:24px 12px;">
<table class="o-tarjeta" role="presentation" width="100%" cellpadding="0" cellspacing="0" {_celda(ARENA, "max-width:560px;border-radius:24px;overflow:hidden;")}>
<tr><td data-cabecera class="o-cabecera" {_celda(SALVIA, f"padding:0;font-family:{_LETRA};font-size:24px;font-weight:800;line-height:1.2;color:{TITULAR};")}><img class="o-claro" src="{clara}" width="560" alt="{MARCA}" style="{imagen}color:{TITULAR};"><!--[if !mso]><!--><div class="o-oscuro" style="display:none;max-height:0;overflow:hidden;mso-hide:all;"><img src="{oscura}" width="560" alt="{MARCA}" style="{imagen}color:{LIMA};"></div><!--<![endif]--></td></tr>
<tr><td style="padding:28px 24px 4px;">
<div class="o-marca" style="font-family:{_LETRA};font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:{BOSQUE};margin:0 0 10px;">{_seguro(etiqueta)}</div>
<h1 class="o-tinta" style="margin:0 0 16px;font-family:{_LETRA};font-size:26px;line-height:1.15;font-weight:800;letter-spacing:-0.4px;color:{TITULAR};">{_seguro(titulo)}</h1>
{"".join(cuerpo)}
{botones}
{respaldo}
</td></tr>
<tr><td style="padding:4px 24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td class="o-linea" style="border-top:1px solid {LINEA};padding-top:16px;">
<div class="o-apagado" style="font-family:{_LETRA};font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:{APAGADO};margin:0 0 8px;">English</div>
<p class="o-texto" style="margin:0 0 10px;font-family:{_LETRA};font-size:14px;line-height:1.55;color:{TEXTO};">{ingles.texto}</p>
{_boton(ingles.boton, principal=False)}
</td></tr></table>
</td></tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;">
<tr><td data-pie class="o-apagado" style="padding:18px 12px 8px;font-family:{_LETRA};font-size:12px;line-height:1.5;color:{APAGADO};">
{_seguro(pie)}<br>© {anio} {MARCA}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""
