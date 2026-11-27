# 🌍 Multi-Environment Setup - ComebackGolfApi

## 📋 Environment Overview

| Environment | Description | Frontend URL | Usage |
|-------------|-------------|--------------|-------|
| **Local (Docker)** | Local development with Docker Compose | `http://localhost:5173` | Daily development |
| **Local (Kubernetes)** | Local Kind cluster | `http://localhost:8080` | K8s testing before deploy |
| **Production** | Production deployment | `https://www.comebackgolf.com` | Live application |

---

## 🐳 Environment 1: Local (Docker)

### Setup

**.env file:**
```bash
FRONTEND_URL=http://localhost:5173
MAILGUN_API_KEY=your-api-key
MAILGUN_DOMAIN=comebackgolf.com
MAILGUN_FROM_EMAIL="Comeback Golf <noreply@comebackgolf.com>"
MAILGUN_API_URL=https://api.eu.mailgun.net/v3
# Correos (BE #563): local y Kind → EMAIL_TRANSPORT=mailpit (no se entregan, se ven en
# http://localhost:8025); producción → mailgun, con RESEND_API_KEY y BREVO_API_KEY de respaldo
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/comebackgolf
SECRET_KEY=your-local-secret-key
```

> **Note:** `DATABASE_URL` supports multiple formats: `postgres://`, `postgresql://`, and `postgresql+asyncpg://` (validated by `entrypoint.sh`).

### Commands

```bash
# Start services
docker-compose up -d

# Apply migrations
docker-compose exec app alembic upgrade head

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Verification
- Backend: http://localhost:8000/docs
- Frontend: http://localhost:5173
- Email links: `http://localhost:5173/verify-email?token=xxx`

---

## ☸️ Environment 2: Local (Kubernetes)

### Requirements
- Docker Desktop
- kubectl
- Kind

### Configuration

**k8s/api-configmap.yaml:**
```yaml
FRONTEND_URL: "http://localhost:8080"
```

**k8s/api-secret.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-secret
  namespace: comebackgolf
type: Opaque
data:
  MAILGUN_API_KEY: <base64-encoded>
  SECRET_KEY: <base64-encoded>
  POSTGRES_PASSWORD: <base64-encoded>
```

### Deployment

```bash
# Deploy complete cluster
./k8s/scripts/deploy-cluster.sh

# Check status
./k8s/scripts/cluster-status.sh

# Port forward (in separate terminals)
kubectl port-forward -n comebackgolf svc/frontend-service 8080:80
kubectl port-forward -n comebackgolf svc/api-service 8000:8000

# Update only backend
./k8s/scripts/deploy-api.sh

# Update only frontend
./k8s/scripts/deploy-front.sh
```

### Verification
- Frontend: http://localhost:8080
- Backend: http://localhost:8000/docs
- Email links: `http://localhost:8080/verify-email?token=xxx`

### Troubleshooting

```bash
# Check ConfigMap
kubectl get configmap api-configmap -n comebackgolf -o yaml | grep FRONTEND_URL

# Edit ConfigMap
kubectl edit configmap api-configmap -n comebackgolf

# Restart deployment
kubectl rollout restart deployment/api-deployment -n comebackgolf

# View logs
kubectl logs -f -n comebackgolf deployment/api-deployment
```

---

## 🚀 Environment 3: Production

### Render.com Configuration

**Backend (Web Service) - Environment Variables:**
```bash
FRONTEND_URL=https://www.comebackgolf.com,<old domain>
DATABASE_URL=<provided-by-render>
MAILGUN_API_KEY=<production-key>
MAILGUN_DOMAIN=comebackgolf.com
MAILGUN_FROM_EMAIL="Comeback Golf <noreply@comebackgolf.com>"
MAILGUN_API_URL=https://api.eu.mailgun.net/v3
# Correos (BE #563): local y Kind → EMAIL_TRANSPORT=mailpit (no se entregan, se ven en
# http://localhost:8025); producción → mailgun, con RESEND_API_KEY y BREVO_API_KEY de respaldo
SECRET_KEY=<production-secret>  # 32 bytes o más; HS256 fijo, sin ALGORITHM (ADR-047)
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=production
PORT=8000
DOCS_USERNAME=admin
DOCS_PASSWORD=<secure-password>
```

**Frontend (Static Site):**
```bash
VITE_API_BASE_URL=https://api.comebackgolf.com
```

### Deployment

Automatic on push to `main`:
```bash
git push origin main
# Monitor at: https://dashboard.render.com
```

### Verification
- Frontend: https://www.comebackgolf.com
- Backend: https://api.comebackgolf.com/docs
- Qué release está desplegada: `curl -s https://api.comebackgolf.com/health`
- Email links: `https://www.comebackgolf.com/verify-email?token=xxx`

---

## 🔍 Configuration Verification

```bash
# Check config script
python k8s/scripts/check_config.py

# Manual check
python -c "from src.config.settings import settings; print(f'FRONTEND_URL: {settings.FRONTEND_URL}')"
```

---

## 🐛 Common Issues

### Issue 1: Wrong Email Links

**Symptoms**: Email links point to wrong URL

**Solution**:
1. Check `FRONTEND_URL` in your environment
2. Restart application
3. For K8s: `kubectl rollout restart deployment/api-deployment -n comebackgolf`

### Issue 2: Emails Not Sending

**Solution**:
```bash
# Verify Mailgun config
python -c "from src.config.settings import settings; print('Mailgun:', bool(settings.MAILGUN_API_KEY))"

# Check logs
docker-compose logs app | grep -i mailgun
kubectl logs -n comebackgolf deployment/api-deployment | grep -i mailgun
```

### Issue 3: Port Already in Use

```bash
# Find process
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn main:app --reload --port 8001
```

---

## 📊 Port Summary

| Service | Docker | K8s (localhost) | Production |
|---------|--------|-----------------|------------|
| Backend | 8000 | 8000 | 443 (HTTPS) |
| Frontend | 5173 | 8080 | 443 (HTTPS) |
| PostgreSQL | 5432 | 5434 | 5432 (Render) |

---

## 🔗 References

- **Render Dashboard**: https://dashboard.render.com
- **Mailgun Dashboard**: https://app.mailgun.com
- **K8s Scripts**: `k8s/scripts/`
- **Full Docs**: See `docs/` directory

---

**Last Updated**: 28 January 2026
