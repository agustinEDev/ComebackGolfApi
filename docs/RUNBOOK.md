# 🚀 Runbook - Comeback Golf API

Operación del día a día: dónde corre cada cosa, cómo mirar su estado y qué hacer
cuando algo falla.

| Entorno | Dónde | Cómo se despliega |
| --- | --- | --- |
| **Producción** | Render (API en Docker + PostgreSQL 15), `https://api.comebackgolf.com` | Solo al mover `main`: Render construye `docker/Dockerfile` y arranca `entrypoint.sh` (comprueba la configuración de seguridad → `alembic upgrade head` → uvicorn) |
| **Kind (local)** | Clúster Kubernetes local `comebackgolf-cluster`, namespace `comebackgolf` | `k8s/scripts/*.sh` (ver [k8s/README.md](../k8s/README.md)) |
| **Docker Compose (local)** | `docker/docker-compose.yml`: `db`, `app`, `mailpit` | `docker compose` (ver [docker/README.md](../docker/README.md)) |

---

## Producción (Render)

### ¿Qué versión está desplegada?

```bash
curl -s https://api.comebackgolf.com/health
# {"status":"ok","version":"2.82.0","commit":"<sha>","branch":"main","environment":"production"}
```

`version` sale de `src/config/version.py` y `commit`/`branch` de las variables que
Render inyecta (`RENDER_GIT_COMMIT`, `RENDER_GIT_BRANCH`). Comparar el `commit` con el
de la release es la forma de saber si el despliegue ya llegó.

### Paquetes del sistema de la imagen al día (INF-02)

Render construye la imagen con su propia caché de capas y no pasa `APT_REFRESH` (el CI le
pasa el día, Render nada): la capa del `apt-get upgrade` del Dockerfile se queda como la
primera vez que la construyó. Hacer **Manual Deploy → «Clear build cache & deploy»** en el
servicio del backend cuando:

- cambie `docker/Dockerfile` (digest de la imagen base incluido), y
- Trivy (pestaña Security o la puerta del CI) avise de un paquete del sistema con arreglo.

Es el mismo despliegue de siempre, solo que sin caché: tarda unos minutos más.

---

## Kind (local)

```bash
./k8s/scripts/deploy-cluster.sh        # Crear el clúster y desplegarlo todo
./k8s/scripts/deploy-api.sh [version]  # Reconstruir y desplegar el backend
./k8s/scripts/deploy-front.sh [version]
./k8s/scripts/deploy-db.sh [--force]   # PostgreSQL + migraciones
./k8s/scripts/cluster-status.sh        # Estado del clúster
./k8s/scripts/restart-cluster.sh
./k8s/scripts/restore-db.sh            # Restaurar una copia de k8s/backups/
./k8s/scripts/destroy-cluster.sh
```

Puertos en el ordenador (de `k8s/kind-config.yaml`): API `localhost:8000`, web
`localhost:8080`, PostgreSQL `localhost:5434`.

```bash
# Pods y eventos
kubectl get pods -n comebackgolf
kubectl describe pod -n comebackgolf <pod>
kubectl get events -n comebackgolf --sort-by='.lastTimestamp'

# Logs
kubectl logs -f -n comebackgolf deployment/comebackgolf-api --tail=100
kubectl logs -n comebackgolf <pod> --previous

# Shell y base de datos
kubectl exec -it -n comebackgolf deployment/comebackgolf-api -- bash
kubectl exec -it -n comebackgolf deployment/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# Migraciones
kubectl exec -it -n comebackgolf deployment/comebackgolf-api -- alembic current
kubectl exec -it -n comebackgolf deployment/comebackgolf-api -- alembic upgrade head

# Reinicio o vuelta atrás
kubectl rollout restart deployment/comebackgolf-api -n comebackgolf
kubectl rollout undo deployment/comebackgolf-api -n comebackgolf

# Servicios
kubectl get svc,endpoints -n comebackgolf    # comebackgolf-api-service, comebackgolf-web-service, postgres-service, mailpit-service
kubectl get pvc -n comebackgolf              # postgres-pvc
```

El log de auditoría de seguridad se escribe en `logs/security_audit.log` dentro del
contenedor de la API.

---

## Docker Compose (local)

Desde la raíz del repo, con `docker/.env` creado a partir de `docker/.env.example`:

```bash
COMPOSE="docker compose -f docker/docker-compose.yml --env-file docker/.env"

$COMPOSE up -d --build            # db + app + mailpit (la app migra al arrancar)
$COMPOSE ps
$COMPOSE logs -f --tail=100 app
$COMPOSE restart app
$COMPOSE exec app alembic current
$COMPOSE exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
$COMPOSE down                     # down -v borra también la base
```

