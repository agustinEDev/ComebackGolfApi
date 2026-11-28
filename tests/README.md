# 🧪 Tests de Comeback Golf API

Cómo están organizados los tests, cómo se ejecutan y qué piezas de `conftest.py`
conviene conocer. La configuración vive en [`pytest.ini`](../pytest.ini) y
[`tests/conftest.py`](conftest.py); el CI que los ejecuta, en
[`docs/ci-cd/PIPELINE_GUIDE.md`](../docs/ci-cd/PIPELINE_GUIDE.md).

## 🎯 Filosofía

- **TDD**: primero la tabla de casos y el test que falla, luego el código.
- **Los tests son documentación viva**: muchos llevan en el docstring el caso en
  formato *Given / When / Then*.
- **Sin efectos fuera**: `conftest.py` sustituye el servicio de correo por un doble y
  vacía `SENTRY_DSN`, así que los tests no mandan correos ni eventos a Sentry. La RFEG de
  la app de prueba es un mock salvo que el test ponga el suyo.

## 🏗️ Estructura

```text
tests/
├── unit/            # Rápidos y sin base de datos
│   ├── architecture/   # Reglas de arquitectura como tests (imports por capa, logs, reloj…)
│   ├── config/         # Arranque, configuración, dependencias con hash
│   ├── fakes/          # Tests de los dobles de tests/fakes
│   ├── modules/        # competition · golf_course · quick_match · social · support · user
│   ├── scripts/        # Scripts del CI y de mantenimiento
│   └── shared/         # Dominio, aplicación e infraestructura compartidos
├── integration/     # Contra PostgreSQL de verdad (API, repositorios, migraciones)
│   ├── api/            # Endpoints de FastAPI de punta a punta
│   ├── config/         # Tareas de fondo y tiempos límite contra la base
│   ├── logging/        # Rastro de auditoría de seguridad
│   ├── modules/        # Persistencia por módulo
│   └── test_*_migration.py  # Migraciones de Alembic (y paridad del esquema, rol de la API…)
├── security/        # CSRF, XSS, inyección SQL, auth bypass, rate limiting
├── fakes/           # Dobles reutilizables (p. ej. el servicio de hándicap)
└── fixtures/        # Datos de prueba (extracto de OpenStreetMap)
```

Recuento con `pytest --collect-only -q` (28 nov 2026, v2.82.0): **11.258** unitarios,
**1.737** de integración y **67** de seguridad.

## 🚀 Cómo ejecutarlos

```bash
source .venv/bin/activate

pytest tests/unit/                 # Unitarios (sin base de datos)
pytest tests/security -n 2         # Seguridad
pytest tests/integration/          # Integración: necesita PostgreSQL (ver abajo)

# Un fichero o un test concreto
pytest tests/unit/modules/user/domain/value_objects/test_user_id.py
pytest "tests/unit/test_sin_la_marca_vieja.py::test_m1_the_repo_does_not_name_the_old_brand"
```

`pytest.ini` añade `-n auto` (pytest-xdist): todo corre en paralelo con un proceso por
núcleo. Para depurar en un solo proceso, `-n0`.

Ejecuta cada carpeta por separado, como el CI: hay varios módulos de test con el
mismo nombre en carpetas distintas (p. ej. `test_rotacion_del_refresco.py`) y una
colección conjunta (`pytest tests/`) falla al importar.

### `dev_tests.py`

Lanza la suite con pytest-xdist y `pytest-json-report` y deja los informes en
`tests/reports/`:

- `test_report.json`: los resultados en crudo.
- `test_summary.md`: resumen legible (totales, avisos, los tests más lentos y el
  detalle de los fallos).
- `warnings.txt`: todos los avisos de la ejecución.

```bash
python dev_tests.py
```

### PostgreSQL para integración

Los tests de integración usan la misma URL que la app: `tests/conftest.py` la importa
de `src/config/database.py` (como `APP_DATABASE_URL`, un alias interno, no una variable
de entorno) y crea en ese servidor una base efímera por test. Esa URL sale de:

1. `DATABASE_URL`, del entorno o del `.env` de la raíz (`load_dotenv()` no pisa lo ya
   exportado). Ojo: el `.env` copiado de `.env.example` trae una con el puerto 5432.
2. Si no hay `DATABASE_URL`: `postgresql://POSTGRES_USER:POSTGRES_PASSWORD@localhost:DATABASE_PORT/POSTGRES_DB`,
   con `user`, `pass`, `5434` (la base del Kind) y `comebackgolf_db` por defecto. El host
   es siempre `localhost`: `DATABASE_HOST` se ignora.

`postgres://` no vale: solo se reescribe `postgresql://` a `postgresql+asyncpg://`. El
usuario necesita permiso para crear bases (`CREATE DATABASE`).

Para usar la base del docker-compose (puerto 5433 en el ordenador), exporta la URL con
las credenciales de `docker/.env`:

```bash
cd docker && docker compose up -d db && cd ..
export DATABASE_URL="postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@localhost:5433/<POSTGRES_DB>"
pytest tests/integration/
```

## 🛠️ Configuración clave

### `pytest.ini`

- `asyncio_mode = auto`: las funciones `async def` se ejecutan sin decorador.
- `addopts = -n auto`: paralelo por defecto.
- `markers`: registra `integration`.

### `tests/conftest.py`

- **`pytest_configure`**: arranca los mappers de SQLAlchemy (los mismos que la app y
  Alembic) una sola vez, también con xdist.
- **`client`**: el `AsyncClient` de httpx para los tests de API. Cada test tiene **su
  propia base de datos** (`test_db_<worker>_<id>`), con el esquema creado al empezar y
  borrada al terminar, así que los tests en paralelo no se pisan.
- **`db_session`**: una `AsyncSession` aislada, con la misma estrategia, para probar
  repositorios.
- **`unit_client`**: cliente de la app sin base de datos para tests unitarios de rutas.
- **Dobles automáticos**: `mock_external_services` (el servicio de correo) y
  `reset_rate_limits` (limpia el rate limiting entre tests).
- **Ayudas**: `authenticated_client`, `create_authenticated_user`,
  `create_competition`, `sample_user_data`, `sample_competition_data`…

## 🔒 Tests que vigilan el repo

- `tests/unit/architecture/`: reglas de Clean Architecture comprobadas como tests,
  además de los contratos de `lint-imports`.
- `tests/unit/test_sin_la_marca_vieja.py`: ningún fichero del repo (salvo el
  CHANGELOG) nombra la marca anterior.
- `tests/unit/config/test_dependencias_con_hash.py`: el lock con hashes fija las mismas
  versiones que `requirements.txt`.
