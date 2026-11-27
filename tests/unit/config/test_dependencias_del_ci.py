"""
El CI prueba y audita lo mismo que se despliega (re-auditoría del 16 nov 2026).

- INF-05: los tests, mypy, bandit y pip-audit corrían sobre una resolución nueva y sin
  hashes de requirements-dev.txt, mientras la imagen instala requirements.lock. Ahora
  cada job instala antes el lock exacto con --require-hashes (y pip desde su lock de
  arranque), después las herramientas de desarrollo, y comprueba que ninguna versión del
  lock se ha movido.
- INF-04: el generador del SBOM se instala desde su propio lock con hashes, y el paso que
  tiene el token no ejecuta ninguna herramienta instalada.
- INF-03: el SBOM se genera desde requirements.lock (los 55 paquetes que se instalan), no
  desde requirements.txt (31).
"""

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
FLUJOS = RAIZ / ".github" / "workflows"


def _pasos(fichero: str) -> list[tuple[str, dict]]:
    """(job, paso) de cada paso con `run` del workflow."""
    flujo = yaml.safe_load((FLUJOS / fichero).read_text(encoding="utf-8"))
    return [
        (nombre, paso)
        for nombre, job in flujo["jobs"].items()
        for paso in job.get("steps", [])
        if "run" in paso
    ]


def _ordenes(run: str) -> list[str]:
    """Las órdenes de un `run`, sin comentarios y con las continuaciones unidas."""
    lineas = [x for x in run.replace("\\\n", " ").splitlines() if not x.strip().startswith("#")]
    return [x.strip() for x in lineas if x.strip()]


def _instalaciones(fichero: str) -> list[tuple[str, str, list[str]]]:
    return [
        (job, paso.get("name", ""), _ordenes(paso["run"]))
        for job, paso in _pasos(fichero)
        if "pip install" in paso["run"]
    ]


# Quién instala el proyecto y cómo: con las herramientas de desarrollo (--dev) o solo lo
# que se despliega. Un consumidor que falte o cambie de modo tiene que verse aquí
INSTALADORES = {
    ("ci_cd_pipeline.yml", "unit_tests"): "--dev",
    ("ci_cd_pipeline.yml", "integration_tests"): "--dev",
    ("ci_cd_pipeline.yml", "security_tests"): "--dev",
    ("ci_cd_pipeline.yml", "security_checks"): "--dev",
    ("ci_cd_pipeline.yml", "linting"): "--dev",
    ("ci_cd_pipeline.yml", "type_checking"): "--dev",
    ("ci_cd_pipeline.yml", "api_contract"): "",
    ("snyk_review.yml", "snyk"): "",
}


def test_every_ci_job_installs_through_the_shared_script():
    """
    Given: los pasos del CI y de Snyk
    When: se mira qué ejecutan
    Then: ninguno instala requirements*.txt a mano, y cada job que instala el proyecto
          llama UNA vez a instalar_dependencias.sh, con --dev solo donde hacen falta
          las herramientas (CodeRabbit en BE #884: un total no ve un job que falte)
    """
    llamadas: dict[tuple[str, str], list[str]] = {}
    for fichero in ("ci_cd_pipeline.yml", "snyk_review.yml"):
        for job, paso in _pasos(fichero):
            donde = f"{fichero} · {job} · {paso.get('name', '')}"
            for orden in _ordenes(paso["run"]):
                assert not re.search(r"pip install .*-r requirements", orden), donde
                if "bash .github/scripts/instalar_dependencias.sh" in orden:
                    modo = orden.split("instalar_dependencias.sh", 1)[1].strip()
                    llamadas.setdefault((fichero, job), []).append(modo)

    assert llamadas == {clave: [modo] for clave, modo in INSTALADORES.items()}


def test_the_install_script_installs_the_locks_with_hashes_before_the_dev_tools():
    """
    Given: .github/scripts/instalar_dependencias.sh
    When: se miran sus órdenes
    Then: pip desde su lock y el proyecto desde requirements.lock, con --require-hashes;
          después, solo con --dev, las herramientas; y al final comprueba los DOS locks
    """
    guion = (RAIZ / ".github" / "scripts" / "instalar_dependencias.sh").read_text(encoding="utf-8")
    ordenes = [o for o in _ordenes(guion) if not o.startswith(("set ", "if ", "fi"))]

    assert "--require-hashes --no-deps -r requirements-bootstrap.lock" in ordenes[0]
    assert "--require-hashes -r requirements.lock" in ordenes[1]
    assert "-r requirements-dev.txt" in ordenes[2]
    assert ordenes[-1] == (
        "python .github/scripts/comprobar_lock_instalado.py "
        "requirements.lock requirements-bootstrap.lock"
    )


def test_no_ci_step_upgrades_pip_without_a_version_and_a_hash():
    """
    Given: los workflows de Python
    When: se buscan instalaciones de pip
    Then: ninguna es `pip install --upgrade pip` (sin versión ni hash)
    """
    for fichero in ("ci_cd_pipeline.yml", "snyk_review.yml"):
        for job, nombre, ordenes in _instalaciones(fichero):
            for orden in ordenes:
                assert "--upgrade pip" not in orden, f"{fichero} · {job} · {nombre}"
    guion = (RAIZ / ".github" / "scripts" / "instalar_dependencias.sh").read_text(encoding="utf-8")
    assert "--upgrade pip" not in guion


