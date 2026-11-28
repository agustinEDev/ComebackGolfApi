# 📚 Documentación - Comeback Golf API

Índice de la documentación del backend. La portada del proyecto es el
[README](../README.md); el historial de versiones, el [CHANGELOG](../CHANGELOG.md).

---

## 🧭 Empezar

| Documento | Para qué |
|-----------|----------|
| [README](../README.md) | Qué es, stack, puesta en marcha rápida |
| [MULTI_ENVIRONMENT_SETUP.md](MULTI_ENVIRONMENT_SETUP.md) | Variables de entorno y diferencias entre local, Kind y producción |
| [project-structure.md](project-structure.md) | Cómo está organizado `src/` |
| [tests/README.md](../tests/README.md) | Cómo se organizan y ejecutan los tests |

## 🏗️ Arquitectura y dominio

| Documento | Para qué |
|-----------|----------|
| [design-document.md](design-document.md) | Diseño general: Clean Architecture, DDD, módulos |
| [modules/user-management.md](modules/user-management.md) | Módulo de usuarios |
| [modules/competition-management.md](modules/competition-management.md) | Módulo de competiciones |
| [DATABASE_ERD.md](DATABASE_ERD.md) | Modelo de datos |
| [architecture/decisions/](architecture/decisions/) | ADRs: las decisiones de arquitectura, una por fichero |

## 📡 API

| Documento | Para qué |
|-----------|----------|
| [API.md](API.md) | Referencia de endpoints, autenticación, CSRF y límites de peticiones |
| `/docs`, `/redoc`, `/openapi.json` | Documentación interactiva generada por la app (tras HTTP Basic) |

## 🚀 Operación

| Documento | Para qué |
|-----------|----------|
| [DEPLOYMENT.md](../DEPLOYMENT.md) | Despliegue: Docker Compose y Render |
| [RUNBOOK.md](RUNBOOK.md) | Día a día: estado, logs, migraciones, copias, permisos de la base y restauración |
| [ci-cd/PIPELINE_GUIDE.md](ci-cd/PIPELINE_GUIDE.md) | Qué comprueba el CI y cómo reproducirlo |
| [k8s/README.md](../k8s/README.md) · [k8s/scripts/README.md](../k8s/scripts/README.md) | Clúster local con Kind |
| [docker/README.md](../docker/README.md) · [docker/scripts/README.md](../docker/scripts/README.md) | Docker Compose local |
| [RFEG_COURSE_IMPORT.md](RFEG_COURSE_IMPORT.md) | Importar los campos federados |

## 🔐 Seguridad

| Documento | Para qué |
|-----------|----------|
| [security/THREAT_MODEL.md](security/THREAT_MODEL.md) | Modelo de amenazas (STRIDE) de los flujos críticos |
| [KNOWN_SECURITY_ISSUES.md](KNOWN_SECURITY_ISSUES.md) | Riesgos aceptados y resueltos |

## 🗺️ Producto

| Documento | Para qué |
|-----------|----------|
| [ROADMAP.md](../ROADMAP.md) | Lo que hay y lo que queda |
| [pendientes-de-release.md](pendientes-de-release.md) | Decisiones que una release deja para otra |
| [plan-de-pago-e-ia.md](plan-de-pago-e-ia.md) | Plan de pago e IA (aparcado) |

## 🗄️ Histórico

Se conservan como registro; no describen el código de hoy.

| Documento | Qué fue |
|-----------|---------|
| [AUDIT_BACKEND_2026-07.md](AUDIT_BACKEND_2026-07.md) | Auditoría de seguridad y arquitectura de julio de 2026 |
| [RAG_IMPLEMENTATION.md](RAG_IMPLEMENTATION.md) | Plan de asistente de diciembre de 2025, sustituido y nunca implementado |
