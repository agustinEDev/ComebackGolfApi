# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
