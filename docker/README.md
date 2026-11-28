# 🐳 Docker Compose - Comeback Golf API

Entorno local ligero con Docker Compose: la API (con recarga en caliente), PostgreSQL y un buzón de correo local (Mailpit). Para el entorno completo con frontend, ver el [entorno de Kubernetes](../k8s/README.md).

## Puesta en marcha

Desde la raíz del repositorio:

1. **Variables de entorno** (`docker/.env` es obligatorio: sin él, Compose no arranca):
   ```bash
   cp docker/.env.example docker/.env
   # Edita docker/.env con tus valores
   ```

2. **Arrancar los servicios**:
   ```bash
   docker compose -f docker/docker-compose.yml --env-file docker/.env up -d
   ```
   `--env-file docker/.env` hace que Compose interpole también las variables de puerto (`DOCKER_DATABASE_PORT`, `DOCKER_APP_PORT`).

3. **Comprobar**:
   ```bash
   docker compose -f docker/docker-compose.yml --env-file docker/.env ps
   curl http://localhost:8000/health
   ```

Las **migraciones se aplican solas**: el `entrypoint.sh` de la imagen ejecuta `alembic upgrade head` antes de arrancar `uvicorn`. Para lanzarlas a mano:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env exec app alembic upgrade head
```

## Servicios

| Servicio | Imagen | En tu máquina |
|---|---|---|
| `db` | `postgres:15-alpine` | `localhost:${DOCKER_DATABASE_PORT}` (5433 por defecto) |
| `app` | se construye desde `docker/Dockerfile` | `localhost:${DOCKER_APP_PORT}` (8000 en `.env.example`; 8001 si no se define) |
| `mailpit` | `axllent/mailpit` | http://localhost:8025 (solo `127.0.0.1`) |

- **API**: `/health`, y `/docs`, `/redoc` y `/openapi.json` protegidos con HTTP Basic (`DOCS_USERNAME` / `DOCS_PASSWORD`; si están vacíos, la documentación no está disponible).
- **Recarga en caliente**: se montan solo `src/`, `alembic/` y `scripts/` (de solo lectura) y, con `ENVIRONMENT=development`, `uvicorn` arranca con `--reload`. `main.py` y `alembic.ini` van dentro de la imagen: si cambian, `docker compose -f docker/docker-compose.yml build app`.
- **Correos**: por defecto van a Mailpit y no se entregan (`EMAIL_TRANSPORT` vacío = `mailpit`). Con `EMAIL_TRANSPORT=mailgun` y una `MAILGUN_API_KEY` real se mandan de verdad; `RESEND_API_KEY` y `BREVO_API_KEY` son los respaldos de Mailgun (vacíos = sin respaldo).

## Configuración

Las variables están en `docker/.env` (plantilla: `docker/.env.example`):

| Variable | Para qué |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Base de datos (obligatorias) |
| `DOCKER_DATABASE_PORT`, `DOCKER_APP_PORT` | Puertos publicados en tu máquina |
| `SECRET_KEY` | Firma de los JWT (obligatoria; fuera de desarrollo, la app no arranca con la de ejemplo ni con menos de 32 bytes) |
| `ENVIRONMENT`, `PORT`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Aplicación |
| `DOCS_USERNAME`, `DOCS_PASSWORD` | Acceso a la documentación de la API |
| `MAILGUN_*`, `EMAIL_TRANSPORT`, `RESEND_API_KEY`, `BREVO_API_KEY` | Correo |
| `FRONTEND_URL` | Base de los enlaces de los correos (`http://localhost:5173` por defecto) |
| `SENTRY_DSN` y tasas de muestreo | Sentry (vacío = desactivado) |

**Docker y Kind a la vez**: el Kind publica la API en el `8000`. Si necesitas los dos, pon `DOCKER_APP_PORT=8001` en `docker/.env`. PostgreSQL no choca: 5433 aquí, 5434 en el Kind.

## Comandos útiles

```bash
COMPOSE="docker compose -f docker/docker-compose.yml --env-file docker/.env"

# Logs
$COMPOSE logs -f app

# Reiniciar reconstruyendo la imagen
$COMPOSE up -d --build

# Consola de PostgreSQL
$COMPOSE exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# Parar
$COMPOSE down

# Parar y BORRAR los datos (volúmenes postgres_data y app_logs)
$COMPOSE down -v
```

## Problemas habituales

**`port is already allocated` en el 8000**
- Seguramente el Kind está encendido: `kind get clusters`. Apágalo (`k8s/scripts/destroy-cluster.sh`) o usa `DOCKER_APP_PORT=8001`.
- Si no, mira quién lo ocupa: `lsof -i :8000`.

**`port is already allocated` en el 5433**
- Otro proceso usa ese puerto: `lsof -i :5433`, o cambia `DOCKER_DATABASE_PORT`.

**`MISSING_USER`, `MISSING_PASSWORD`, `MISSING_DB` o `MISSING_SECRET_KEY`**
- Falta `docker/.env` o alguna variable obligatoria. Los valores `MISSING_*` solo existen para que el YAML sea válido: los scripts de validación los rechazan y el contenedor no arranca (ver [`scripts/README.md`](scripts/README.md)).
