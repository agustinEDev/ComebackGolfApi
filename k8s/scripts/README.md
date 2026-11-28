# 🛠️ Kubernetes Scripts - Comeback Golf

Automation scripts for the local Kind cluster. For the overview (prerequisites, ports, secrets, emails), see the [Kubernetes guide](../README.md).

All scripts work out their own paths, so they can be run from `k8s/` (the usual place) or from the repository root. They all target:

| Setting | Value |
|---|---|
| Cluster | `comebackgolf-cluster` |
| Namespace | `comebackgolf` |
| API deployment | `comebackgolf-api` (container `fastapi`, image `agustinedev/comebackgolf-api`) |
| Frontend deployment | `comebackgolf-web` (container `nginx`, image `agustinedev/comebackgolf-web`) |
| Database | deployment `postgres`, database `comebackgolf_dev` |
| Frontend source | `../ComebackGolfWeb`, next to this repository |

Images are built locally and loaded into the cluster with `kind load docker-image`; nothing is pushed to a registry. Builds use the Docker cache; set `NO_CACHE=1` to build from scratch (`--no-cache --pull`).

---

## 📜 Available Scripts

### 1. `deploy-cluster.sh` - Full Cluster Deployment

Deploys the whole application with a single command. Run it with `./`, never with `source`.

```bash
./scripts/deploy-cluster.sh
```

**What it does:**

- ✅ Checks Docker, kubectl and Kind, and that Docker is running
- ✅ Shows which branch each image will be built from (`rama-de-la-imagen.sh`)
- ✅ Creates the Kind cluster from `kind-config.yaml`. If it already exists, it is only deleted and recreated when you **type its name** (the database goes with it); pressing Enter reuses it
- ✅ Applies the namespace, ConfigMaps and the Secret (`api-secret.local.yaml` if present, otherwise `api-secret.yaml`)
- ✅ Creates the PostgreSQL PVC
- ✅ Builds the API and frontend images and loads them, plus `postgres:15`, into the cluster
- ✅ Deploys PostgreSQL, Mailpit, the API and the frontend, in that order, waiting for each rollout
- ✅ Checks that every pod is `Running` and prints the access URLs

---

### 2. `deploy-api.sh` - Update the Backend API

Rebuilds the API image from the working tree and rolls it out.

```bash
# Tag "latest"
./scripts/deploy-api.sh

# Specific tag (also re-tagged as latest)
./scripts/deploy-api.sh v2.82.0
```

**What it does:**

- ✅ Shows the branch and asks for confirmation
- ✅ Checks Docker, kubectl, Kind, the cluster and the deployment
- ✅ Builds `agustinedev/comebackgolf-api:<tag>` from `docker/Dockerfile`
- ✅ Loads it into Kind
- ✅ Updates the deployment image (or restarts it if the tag did not change) and waits for the rollout (5 min timeout)
- ✅ Shows the pods, their images and the last log lines, plus the rollback command

---

### 3. `deploy-front.sh` - Update the Frontend

Same flow as `deploy-api.sh`, building `agustinedev/comebackgolf-web:<tag>` from `../ComebackGolfWeb/Dockerfile`.

```bash
./scripts/deploy-front.sh [tag]
```

---

### 4. `deploy-db.sh` - Restart the Database and Apply Migrations

```bash
# Interactive (asks for confirmation)
./scripts/deploy-db.sh

# Skip the confirmation
./scripts/deploy-db.sh --force
```

**What it does:**

- ✅ Rebuilds the API image (it carries the Alembic migrations), loads it into Kind and restarts the API
- ✅ Checks the database pod is running and ready
- 💾 Saves a `pg_dump` in `k8s/backups/db_backup_YYYYMMDD_HHMMSS.sql`; if the backup fails, it asks before going on
- 🔄 Restarts PostgreSQL (scale 0 → 1) and waits until it accepts connections
- 🔧 Runs `alembic upgrade head` inside the API pod and shows `alembic current`
- ✅ Verifies the database pod, the API pods and the connection from the API

**When to use it:** after adding Alembic migrations, or to restart PostgreSQL.

---

### 5. `restore-db.sh` - Restore the Database from a Backup

```bash
./scripts/restore-db.sh
```

**What it does:**

- 📋 Lists the `db_backup_*.sql` files in `k8s/backups/` with size and date
- ✍️ Asks for the file name (a bare name is looked up in `k8s/backups/`; a path starting with `/` or `./` is used as is)
- ✅ Checks the file exists and is not empty
- ⚠️ Warns that **all current data will be lost** and asks for `y`
- 🗄️ Drops and recreates `comebackgolf_dev`, then restores it with `psql`
- 🔧 Runs the Alembic migrations and restarts the API

