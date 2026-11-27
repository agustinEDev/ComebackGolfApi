"""
La marca vieja no vuelve al código (27 nov 2026, decisión de Agustín: «eliminemos
todo lo referente a la marca»).

  M1  ningún fichero del repo nombra la marca vieja (salvo el CHANGELOG, que es historia
      y se empieza de nuevo en los repos nuevos)
  M2  excepción: los roles de la base de datos de producción (`rydercup_app`,
      `rydercup_owner`, `rydercupam_*`), que se quedan como la propia base
  M3  el modo de juego RYDER_CUP («Ryder Cup» como formato) no es la marca: se queda

Los números de issue anteriores a los repos nuevos (BE #…, FE #…) son de los repos
archivados RyderCupAm y RyderCupWeb.
"""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MARCA = re.compile(
    r"ryder[ _-]?cup[ _-]?(friends|am\b|web)|rydercupfriends|rydercupam(?!_)"
    r"|rydercup[-:.][a-z]|rydercup_(?!app\b|owner\b)|/rydercup\b|(?-i:\brydercup\b)|ryder ?cup (amateur )?manager|ryderclub",
    re.IGNORECASE,
)
ESTE = Path(__file__).resolve()
# La historia: el CHANGELOG se empieza de nuevo en los repos nuevos
FUERA = {"CHANGELOG.md"}


def _ficheros(*carpetas: str) -> list[Path]:
    salida = subprocess.run(
        ["git", "ls-files", *carpetas], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return [
        RAIZ / f
        for f in salida.splitlines()
        if (RAIZ / f).resolve() != ESTE and f not in FUERA and (RAIZ / f).is_file()
    ]


def test_m1_the_repo_does_not_name_the_old_brand():
    """
    Given: todos los ficheros del repo
    When: se busca la marca vieja
    Then: no aparece (salvo los roles de la base, M2)
    """
    encontrados = []
    for fichero in _ficheros():
        try:
            texto = fichero.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for numero, linea in enumerate(texto.splitlines(), 1):
            if MARCA.search(linea):
                encontrados.append(f"{fichero.relative_to(RAIZ)}:{numero}: {linea.strip()}")
    assert encontrados == []


def test_m2_the_database_roles_are_not_the_brand():
    """
    Given: los roles que se quedan en producción
    When: se comprueban con el patrón
    Then: no cuentan como marca; el dominio o el nombre de la app sí
    """
    for permitido in ("rydercup_app", "rydercup_owner", "rydercupam_adminuser"):
        assert not MARCA.search(permitido), permitido
    for prohibido in (
        "rydercupfriends.com",
        "RyderCupAm",
        "RyderCupWeb #880",
        "rydercup-api",
        "Ryder Cup Friends",
        "ryder-cup-friends",
        "RYDER_CUP_FRIENDS",
        "Ryder Cup AM",
        "db:5432/rydercup",
        "app: rydercup",
        "Ryder Cup Manager API",
        "ryderclub",
    ):
        assert MARCA.search(prohibido), prohibido
    # M3: el modo de juego se queda
    for modo in (
        "RYDER_CUP",
        "ryder_cup_setup",
        "RyderCupSetup",
        "TournamentType.RYDER_CUP",
        "en estilo RyderCup",
    ):
        assert not MARCA.search(modo), modo
