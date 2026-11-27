"""
Imágenes de prueba para los tests del procesado de imágenes (unidad e integración).

Archivos cortados o dañados como los de una subida que se quedó a medias. Llevan
ruido para que el archivo sea grande y un corte caiga en los píxeles, no en la
cabecera. Se construyen una vez por proceso (`functools.cache`): el ruido cuesta.
"""

import functools
import io
import random

from PIL import Image


def con_ruido(ancho: int, alto: int, semilla: int = 7) -> Image.Image:
    """Una imagen RGB de ruido, siempre la misma para la misma semilla."""
    return Image.frombytes("RGB", (ancho, alto), random.Random(semilla).randbytes(ancho * alto * 3))


def guardada(imagen: Image.Image, formato: str, **opciones) -> bytes:
    """Los bytes de `imagen` guardada en `formato`."""
    buffer = io.BytesIO()
    imagen.save(buffer, formato, **opciones)
    return buffer.getvalue()


@functools.cache
def cortada(formato: str, fraccion: float) -> bytes:
    """Una foto de 600x400 en `formato`, cortada a esa fracción de su tamaño."""
    completa = guardada(con_ruido(600, 400), formato)
    return completa[: int(len(completa) * fraccion)]


@functools.cache
def apng() -> bytes:
    """Un PNG animado de tres fotogramas (Pillow lo abre como «PNG»)."""
    fotogramas = [con_ruido(200, 150, semilla) for semilla in (1, 2, 3)]
    return guardada(fotogramas[0], "PNG", save_all=True, append_images=fotogramas[1:])


def apng_cortado(fraccion: float) -> bytes:
    """El APNG de `apng()`, cortado a esa fracción de su tamaño."""
    completo = apng()
    return completo[: int(len(completo) * fraccion)]


def con_un_byte_cambiado(datos: bytes, chunk: bytes, aparicion: int = 1) -> bytes:
    """
    Cambia un byte dentro de la aparición `aparicion` del chunk de PNG indicado (su CRC
    deja de cuadrar). Si el chunk no está, falla: nunca daña otro sitio del archivo.
    """
    danados = bytearray(datos)
    posicion = -1
    for _ in range(aparicion):
        posicion = danados.find(chunk, posicion + 1)
        assert posicion >= 0, f"no hay {aparicion} chunks {chunk!r} en el archivo"
    danados[posicion + 10] ^= 0xFF
    return bytes(danados)
