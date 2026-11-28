# 🔍 Docker Validation Scripts

Scripts de validación *fail-fast* para que un contenedor no arranque con variables de entorno que faltan, en lugar de fallar más tarde con errores confusos.

## 📋 Scripts disponibles

### 1. `validate-postgres-env.sh`

**Lo usa** el servicio `db` de `docker/docker-compose.yml` como `entrypoint`: valida las variables y, si están bien, cede el control al arranque normal de PostgreSQL.

**Variables obligatorias:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.

**Comportamiento:**
- ✅ Todas presentes: PostgreSQL arranca normalmente.
- ❌ Falta alguna (vacía o con el valor `MISSING_*` que pone Compose por defecto): imprime qué falta y cómo configurarlo, y sale con código 1 (el contenedor no arranca).

### 2. `validate-app-env.sh`

Valida las variables de la API antes de arrancar FastAPI.

**Obligatorias:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `SECRET_KEY`.
**Recomendadas (solo avisa):** `MAILGUN_API_KEY`, `DOCS_USERNAME`, `DOCS_PASSWORD`.

Compose lo monta en el contenedor `app` (`/validate-app-env.sh`), pero **no es su entrypoint**: el servicio arranca con el `entrypoint.sh` de la imagen, que hace su propia validación (variables obligatorias y valores `MISSING_*`), espera a PostgreSQL, aplica las migraciones y lanza `uvicorn`. Se puede ejecutar a mano para comprobar un entorno:

```bash
docker compose -f docker/docker-compose.yml --env-file docker/.env exec app sh /validate-app-env.sh
```

### 3. `test-validation.sh`

Prueba de humo de `validate-postgres-env.sh`: comprueba que falla sin `POSTGRES_USER` y que pasa con todas las variables definidas.

## 🧪 Ejecutar las pruebas

Desde la raíz del repositorio:

```bash
./docker/scripts/test-validation.sh
```

`validate-postgres-env.sh` está pensado para ejecutarse **dentro del contenedor** `db`:
si las variables están bien, termina con `exec docker-entrypoint.sh postgres`, que fuera
de la imagen de PostgreSQL no existe. Para probarlo en tu máquina, usa
`test-validation.sh`, que sustituye ese arranque por uno de mentira.

## 🔧 Configuración

Las variables salen de **`docker/.env`** (el `env_file` de Compose es relativo a `docker/docker-compose.yml`). Créalo desde la plantilla:

```bash
cp docker/.env.example docker/.env
# Edita docker/.env con tus valores
```

## 📝 Notas técnicas

- Los scripts usan **shell POSIX** (`/bin/sh`), compatible con la imagen Alpine de PostgreSQL.
- Se montan en **solo lectura** (`:ro`).
- Los valores por defecto `MISSING_*` de `docker-compose.yml` solo existen para que la interpolación sea válida; los validadores los tratan como ausentes.

## 🔗 Referencias

- [`../docker-compose.yml`](../docker-compose.yml): servicios
- [`../.env.example`](../.env.example): plantilla de variables
- [`../README.md`](../README.md): guía de Docker Compose