def test_the_sbom_comes_from_the_lock_and_its_tool_from_a_hashed_lock():
    """
    Given: los jobs del SBOM
    When: se miran sus pasos y permisos
    Then: el que genera instala el generador con --require-hashes desde su lock, genera
          desde requirements.lock y solo lee; el que envía es el único con escritura y no
          instala ni ejecuta ninguna herramienta (comparten nada más que el artifact)
    """
    flujo = yaml.safe_load((FLUJOS / "ci_cd_pipeline.yml").read_text(encoding="utf-8"))
    genera = flujo["jobs"]["sbom_generation"]
    envia = flujo["jobs"]["sbom_submission"]
    runs = [p["run"] for p in genera["steps"] if "run" in p]

    instalar = next(r for r in runs if "sbom-tools" in r)
    assert "--require-hashes" in instalar
    assert "-r .github/sbom-tools.lock" in instalar
    generar = next(r for r in runs if "cyclonedx-py requirements" in r)
    assert re.search(r"cyclonedx-py requirements requirements\.lock\b", generar)

    assert genera["permissions"] == {"contents": "read"}
    assert not any("GITHUB_TOKEN" in (p.get("env") or {}) for p in genera["steps"])

    assert envia["permissions"] == {"contents": "write"}
    assert envia["needs"] == ["sbom_generation"]
    for paso in envia["steps"]:
        texto = paso.get("run", "") + str(paso.get("uses", ""))
        assert "pip install" not in texto
        assert "cyclonedx-py" not in texto
        assert "setup-python" not in texto

    guion = (RAIZ / "scripts" / "submit-sbom-to-github.sh").read_text(encoding="utf-8")
    assert "cyclonedx-py --version" not in guion
    assert '"requirements.lock"' in guion
    # Un correlator fijo: cada envío sustituye al anterior, y el manifiesto viejo
    # (requirements.txt) no se queda colgado en el grafo
    assert '"correlator": "sbom_generation",' in guion
    # La versión que llega en el SBOM solo entra con forma de versión
    assert 'DETECTOR_VERSION="unknown"' in guion


def test_the_sbom_tool_lock_pins_its_source_with_hashes():
    """
    Given: .github/sbom-tools.txt y su lock
    When: se comparan
    Then: el lock fija cyclonedx-bom a la versión de la fuente y todo lleva hash
    """
    fuente = (RAIZ / ".github" / "sbom-tools.txt").read_text(encoding="utf-8")
    lock = (RAIZ / ".github" / "sbom-tools.lock").read_text(encoding="utf-8")

    version = re.search(r"^cyclonedx-bom==(\S+)", fuente, re.M)
    assert version
    assert f"cyclonedx-bom=={version.group(1)}" in lock
    bloques = [b for b in re.split(r"\n(?=[A-Za-z0-9._-]+==)", lock) if "==" in b.split("\n")[0]]
    assert bloques
    assert all("--hash=sha256:" in b for b in bloques)


def _comprobador():
    """El script de comprobación, cargado como módulo."""
    import importlib.util

    ruta = RAIZ / ".github" / "scripts" / "comprobar_lock_instalado.py"
    spec = importlib.util.spec_from_file_location("comprobar_lock_instalado", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_the_installed_lock_check_finds_a_moved_version(tmp_path):
    """
    Given: un lock con un paquete en una versión que no es la instalada
    When: se ejecuta la comprobación del CI
    Then: termina con error y nombra el paquete
    """
    modulo = _comprobador()

    lock = tmp_path / "requirements.lock"
    lock.write_text("pyyaml==0.0.1 \\\n    --hash=sha256:abc\n", encoding="utf-8")

    distintos = modulo.distintos(lock)

    assert "pyyaml" in distintos
    assert distintos["pyyaml"][0] == "0.0.1"


def test_the_installed_lock_check_passes_with_other_spellings_of_the_names(tmp_path):
    """
    Given: un lock con paquetes instalados escritos con otra grafía (PyYAML, Typing_Extensions)
    When: se ejecuta la comprobación del CI
    Then: no da ninguno por distinto
    """
    import importlib.metadata

    modulo = _comprobador()
    version = importlib.metadata.version("pyyaml")
    extensiones = importlib.metadata.version("typing-extensions")

    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"PyYAML=={version} \\\n    --hash=sha256:abc\n    # via -r requirements.txt\n"
        f"Typing_Extensions=={extensiones} \\\n    --hash=sha256:abc\n",
        encoding="utf-8",
    )

    assert modulo.distintos(lock) == {}