| Servicio | URL |
| --- | --- |
| API | `http://localhost:8000` (`DOCKER_APP_PORT`; 8001 si no se define) |
| Documentación | `http://localhost:8000/docs` (HTTP Basic con `DOCS_USERNAME` / `DOCS_PASSWORD`) |
| PostgreSQL | `localhost:5433` (`DOCKER_DATABASE_PORT`) |
| Mailpit (correos de prueba) | `http://127.0.0.1:8025` |

### Copias

```bash
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
gunzip -c backup_<fecha>.sql.gz | $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

---

## Usuario de la API sin permisos de estructura (DB-01)

La API puede entrar con su propio rol (el que crea `scripts/db/rol_de_la_api.sql`), que solo
lee y escribe filas; las migraciones del arranque entran con el dueño de la base. Sin
`MIGRATIONS_DATABASE_URL` todo funciona como antes (las migraciones usan `DATABASE_URL`).

Ninguna contraseña va en la línea de órdenes (quedaría en el historial y en `ps`): psql la
pide en su aviso.

1. **Entrar como el dueño.** Con los datos de la URL actual de la API, SIN la contraseña:
   `psql "host=<host> port=5432 dbname=<base> user=<usuario> sslmode=require"`. Sin psql
   instalado: `docker run --rm -it -v "$PWD/scripts/db:/s:ro" postgres:15 psql "<lo mismo>"`.
2. **Comprobar quién es el dueño.** `SELECT current_user;` tiene que dar el dueño de las
   tablas (`SELECT tableowner FROM pg_tables WHERE tablename = 'users';`). Si no
   coinciden, parar: los permisos por defecto serían de otro usuario.
3. **Crear el usuario.** `\set ON_ERROR_STOP on` y luego `\i scripts/db/rol_de_la_api.sql`
   (o `\i /s/rol_de_la_api.sql` con Docker). Va en una transacción: si algo falla no
   cambia nada. Se puede repetir y se niega si la base no está migrada. Después,
   `SET password_encryption = 'scram-sha-256';` y `\password <rol de la API>` (sin el SET,
   Render la guarda en MD5: DB-R3-02). El script también quita al rol de solo lectura del
   informe la lectura automática de las tablas futuras (DB-03); sus permisos sobre las de
   hoy los recorta `scripts/db/rol_de_n8n.sql` (sección siguiente).
4. **Render, primero sin cambiar nada:** añadir `MIGRATIONS_DATABASE_URL` con el valor
   ACTUAL de `DATABASE_URL` y desplegar. Todo sigue igual.
5. **Render, el cambio:** `DATABASE_URL` pasa a
   `postgresql://<rol de la API>:<contraseña>@<mismo host>:5432/<misma base>`, con la
   contraseña codificada para URL si lleva `@ : / # ? %` (mejor elegir una sin ellos), y
   desplegar. Mirar `/health` y entrar en la app. Antes, todo esto en el Kind.
6. **Volver atrás:** `DATABASE_URL` con el valor de `MIGRATIONS_DATABASE_URL` y desplegar.

Las tablas que creen las migraciones futuras ya le dan permiso al rol de la API solas (paso
4 del script). Si la copia diaria externa entra con un rol de solo lectura, ese rol tiene
que leer también las tablas futuras por un permiso por defecto del dueño: comprobarlo antes
del cambio con `\ddp` (tiene que salir `<rol de la copia>=r` en las tablas del dueño); si no
sale, las copias no llevarían las tablas nuevas.

## n8n solo lee lo del informe (DB-01)

El informe semanal de n8n entra con un rol de solo lectura. `scripts/db/rol_de_n8n.sql` le
quita cualquier permiso de tabla entera y le deja solo las columnas que lee la consulta del
informe, solo lectura y con tiempos límite. El script dice qué columnas son; si el informe
pasa a leer otra, se añade allí.

1. **Entrar como el dueño**, como en la sección anterior (pasos 1 y 2).
2. `\set ON_ERROR_STOP on` y `\i scripts/db/rol_de_n8n.sql`. Va en una transacción y
   comprueba el resultado antes del `COMMIT`: si sale «conserva permisos de tabla entera»,
   esos permisos los dio otro usuario (el `REVOKE` solo quita los que dio quien lo
   ejecuta) y no ha cambiado nada; ejecutarlo como ese usuario.
3. **Mirar las consultas del final:** ninguna tabla entera legible, solo las columnas que
   lista el script, `false` en hashes, correos, `refresh_tokens` y `password_history`, y
   los cuatro ajustes del rol (`default_transaction_read_only=on`, `statement_timeout=30s`,
   `idle_in_transaction_session_timeout=60s`, `lock_timeout=5s`).
4. **Probar el informe sin mandarlo:** en n8n, abrir el flujo del informe y ejecutar solo
   el nodo que lee la base. Tiene que devolver una fila con los números.
5. **Volver atrás no hace falta para el informe:** si el paso 4 falla con «permission
   denied for ... column X», el informe ha pasado a leer una columna nueva; se añade al
   script (pasos 3 y 5) y se vuelve a ejecutar. Nunca devolver la tabla entera: un
   `GRANT SELECT ON public.users` vuelve a dar el hash, el correo y el token de reseteo.