---

### 6. `restart-cluster.sh` - Restart without Rebuilding

Re-applies the ConfigMaps, the Secret (`api-secret.local.yaml` if present) and Mailpit, then restarts deployments. Useful after editing configuration.

```bash
./scripts/restart-cluster.sh          # same as --all: API + frontend
./scripts/restart-cluster.sh --api
./scripts/restart-cluster.sh --front
./scripts/restart-cluster.sh --db     # asks you to type "yes"
```

---

### 7. `cluster-status.sh` - Diagnostics

```bash
./scripts/cluster-status.sh
```

**What it shows:** cluster info, nodes, pods (frontend, API and database), services, deployments, ConfigMaps and Secrets, PVCs, recent events, health checks (the API's `/` and the frontend's `/health`), the access mode (NodePorts or active port-forwards) and a summary.

---

### 8. `destroy-cluster.sh` - Delete the Cluster

```bash
./scripts/destroy-cluster.sh
```

Asks for confirmation, deletes the cluster and then offers to remove the `kindest/node` Docker images.

**⚠️ Irreversible:** it deletes every pod, the PostgreSQL data and all the configuration in the cluster.

---

### 9. `check_config.py` - Configuration Check

```bash
python k8s/scripts/check_config.py
```

Loads `src/config/settings.py`, detects the environment from `FRONTEND_URL` (local, Kubernetes or production) and checks the required variables, the frontend URL, the email service and the JWT settings, with recommendations.

### `rama-de-la-imagen.sh` (helper)

Not meant to be run directly: `deploy-cluster.sh`, `deploy-api.sh` and `deploy-front.sh` source it to warn which branch an image is built from.

---

## 🚀 Typical Workflows

### First Time Setup

```bash
./scripts/deploy-cluster.sh
./scripts/cluster-status.sh
# Frontend: http://localhost:8080
# API:      http://localhost:8000
```

### Update the Backend after Code Changes

```bash
./scripts/deploy-api.sh
kubectl logs -n comebackgolf deployment/comebackgolf-api -f
```

### Apply Database Migrations

```bash
# 1. Create the migration (from the repository root, with your local database)
alembic revision --autogenerate -m "Add new field"

# 2. Apply it in the cluster (backup included)
./scripts/deploy-db.sh

# 3. Check it
kubectl exec -n comebackgolf deployment/comebackgolf-api -- alembic current
```

### Daily Checks

```bash
./scripts/cluster-status.sh
kubectl logs -n comebackgolf -f deployment/comebackgolf-api
curl http://localhost:8000/health
curl http://localhost:8080/health
```

### Roll Back a Deployment

```bash
kubectl rollout history -n comebackgolf deployment/comebackgolf-api
kubectl rollout undo -n comebackgolf deployment/comebackgolf-api
```

---

## 💾 Database Backups

Backups live in `k8s/backups/` and are ignored by Git (`k8s/backups/*.sql`).

### Manual Backup

Name it `db_backup_*.sql` so `restore-db.sh` lists it:

```bash
DB_POD=$(kubectl get pods -n comebackgolf -l component=database -o jsonpath='{.items[0].metadata.name}')
POSTGRES_USER=$(kubectl get secret comebackgolf-api-secret -n comebackgolf -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
kubectl exec -n comebackgolf "$DB_POD" -- pg_dump -U "$POSTGRES_USER" comebackgolf_dev \
  > k8s/backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 🐛 Troubleshooting

### "Permission denied"

```bash
chmod +x k8s/scripts/*.sh
```

### "docker: command not found" or Docker not running

```bash
docker --version
docker info
```

### Recreate the cluster from scratch

`deploy-cluster.sh` asks you to type the cluster name to recreate it. Or, by hand:

```bash
kind delete cluster --name comebackgolf-cluster
./scripts/deploy-cluster.sh
```

### Backup fails with "role does not exist"

The scripts read the PostgreSQL user from the Secret. Check it:

```bash
kubectl get secret comebackgolf-api-secret -n comebackgolf -o jsonpath='{.data.POSTGRES_USER}' | base64 -d
```

### Restore fails

```bash
ls -lh k8s/backups/
kubectl get pods -n comebackgolf -l component=database
kubectl logs -n comebackgolf -l component=database --tail=50
```

---

## 📝 Notes

- Every `.sh` script except `cluster-status.sh` and the `rama-de-la-imagen.sh` helper stops on the first error (`set -e`).
- Destructive actions (recreating the cluster, restarting or restoring the database, deleting the cluster) ask for confirmation, and the default answer is no.