def test_the_lock_check_fails_when_any_of_several_locks_moved(tmp_path, monkeypatch, capsys):
    """
    Given: dos locks, el primero bien y el segundo (el de pip) con otra versión
    When: se ejecuta la comprobación con los dos
    Then: sale con 1 y nombra el lock que no coincide
    """
    import importlib.metadata

    modulo = _comprobador()
    bien = tmp_path / "requirements.lock"
    bien.write_text(f"pyyaml=={importlib.metadata.version('pyyaml')}\n", encoding="utf-8")
    mal = tmp_path / "requirements-bootstrap.lock"
    mal.write_text("pip==0.0.1\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", str(bien), str(mal)])

    assert modulo.main() == 1
    assert "requirements-bootstrap.lock" in capsys.readouterr().out


FILTRO_DE_ARQUITECTURA = '"$RUNNER_TEMP/arquitectura.txt"'


def _paso_de_arquitectura() -> str:
    """El `run` del único paso del job de arquitectura que instala con pip."""
    runs = [
        paso["run"]
        for job, paso in _pasos("ci_cd_pipeline.yml")
        if job == "architecture" and "pip install" in paso["run"]
    ]
    assert len(runs) == 1, runs
    return runs[0]


def _ejecutar_paso_de_arquitectura(tmp_path: Path, dev: str):
    """
    Ejecuta el paso tal cual con bash -e (el shell de GitHub), en una carpeta con el
    requirements-dev.txt dado y un `pip` falso que copia lo que le piden instalar.
    """
    import shutil
    import subprocess

    (tmp_path / "requirements-dev.txt").write_text(dev, encoding="utf-8")
    binarios = tmp_path / "bin"
    binarios.mkdir()
    pip = binarios / "pip"
    pip.write_text(
        '#!/bin/sh\n[ "$1 $2" = "install -r" ] || exit 9\ncat "$3" > "$PIP_INSTALO"\n',
        encoding="utf-8",
    )
    pip.chmod(0o755)
    temporal = tmp_path / "runner_temp"
    temporal.mkdir()
    instalado = tmp_path / "instalado.txt"
    bash = shutil.which("bash")
    assert bash
    resultado = subprocess.run(
        [bash, "-e", "-c", _paso_de_arquitectura()],
        cwd=tmp_path,
        env={
            "PATH": f"{binarios}:/usr/bin:/bin",
            "RUNNER_TEMP": str(temporal),
            "PIP_INSTALO": str(instalado),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return resultado, instalado


def test_the_architecture_job_pins_import_linter_and_grimp_from_requirements_dev():
    """
    Given: el job de arquitectura, que instala import-linter suelto (sin el script)
    When: se mira su paso de instalación
    Then: filtra de requirements-dev.txt las líneas exactas de import-linter y grimp a
          un fichero temporal, comprueba que son 2 y las instala con `pip install -r`:
          import-linter solo pide grimp>=X, y sin fijarla el CI usaría la última grimp
          publicada, no la que se probó en local
    """
    ordenes = _ordenes(_paso_de_arquitectura())
    filtro = "grep -E '^(import-linter|grimp)==' requirements-dev.txt > " + FILTRO_DE_ARQUITECTURA

    assert ordenes[0] == filtro, ordenes
    assert any(FILTRO_DE_ARQUITECTURA in o and "-eq 2" in o for o in ordenes[1:-1]), ordenes
    assert ordenes[-1] == "pip install -r " + FILTRO_DE_ARQUITECTURA, ordenes

    dev = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
    for paquete in ("import-linter", "grimp"):
        assert len(re.findall(rf"^{paquete}==\S+", dev, re.MULTILINE)) == 1, paquete


def test_the_architecture_step_installs_both_pins_even_with_a_trailing_comment(tmp_path):
    """
    Given: un requirements-dev.txt con las dos líneas, una con comentario al final
    When: se ejecuta el paso de instalación del job de arquitectura
    Then: pip recibe con -r exactamente esas dos líneas
    """
    dev = "ruff==1.0\nimport-linter==2.16  # contratos\ngrimp==3.19\n"

    resultado, instalado = _ejecutar_paso_de_arquitectura(tmp_path, dev)

    assert resultado.returncode == 0, resultado.stderr
    assert instalado.read_text(encoding="utf-8").splitlines() == [
        "import-linter==2.16  # contratos",
        "grimp==3.19",
    ]


def test_the_architecture_step_fails_when_a_pin_is_missing(tmp_path):
    """
    Given: un requirements-dev.txt sin la línea exacta de grimp
    When: se ejecuta el paso de instalación del job de arquitectura
    Then: falla antes de llamar a pip
    """
    resultado, instalado = _ejecutar_paso_de_arquitectura(tmp_path, "import-linter==2.16\n")

    assert resultado.returncode != 0
    assert not instalado.exists()


def test_dependabot_bumps_import_linter_and_grimp_in_the_same_group():
    """
    Given: .github/dependabot.yml
    When: se mira el grupo dev-tools del ecosistema pip
    Then: incluye import-linter y grimp, para que lleguen en la misma PR (import-linter
          pide una grimp mínima y por separado no instalan: #924 y #874)
    """
    config = yaml.safe_load((RAIZ / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    pip = next(u for u in config["updates"] if u["package-ecosystem"] == "pip")
    patrones = pip["groups"]["dev-tools"]["patterns"]

    assert "import-linter" in patrones
    assert "grimp" in patrones
