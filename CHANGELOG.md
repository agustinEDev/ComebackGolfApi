# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.82.2] - 2026-11-28

Mantenimiento: dependencias al día y limpieza tras el renombrado. Sin migraciones ni cambio de
contrato. Va con el frontend 2.96.2.

### Changed

- **Dependencias** (#87): FastAPI 0.165.0 (los límites nuevos de cuerpo, formularios y
  concurrencia vienen apagados por defecto), email-validator 2.4.0 y secure 2.0.2; en
  desarrollo, ruff, pip-tools y cyclonedx-bom. El `requirements.lock` se ha regenerado.
- **Limpieza tras el renombrado** (#88, #89): el contacto de la licencia pasa a
  hola@comebackgolf.com; el plan de pago sale del repositorio; se borran la auditoría de julio
  de 2026, el plan RAG que no se hizo y un paquete vacío. El `.env.example` trae
  `EMAIL_TRANSPORT=mailpit`, para que una copia en local no entregue correos de verdad (fuera de
  desarrollo la app sigue exigiendo mailgun).

## [2.82.1] - 2026-11-28

**Primera release desde el repositorio nuevo `agustinEDev/ComebackGolfApi`.** Sin cambios en el
código ni migraciones: solo documentación. Va con el frontend 2.96.1.

### Changed

- **Documentación renovada** (#84): README rehecho; referencia de la API (213 operaciones),
  diagrama de la base de datos (44 tablas), módulos, despliegue, entornos, runbook, guía de la
  pipeline, modelo de amenazas, problemas de seguridad conocidos y los README de Kind, Docker y
  tests, al día con el nombre y los repos nuevos.

## [2.82.0] - 2026-11-27

**El código deja de nombrar la marca vieja** (#947, #948). Sin migraciones ni cambio de
contrato. Al desplegar, cada sesión abierta recibe un 403 de CSRF que el frontend recupera solo
(refresca y reintenta): la etiqueta de la clave cambió. Va con el frontend 2.96.0, que no
depende de él. Probado en el Kind recreado con los nombres nuevos (`comebackgolf-cluster`) y el
frontend 2.96.0: barrido de pantallas sin errores.

### Changed

- **El código ya no nombra la marca vieja** (renombrado a Comeback Golf, primera parte: `src/`
  y `tests/`). Las referencias a issues pasan a «BE #N» (los números anteriores a los repos
  nuevos son de los archivados). Un test impide que vuelva; se quedan los roles de la base de
  datos (`rydercup_app`, `rydercupam_*`), como la propia base, y el modo de juego Ryder.
- **Etiquetas de las claves derivadas con el nombre nuevo**: la del token CSRF y la de la huella
  de los correos en el registro de seguridad. Al desplegar, cada sesión abierta recibe un 403
  de CSRF que el frontend recupera solo (refresca y reintenta). Las huellas de correo de antes
  y de después del despliegue no coinciden: no se puede cruzar un mismo correo entre las dos.
- La release que se declara a Sentry pasa a `comebackgolf-api@<versión>`.
- **Segunda parte del renombrado: Kind, Docker, documentación, scripts y CI.** El clúster local
  pasa a `comebackgolf-cluster`, con namespace `comebackgolf`, imágenes `comebackgolf-api` y
  `comebackgolf-web` y base `comebackgolf_dev` (hay que recrearlo). Los enlaces apuntan ya a
  los repos nuevos (`ComebackGolfApi`, `ComebackGolfWeb`) y el script de importar campos usa
  `course.import@comebackgolf.com` (en PRO se actualiza esa fila a la vez). El guardián mira
  ahora todo el repo, salvo este CHANGELOG.

## Earlier versions

The history up to this version lives in the archived repository `agustinEDev/RyderCupAM`.
