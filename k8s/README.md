# 🚀 Entorno local con Kubernetes (Kind)

Este documento explica cómo levantar, gestionar y apagar el entorno local de **Comeback Golf** sobre Kubernetes. El detalle de cada script está en [`scripts/README.md`](scripts/README.md).

## 🧐 Qué es y para qué sirve

Usamos **[Kind](https://kind.sigs.k8s.io/) (Kubernetes in Docker)**: un clúster de Kubernetes de un solo nodo que corre dentro de Docker. Levanta juntos la API, el frontend, PostgreSQL y un buzón de correo local (Mailpit), cada uno en su pod, para probar la aplicación completa en tu máquina.

| Recurso | Valor |
|---|---|
| Clúster | `comebackgolf-cluster` (contexto `kind-comebackgolf-cluster`) |
| Namespace | `comebackgolf` |
| Deployments | `comebackgolf-api` (contenedor `fastapi`), `comebackgolf-web` (contenedor `nginx`), `postgres`, `mailpit` |
| Imágenes | `agustinedev/comebackgolf-api:latest` y `agustinedev/comebackgolf-web:latest`, construidas en local y cargadas con `kind load` (no se suben a ningún registro); `postgres:15`; `axllent/mailpit` |
| Base de datos | `comebackgolf_dev`, en el PVC `postgres-pvc` |

Cada deployment tiene **una réplica**: es un entorno de pruebas local, no un clúster de producción.

---

## ✅ Prerrequisitos

- **Docker Desktop** (o Docker Engine) arrancado: `docker info`
- **kubectl**: `kubectl version --client`
- **Kind**: `kind version`
- El repositorio del frontend clonado **junto a este**, con el nombre `ComebackGolfWeb`:

```text
repos/
├── ComebackGolfApi/   ← este repositorio
└── ComebackGolfWeb/   ← el frontend (los scripts lo buscan en ../ComebackGolfWeb)
```

---

## 🚀 Flujo de trabajo

Los scripts calculan sus rutas solos; lo habitual es lanzarlos desde `k8s/`.

1. **Primer despliegue** (crea el clúster y despliega todo):
   ```bash
   cd k8s
   ./scripts/deploy-cluster.sh
   ```
2. **Abrir la aplicación** (los puertos ya están mapeados a `localhost`):
   - Frontend: http://localhost:8080
   - API: http://localhost:8000 (`/health`, y `/docs` con las credenciales de `DOCS_USERNAME`/`DOCS_PASSWORD`)
3. **Ver el estado**:
   ```bash
   ./scripts/cluster-status.sh
   ```
4. **Al terminar**, borra el clúster para liberar memoria:
   ```bash
   ./scripts/destroy-cluster.sh
   ```

Las imágenes se construyen con la caché de Docker; `NO_CACHE=1 ./scripts/deploy-cluster.sh` (también en `deploy-api.sh`, `deploy-front.sh` y `deploy-db.sh`) construye desde cero. Antes de construir, `deploy-cluster.sh`, `deploy-api.sh` y `deploy-front.sh` muestran **de qué rama** sale cada imagen (`rama-de-la-imagen.sh`), porque construyen desde el árbol de trabajo tal y como esté.

### Resumen de scripts

| Script | Qué hace |
|---|---|
| `deploy-cluster.sh` | **(Principal)** Crea el clúster si no existe y despliega PostgreSQL, Mailpit, la API y el frontend. Si el clúster ya existe, solo lo borra si escribes su nombre. |
| `deploy-api.sh [tag]` | Reconstruye la imagen de la API, la carga en Kind y reinicia el deployment. |
| `deploy-front.sh [tag]` | Lo mismo para el frontend (desde `../ComebackGolfWeb`). |
| `deploy-db.sh [--force]` | Reconstruye la imagen de la API, hace backup de la base, reinicia PostgreSQL y aplica las migraciones de Alembic. |
| `restart-cluster.sh [--api\|--front\|--db\|--all]` | Reaplica ConfigMaps y Secrets y reinicia los deployments sin reconstruir imágenes (por defecto, API y frontend). |
| `restore-db.sh` | Restaura la base desde un backup de `k8s/backups/` y aplica las migraciones. |
| `cluster-status.sh` | Informe del clúster: nodos, pods, servicios, almacenamiento, eventos y health checks. |
| `destroy-cluster.sh` | **(Irreversible)** Borra el clúster y todos sus datos; opcionalmente, las imágenes `kindest/node`. |
| `check_config.py` | Comprueba la configuración que lee la app (`src/config/settings.py`) para el entorno detectado. |
| `rama-de-la-imagen.sh` | Auxiliar: lo cargan los scripts de despliegue para avisar de la rama. |

---

## 🔐 Secrets

`k8s/api-secret.yaml` está **versionado en git** y solo contiene valores de ejemplo, nunca reales (el repositorio es público).

Para usar credenciales reales en local (por ejemplo, para mandar un correo de verdad):

1. Crea `k8s/api-secret.local.yaml` (está en `.gitignore`) con la misma estructura que `api-secret.yaml`.
2. Rellena ahí los valores reales, copiándolos directamente del panel del proveedor, sin pasar por ningún fichero versionado.
3. `deploy-cluster.sh` y `restart-cluster.sh` aplican `api-secret.local.yaml` si existe, en lugar de `api-secret.yaml`.

⚠️ Si un valor real llega a `api-secret.yaml` por error, rótalo de inmediato en el proveedor: el fichero es público en cuanto se sube.

---

## 📬 Correos

**El Kind no entrega correos**: la API los manda a **Mailpit** (`k8s/mailpit.yaml`, `EMAIL_TRANSPORT=mailpit` en `api-configmap.yaml`), un buzón local que los guarda sin enviarlos. Así las pruebas no gastan el cupo de Mailgun de producción.

- **Verlos** (HTML, enlaces y tokens):
  ```bash
  kubectl port-forward -n comebackgolf svc/mailpit-service 8025:8025
  ```
  y abrir http://localhost:8025. Se guardan en memoria: un reinicio del pod los vacía.
- **Mandar uno de verdad** (por ejemplo, para verlo en el móvil), solo a propósito y solo a tu propia dirección:
  ```bash
  kubectl set env deployment/comebackgolf-api -n comebackgolf EMAIL_TRANSPORT=mailgun
  # ... la prueba ...
  kubectl set env deployment/comebackgolf-api -n comebackgolf EMAIL_TRANSPORT-
  ```
  Al quitarlo vuelve el valor del ConfigMap (`mailpit`). Necesita la `MAILGUN_API_KEY` real en `api-secret.local.yaml`.
- En **producción** la app no arranca con otro valor que `mailgun`.

---

## 🗃️ Base de datos

### Backups
- **Automáticos:** `deploy-db.sh` guarda un `pg_dump` en `k8s/backups/db_backup_AAAAMMDD_HHMMSS.sql` antes de tocar nada.
- **Manuales:** ver «Manual Backup» en [`scripts/README.md`](scripts/README.md).
- Los `.sql` de `k8s/backups/` están en `.gitignore`: nunca se suben.

### Restauración
`restore-db.sh` lista los backups de `k8s/backups/`, pide el fichero, avisa de que **se borrarán todos los datos actuales**, recrea la base `comebackgolf_dev`, la restaura con `psql`, aplica las migraciones y reinicia la API.

```bash
./scripts/restore-db.sh
```

---

## 🌐 Acceso a los servicios

`kind-config.yaml` mapea los NodePorts del clúster a `localhost` (solo `127.0.0.1`, no a la red local). No hace falta `port-forward` salvo para Mailpit.

| Servicio | En tu máquina | Service y NodePort |
|---|---|---|
| Frontend | http://localhost:8080 | `comebackgolf-web-service` → 32315 |
| API | http://localhost:8000 | `comebackgolf-api-service` → 30321 |
| PostgreSQL | `localhost:5434` | `postgres-service` → 30432 |
| Mailpit | http://localhost:8025 (con `port-forward`) | `mailpit-service` (ClusterIP) |

Los mapeos se aplican al **crear** el clúster: si cambias `kind-config.yaml`, hay que recrearlo.

---

## 🛠️ Problemas habituales

- **`Permission denied` al lanzar un script:**
  ```bash
  chmod +x k8s/scripts/*.sh
  ```
- **Pods en `CrashLoopBackOff` o `Error`:** `./scripts/cluster-status.sh` da la visión general; después, los logs:
  ```bash
  kubectl logs -n comebackgolf deployment/comebackgolf-api --tail=50
  ```
- **El puerto `8080`, `8000` o `5434` ya está en uso:** otro servicio (o un `port-forward` antiguo) lo ocupa. `lsof -i :8080` dice cuál. El `docker-compose` de `docker/` puede usar también el `8000`: ver [`docker/README.md`](../docker/README.md).
- **No encuentra el frontend:** `deploy-cluster.sh` y `deploy-front.sh` esperan el repositorio en `../ComebackGolfWeb` (ver «Prerrequisitos»).
