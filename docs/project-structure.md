# 📂 Estructura del proyecto

> Versión 2.82.0 · actualizado el 28 de noviembre de 2026

## Convenciones

- **Módulos y ficheros**: snake_case (`quick_match/`, `envio_de_correo.py`). Conviven nombres en inglés y en castellano: el código nuevo suele nombrar las reglas en castellano (`freno_del_login.py`, `plazas_en_franjas.py`).
- **Clases**: PascalCase (`UserRepository`, `CierreDeInscripciones`).
- **Funciones y variables**: snake_case.
- **Constantes**: UPPER_SNAKE_CASE (`MAX_PLAYERS`, `HORA_DEL_CIERRE`).
- **Tests**: `test_<nombre>.py`, en una carpeta que repite la ruta de `src/`.

## Árbol de directorios

```
src/
├── config/                 # Raíz de composición y configuración global
│   ├── dependencies/       # Inyección de dependencias: un fichero por contexto
│   │                       # (usuarios, competicion, competicion_juego, campos,
│   │                       #  partida_rapida, social, soporte, comun)
│   ├── settings.py         # Variables de entorno
│   ├── database.py         # Motor y sesiones de SQLAlchemy
│   ├── mappers.py          # Arranca todos los mappers imperativos en un solo sitio
│   ├── arranque_seguro.py  # Lo que la app exige para arrancar fuera de desarrollo
│   ├── rate_limit.py  cors_config.py  csrf_config.py  sentry_config.py
│   ├── cierre_de_inscripciones.py  cierre_de_partidas_rapidas.py
│   ├── limpieza_de_sesiones.py  refresco_de_handicaps.py  clave_de_brevo_viva.py
│   │                       # Tareas en segundo plano del proceso de la API
│   └── version.py          # APP_VERSION, la que expone GET /health
│
├── modules/                # Un contexto acotado por módulo, con la misma forma salvo `support`, que es mínimo
│   ├── user/               # Cuentas, acceso, sesiones por dispositivo, hándicaps, avatares, admin
│   ├── competition/        # Torneos (formato Ryder, Stableford, Medal)
│   ├── golf_course/        # Campos, barras, hoyos, mapas de hoyos (OSM), importación RFEG
│   ├── quick_match/        # Partidas rápidas
│   ├── social/             # Amistades, perfiles, fotos, actividad y logros
│   └── support/            # Formulario de contacto
│
│   Cada módulo:
│   ├── domain/
│   │   ├── entities/        # Agregados y entidades
│   │   ├── value_objects/   # Ids, estados, reglas de validación
│   │   ├── services/        # Servicios de dominio puros
│   │   ├── repositories/    # Interfaces de repositorio y de Unit of Work
│   │   └── exceptions/ (o errors/)
│   ├── application/
│   │   ├── use_cases/       # Un caso de uso por operación
│   │   ├── services/        # Pasos compartidos por varios casos de uso
│   │   ├── ports/           # Interfaces hacia fuera (correo, RFEG, otros módulos…)
│   │   └── dto/ (dtos/ en golf_course)  mappers/
│   └── infrastructure/
│       ├── api/v1/          # Routers de FastAPI
│       └── persistence/
│           ├── sqlalchemy/  # Mappers imperativos, repositorios, Unit of Work
│           └── in_memory/   # Dobles para los tests unitarios
│
│   Carpetas propias de algunos módulos: competition/domain/policies (reglas de
│   horario: plazo y apertura de inscripciones, zona horaria del campo, draft,
│   marcadores), user/infrastructure/{security,external,static},
│   golf_course/infrastructure/{osm,importers}, social/infrastructure/adapters.
│
└── shared/                 # Núcleo compartido (no importa ningún módulo)
    ├── domain/             # Country, value objects comunes (MatchFormat, Modality,
    │                       # PlayMode, ScoringFormat, Gender…), calculadoras de
    │                       # hándicap de juego y de puntuación, eventos de seguridad
    ├── application/        # Validación, concurrencia
    └── infrastructure/
        ├── api/v1/         # country_routes
        ├── database/       # Paquete vacío (solo __init__.py); la conexión vive en src/config/database.py
        ├── http/           # Middlewares: correlation id, cabeceras de seguridad,
        │                   # límite del cuerpo, errores no controlados, Sentry…
        ├── middleware/     # CSRF
        ├── security/       # JWT, cookies, hash de tokens
        ├── email/          # Envío de correo (Mailgun → Resend → Brevo; Mailpit en local)
        ├── logging/        # Formato de logs y log de seguridad
        └── persistence/    # Base de SQLAlchemy (metadata única) y países

tests/
├── unit/                   # Sin base de datos
│   ├── modules/<módulo>/   # domain, application, infrastructure
│   ├── shared/
│   ├── config/  scripts/
│   └── architecture/       # Imports permitidos por capa, logs sin nombres, sin reloj local…
├── integration/            # Con PostgreSQL
│   ├── api/v1/             # Endpoints
│   ├── modules/<módulo>/   # Repositorios y casos de uso contra la base
│   └── test_*_migration.py # Migraciones de Alembic
├── security/               # CSRF, XSS, inyección SQL, auth bypass, rate limiting
├── fakes/                  # MockHandicapService
└── fixtures/osm/           # Datos de OpenStreetMap para los tests de mapas de hoyos
```

## Separación de responsabilidades

### Domain
- ❌ No depende de frameworks ni de infraestructura.
- ✅ Contiene las reglas de negocio puras.
- Tests: unitarios, sin base de datos.

### Application
- ❌ No contiene reglas de negocio: las delega en el dominio.
- ✅ Orquesta dominio, repositorios y puertos; llama explícitamente al puerto que produce cada efecto (ADR-050).
- Tests: unitarios con repositorios en memoria y dobles de los puertos.

### Infrastructure
- ❌ No contiene reglas de negocio.
- ✅ Implementa las interfaces del dominio y de la aplicación (repositorios, adaptadores externos, routers).
- Tests: de integración con PostgreSQL.

Las reglas de capas las comprueba `import-linter` con los contratos de `.importlinter` (job «Architecture» del CI) y `tests/unit/architecture/` (ADR-046).

## Ficheros de la raíz

- `main.py`: punto de entrada; crea la app, registra middlewares y routers y arranca las tareas en segundo plano.
- `alembic.ini`, `alembic/`: migraciones (`versions/`) y semillas (`seeds/`).
- `pytest.ini`: `asyncio_mode = auto` y `-n auto` (pytest-xdist) por defecto.
- `dev_tests.py`: ejecuta la batería completa y muestra el resultado por fichero, con un resumen final y un informe en Markdown.
- `ruff.toml`, `mypy.ini`, `.importlinter`: lint y formato, tipos y contratos de arquitectura.
- `requirements.txt` / `requirements-dev.txt`: dependencias declaradas; `requirements.lock` y `requirements-bootstrap.*`: versiones fijadas con hash para instalar.
- `docker/`: `Dockerfile`, `docker-compose.yml` y scripts del contenedor.
- `k8s/`: manifiestos y scripts del clúster local (Kind).
- `entrypoint.sh`: arranque del contenedor.
- `scripts/`: utilidades (importar campos y mapas de hoyos, SBOM, firmas GPG, congelar dependencias, SQL de roles de la base).
- `.env.example`: plantilla de variables de entorno (el `.env` no se sube).
