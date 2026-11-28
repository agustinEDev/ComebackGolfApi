# Roadmap - Comeback Golf Backend

> **Versión en producción:** 2.82.0 (27 nov 2026) · fuente: `src/config/version.py`
>
> El detalle de cada versión está en el [CHANGELOG](CHANGELOG.md). Este documento resume
> lo que ya existe y lo que queda por delante; no repite el historial.

---

## Lo que ya está en producción

| Módulo | Qué cubre |
|--------|-----------|
| **user** | Registro con verificación por correo, inicio de sesión con cookies httpOnly y CSRF, Google (entrar, vincular, desvincular), restablecer contraseña, cambio de correo, dispositivos, hándicap (RFEG y manual), avatares (prediseñados o foto propia), estadísticas del jugador, aceptación de términos, panel de administración |
| **competition** | Torneos en formato Ryder (`RYDER_CUP`), Stableford y Medal; estados `DRAFT → ACTIVE → CLOSED → IN_PROGRESS → COMPLETED` (+ `CANCELLED`) con vuelta atrás; inscripciones, invitaciones (por usuario o por correo), lista de espera y cierre automático; equipos, capitanes, draft y sobres; rondas y partidos (`SINGLES`, `FOURBALL`, `FOURSOMES`); grupos de salida y anotación de stroke play; anotación hoyo a hoyo con validación, clasificaciones y leaderboard |
| **golf_course** | Campos con barras y hoyos, solicitudes y aprobación por un administrador, importación de los recorridos federados ([RFEG_COURSE_IMPORT.md](docs/RFEG_COURSE_IMPORT.md)), mapa de hoyos a partir de OpenStreetMap con revisión |
| **quick_match** | Partidas rápidas fuera de un torneo: amigos e invitados sin cuenta, anotadores delegados, cierre automático de las que se quedan abiertas, ocultar, papelera y borrado cuando la borran todos, excluir de las estadísticas |
| **social** | Amistades y bloqueos, perfil público, galería de fotos, actividad y novedades de los amigos, logros |
| **support** | Formulario de contacto que llega por correo al buzón de la app |

Trabajos en segundo plano que arranca la app: cierre de inscripciones y de partidas
rápidas pasadas de plazo, limpieza de sesiones caducadas, refresco programado de
hándicaps con la RFEG y comprobación diaria de la clave de Brevo.

---

## Pendiente

- **Decisiones abiertas de la última release:** ver
  [docs/pendientes-de-release.md](docs/pendientes-de-release.md).
- **Plan de pago e IA (aparcado):** asistente del reglamento, entrenador de swing y
  caddie. Plan, costes y precio en [docs/plan-de-pago-e-ia.md](docs/plan-de-pago-e-ia.md)
  y [ADR-052](docs/architecture/decisions/ADR-052-no-ai-rules-assistant-for-now.md).
  Aparcado hasta poder facturar; necesita antes un sistema de pagos
  (Stripe), que hoy no existe. Sustituye al antiguo módulo «AI & RAG» (LangChain +
  Pinecone + OpenAI), que no se llegó a hacer: [docs/RAG_IMPLEMENTATION.md](docs/RAG_IMPLEMENTATION.md).
- **Iniciar sesión con Apple:** no existe todavía (solo Google). Requiere una cuenta de
  Apple Developer.

## Ideas sin fecha

Nada de esto existe hoy en el código; son candidatas, no compromisos:

- Exportación de los datos del usuario (RGPD).
- Leaderboard en tiempo real por WebSocket.
- Notificaciones push.
- Llaves de seguridad (WebAuthn).