## Restaurar producción (DB-03)

Para cuando la base de Render se pierde o se corrompe. La copia diaria externa (fuera del
repo) es `pg_dump -Fc --no-owner --no-privileges`: trae tablas, datos y la versión de
Alembic, pero **ni dueños, ni permisos, ni usuarios, ni sus ajustes**. Restaurarla sin más
deja a la API, a la copia y al informe sin poder leer nada. El orden importa.

Ninguna contraseña va en la línea de órdenes: psql y pg_restore la piden en su aviso.

1. **Parar las escrituras.** En Render, suspender el servicio de la API: lo que se
   escriba mientras tanto se perdería al restaurar.
2. **Elegir la copia.** La más reciente que esté bien: `pg_restore --list <copia>.dump |
   grep -c 'TABLE DATA'` tiene que dar el mismo número de tablas que la base de origen
   (el que tenga en la última migración).
3. **La base de destino.** Si la de Render sigue viva, usar la misma (pasos 4 en adelante
   sobre ella). Si hay que crear otra: Postgres **15**, misma región; su usuario por
   defecto será el nuevo dueño.
4. **Restaurar como el dueño**, sin dueños ni permisos de la copia:
   `pg_restore --no-owner --no-privileges --clean --if-exists -d "host=<host> port=5432
   dbname=<base> user=<dueño> sslmode=require" <copia>.dump`. Con `--clean` borra lo que
   haya antes de cargar; en una base nueva no hace falta. Tiene que acabar sin errores
   (los avisos de «does not exist» del `--clean` en una base vacía no lo son).
5. **Comprobar la versión del esquema.** `SELECT version_num FROM alembic_version;` tiene
   que ser la de la release desplegada. Si es anterior, migrar AHORA, antes del paso 6:
   `MIGRATIONS_DATABASE_URL=<la del dueño> alembic upgrade head` desde el repo en la
   versión desplegada (los scripts del paso 6 dan permisos sobre columnas que una copia
   vieja puede no tener, y pararían). Si es posterior, la API desplegada no entiende el
   esquema: desplegar la release que corresponde.
6. **Los usuarios y sus permisos**, en psql como el dueño, con `\set ON_ERROR_STOP on` y
   `SET password_encryption = 'scram-sha-256';` antes de cualquier `\password` (DB-R3-02):
   - `\i scripts/db/rol_de_la_api.sql` (sección «Usuario de la API sin permisos de
     estructura»). En una base nueva el rol de la API no existe y se crea: solo entonces,
     `\password <rol de la API>`. En la misma base de antes NO cambiar la contraseña: la
     `DATABASE_URL` de Render sigue con la de siempre (si se cambia, cambiarla allí).
   - En una base nueva, el rol de solo lectura del informe tampoco existe y el script no
     lo crea: antes, `CREATE ROLE <rol del informe> LOGIN;` y `\password <rol del informe>`,
     y poner esa contraseña en la conexión de n8n. Después, `\i scripts/db/rol_de_n8n.sql`
     (sección «n8n solo lee lo del informe»).
   - `\i scripts/db/ajustes_de_la_base.sql`: tiempos límite del rol de la API, sin
     tablas temporales ni creación en `public` para nadie más.
   - El rol de solo lectura de la copia (no tiene script), con `<rol de la copia>` en
     lugar del nombre: `GRANT CONNECT ON DATABASE <base> TO <rol de la copia>;`,
     `GRANT USAGE ON SCHEMA public TO <rol de la copia>;`, `GRANT SELECT ON ALL TABLES IN
     SCHEMA public TO <rol de la copia>;`, `GRANT SELECT ON ALL SEQUENCES IN SCHEMA public
     TO <rol de la copia>;`, `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON
     TABLES TO <rol de la copia>;` y `ALTER ROLE <rol de la copia> SET
     default_transaction_read_only = on;`. En una base nueva, crearlo antes con
     `CREATE ROLE <rol de la copia> LOGIN` y `\password <rol de la copia>`.
7. **Render y el resto.** Si la base es nueva: `DATABASE_URL` con el rol de la API y
   `MIGRATIONS_DATABASE_URL` con el dueño, los dos al host nuevo; la URL del rol de la
   copia, donde la lea la copia diaria externa; y la conexión de n8n. Reanudar la API.
8. **Comprobar.** `curl https://api.comebackgolf.com/health`, entrar en la app y ver un
   torneo. Lanzar la copia diaria externa a mano: tiene que acabar bien. Ejecutar en n8n
   solo el nodo del informe que lee la base.

**Pendiente:** probarlo entero una vez contra una base de usar y tirar (la auditoría lo
pide). La restauración de los datos ya se probó el 17 oct 2026 (86 146 filas idénticas);
los pasos 6 y 7 no.
