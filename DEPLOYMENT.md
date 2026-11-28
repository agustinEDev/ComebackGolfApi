# 🚀 Deployment Guide - Comeback Golf API

Cómo se despliega la API: en local con Docker Compose y en producción en Render. Para el
clúster local con Kind, ver [k8s/README.md](k8s/README.md); para la operación del día a
día, [docs/RUNBOOK.md](docs/RUNBOOK.md); para las variables de entorno,
[docs/MULTI_ENVIRONMENT_SETUP.md](docs/MULTI_ENVIRONMENT_SETUP.md).

---

## 🧱 La imagen

Una sola imagen para todo: [`docker/Dockerfile`](docker/Dockerfile), sobre
`python:3.14-slim` fijada por digest, con las dependencias instaladas desde
`requirements.lock` con `--require-hashes` y un usuario sin privilegios.

Al arrancar ejecuta [`entrypoint.sh`](entrypoint.sh):

1. Valida las variables obligatorias (`DATABASE_URL` y `SECRET_KEY` en Render; las de
   PostgreSQL en Docker).
2. Si hay `DATABASE_HOST`, espera a que PostgreSQL responda.
3. `python -m src.config.arranque_seguro`: si la configuración de seguridad no es
   válida, no migra ni arranca.
4. `alembic upgrade head` (con `MIGRATIONS_DATABASE_URL` si existe; si no, con
   `DATABASE_URL`).
5. `uvicorn main:app` en `PORT` (8000 por defecto), con `--reload` solo si
   `ENVIRONMENT=development`. La credencial de migraciones se retira del entorno del
   proceso antes de arrancar.

---

## 🐳 Local: Docker Compose

Servicios de [`docker/docker-compose.yml`](docker/docker-compose.yml): `db`
(PostgreSQL 15), `app` (la API, con recarga en caliente de `src/`, `alembic/` y
`scripts/`) y `mailpit` (buzón local: ningún correo sale a nadie).

```bash
cp docker/.env.example docker/.env      # rellenar los valores
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build
docker compose -f docker/docker-compose.yml --env-file docker/.env logs -f app
```

| Servicio | Dirección |
|----------|-----------|
| API | `http://localhost:8000` (`DOCKER_APP_PORT`; 8001 si no se define) |
| Documentación | `http://localhost:8000/docs` (HTTP Basic: `DOCS_USERNAME` / `DOCS_PASSWORD`) |
| PostgreSQL | `localhost:5433` (`DOCKER_DATABASE_PORT`) |
| Mailpit | `http://127.0.0.1:8025` |

Las migraciones se aplican solas al arrancar. A mano:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env exec app alembic current
docker compose -f docker/docker-compose.yml --env-file docker/.env exec app alembic upgrade head
```

Más detalle en [docker/README.md](docker/README.md).

---

## ☁️ Producción: Render

- **Servicios:** una base PostgreSQL 15 y un *Web Service* con runtime Docker
  (`docker/Dockerfile`), en la misma región.
- **Despliegue:** automático cuando se mueve `main` (GitFlow: `develop` →
  `release/*` → `main`). Render construye la imagen y arranca `entrypoint.sh`.
- **Dominio:** `https://api.comebackgolf.com`.

### Variables de entorno

Se definen en el panel de Render. La lista completa y comentada está en
[`.env.example`](.env.example); las imprescindibles:

```env
ENVIRONMENT=production
DATABASE_URL=<URL interna de la base de Render>
SECRET_KEY=<aleatoria, 32 bytes o más>      # python -c "import secrets; print(secrets.token_urlsafe(32))"
FRONTEND_URL=https://www.comebackgolf.com
FRONTEND_ORIGINS=https://www.comebackgolf.com
COOKIE_DOMAIN=.comebackgolf.com
DOCS_USERNAME=<usuario>
DOCS_PASSWORD=<contraseña segura>

MAILGUN_API_KEY=<clave>
MAILGUN_DOMAIN=comebackgolf.com
MAILGUN_FROM_EMAIL="Comeback Golf <noreply@comebackgolf.com>"
MAILGUN_API_URL=https://api.eu.mailgun.net/v3
CONTACT_EMAIL=hola@comebackgolf.com

# Opcionales
MIGRATIONS_DATABASE_URL=<credencial del dueño de la base, solo para migrar>
RESEND_API_KEY=<respaldo de Mailgun, clave de solo envío>
BREVO_API_KEY=<último respaldo; nunca recibe correos con token ni avisos de seguridad>
SENTRY_DSN=<DSN del proyecto>
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.05
HANDICAP_REFRESH_ENABLED=true
```

**Lo que hace que la app no arranque en producción** (a propósito):

- `SECRET_KEY` ausente, de ejemplo o de menos de 32 bytes (ADR-047).
- Sin `MAILGUN_API_KEY`, con `EMAIL_TRANSPORT` distinto de `mailgun` o con una URL de
  proveedor que no sea `https://`.
- Sin `FRONTEND_ORIGINS`, o con `*`.
- `COOKIE_DOMAIN`, `GOOGLE_REDIRECT_URI` o `FRONTEND_URL` mal escritos, o `TESTING`
  puesto fuera de desarrollo.

### Comprobar el despliegue

`/health` devuelve la versión y el commit que están corriendo; es la forma de confirmar
que una release ha llegado:

```bash
curl -s https://api.comebackgolf.com/health
# {"status":"ok","version":"2.82.2","commit":"<sha>","branch":"main","environment":"production"}
```

El `commit` lo inyecta Render (`RENDER_GIT_COMMIT`); compararlo con el de la release.

### Problemas frecuentes

| Síntoma | Qué mirar |
|---------|-----------|
| El despliegue se para antes de migrar | El mensaje de `arranque_seguro` en los logs: nombra la variable insegura |
| Fallan las migraciones | `DATABASE_URL` / `MIGRATIONS_DATABASE_URL` y que la credencial sea la del dueño de las tablas |
| Errores de CORS | `FRONTEND_ORIGINS` con el origen exacto, esquema incluido |
| Enlaces de correo al sitio equivocado | `FRONTEND_URL` y `COOKIE_DOMAIN` (ADR-054, ADR-055) |
| Un paquete del sistema con arreglo sigue en la imagen | Render reutiliza su caché de capas: *Manual Deploy → Clear build cache & deploy* ([RUNBOOK](docs/RUNBOOK.md)) |

---

## 🔒 Checklist de producción

- [ ] `ENVIRONMENT=production`
- [ ] `SECRET_KEY` aleatoria (32 bytes o más)
- [ ] `DOCS_USERNAME` y `DOCS_PASSWORD` propios
- [ ] `DATABASE_URL` con la URL interna de Render
- [ ] `FRONTEND_URL`, `FRONTEND_ORIGINS` y `COOKIE_DOMAIN` del dominio real
- [ ] Mailgun configurado (y, si se quiere, Resend y Brevo de respaldo)
- [ ] Base y API en la misma región
- [ ] `/health` responde con la versión y el commit esperados

---

## 🔄 CI/CD

Cada PR y cada push a las ramas largas pasa por
[`.github/workflows/ci_cd_pipeline.yml`](.github/workflows/ci_cd_pipeline.yml): lint,
tipos, contratos de arquitectura, contrato de la API, Semgrep, Bandit, pip-audit,
Gitleaks, commits firmados, tests unitarios, de integración y de seguridad en Python
3.12 y 3.14, construcción de la imagen, arranque como en Render y Trivy. Detalle en
[docs/ci-cd/PIPELINE_GUIDE.md](docs/ci-cd/PIPELINE_GUIDE.md).
