# Module: User Management

> **Version:** 2.82.0 · **Last updated:** 28 November 2026
> **Code:** `src/modules/user/`

## 📋 Description

The user module owns accounts and access: sign-up with email verification, login with email and password or with Google, sessions per device, password reset and change, email change, handicaps (RFEG lookup or manual), avatars, terms acceptance and the admin back office. It follows Clean Architecture + DDD: the domain does not import infrastructure, and `import-linter` enforces it in CI (`.importlinter`, ADR-046).

Friends, public profiles, profile photos and the activity feed live in the **social** module (`src/modules/social/`), not here.

**Full endpoint list:** [`docs/API.md`](../API.md) and the OpenAPI schema served at `/docs` (protected with HTTP Basic).

---

## 🗂️ Layout

```
src/modules/user/
├── domain/
│   ├── entities/        # User, UserDevice, RefreshToken, PasswordHistory,
│   │                    # UserOAuthAccount, TermsAcceptance, UserAvatarUpload
│   ├── value_objects/   # UserId, Email, Password, Handicap, DeviceFingerprint, TokenHash…
│   ├── services/        # Login brake, refresh-token rotation, device cookie, handicap service…
│   ├── ports/           # PasswordHasher
│   ├── repositories/    # Repository interfaces + UserUnitOfWork interface
│   ├── errors/  exceptions/
├── application/
│   ├── use_cases/       # One class per operation
│   ├── services/        # Shared steps: save the session, revoke sessions, security notices…
│   ├── ports/           # Email, Google OAuth, RFEG handicap, token service, image processor,
│   │                    # security audit, login brake, notice quotas…
│   └── dto/
└── infrastructure/
    ├── api/v1/          # auth_routes, google_auth_routes, user_routes, device_routes,
    │                    # handicap_routes, avatar_routes, admin_routes
    ├── persistence/     # sqlalchemy/ and in_memory/ (test doubles)
    ├── security/        # BcryptPasswordHasher, re-authentication, SecurityAuditLogger
    ├── external/        # RFEG handicap service, Google OAuth service, Pillow image processor,
    │                    # avatar preset provider
    └── static/avatar_presets/
```

---

## 🗃️ Domain Model

| Entity | Role |
|--------|------|
| `User` | Aggregate root: name, alias, email (verified or not, pending email change), password hash, handicap, country, gender, admin and active flags, failed-login counters, avatar choice, terms version accepted |
| `UserDevice` | A device that signed in: name, user agent, IP, fingerprint hash, last use, installed app; the session belongs to it (ADR-039, ADR-042) |
| `RefreshToken` | A hashed refresh token tied to a device, rotated on every refresh |
| `PasswordHistory` | Previous password hashes, to prevent reuse (ADR-029) |
| `UserOAuthAccount` | A linked Google account (`OAuthProvider.GOOGLE`) |
| `TermsAcceptance` | When a user accepted which version of the terms |
| `UserAvatarUpload` | An uploaded avatar image, stored in the database |

Main value objects: `UserId`, `Email`, `Password` (policy below), `Handicap`, `DeviceFingerprint`, `TokenHash`, `AvatarSource`, `OAuthProvider`, `TermsOfService`.

Security audit events (`src/shared/domain/events/security_events.py`) are written to the security log by `SecurityAuditLogger` through the `security_audit_interface` port (ADR-050, ADR-051): login attempts, logout, refresh used/revoked/reused/rejected, password and email changes, password reset requested/completed, account unlocked/deactivated/reactivated/deleted by an admin, admin role changes, Google account linked/unlinked, access denied, rate limit exceeded, terms accepted, among others.

---

## 🎯 Use cases

There are 48 use-case files in `application/use_cases/`. By area:

| Area | Use cases |
|------|-----------|
| Sign-up and verification | register, verify email, resend verification, accept terms |
| Login and sessions | login, logout, refresh access token, re-authenticate, get current user, register device, list devices, revoke device, purge stale sessions |
| Google | Google login, link Google account, unlink Google account |
| Password and account | request password reset, validate reset token, reset password, update security (password/email), confirm or cancel email change, unlock account |
| Profile and search | update profile, find user, search users, player stats, recent matches |
| Handicap | update from RFEG, update several, update manually, refresh my own |
| Avatar | list presets, preset image, set preset, upload, list my uploads, activate an upload, get images, remove |
| Admin | stats, list users, update user, activate/deactivate, delete user |
| Maintenance | ensure the system user, purge old terms acceptances |

---

## 🔐 Security

Values checked in code on 28 Nov 2026:

| Topic | What the code does | Where |
|-------|--------------------|-------|
| Tokens | JWT access token in the `access_token` httpOnly cookie, **15 min** by default (`ACCESS_TOKEN_EXPIRE_MINUTES`); refresh token in the `refresh_token` cookie, **7 days** by default (`REFRESH_TOKEN_EXPIRE_DAYS`) | `src/config/settings.py`, `src/shared/infrastructure/security/cookie_handler.py` |
| Refresh rotation | Each refresh replaces the token with a successor; reuse of a replaced token is detected and handled (lost response, two tabs or theft) | `domain/services/rotacion_del_refresco.py` |
| CSRF | Signed token bound to the user, in the `csrf_token` cookie plus a header | `src/config/csrf_config.py`, ADR-028, ADR-040, ADR-047 |
| Password policy | 12 to 64 characters and at most 72 bytes, checked against blocklists | `domain/value_objects/password.py` |
| Hashing | bcrypt, **12 rounds** by default (`BCRYPT_ROUNDS`; fewer only in development) | `src/config/contrasenas.py`, `infrastructure/security/bcrypt_password_hasher.py` |
| Password history | The last 5 passwords cannot be reused | `domain/entities/password_history.py`, ADR-029 |
| Login brake | Per email and origin (the network, or a trusted device): 10 failures in 30 min lock that origin for 30 min; the account-wide backstop never locks out a trusted device | `domain/services/freno_del_login.py`, ADR-043 |
| Sign-up and reset | Sign-up does not reveal existing accounts; email links are hashed and expire | ADR-048 |
| New device | A sign-in from a new device sends a notice by email | ADR-042 |
| Google | Login with PKCE (`tests/integration/api/v1/test_google_pkce.py`) | `infrastructure/external/google_oauth_service.py` |

Rate limiting is shared by the whole API (slowapi, default limit plus per-route limits, ADR-041).

---

## 📡 API

Operations per OpenAPI tag (counted from `app.openapi()`):

| Tag | Prefix | Operations |
|-----|--------|-----------:|
| Authentication (incl. Google) | `/api/v1/auth` | 16 |
| Users | `/api/v1/users` | 12 |
| Devices | `/api/v1/users/me/devices` | 2 |
| Handicaps | `/api/v1/handicaps` | 4 |
| Avatars | `/api/v1/avatar-presets`, `/api/v1/users/me/avatar…`, `/api/v1/users/{user_id}/avatar` | 9 |
| Admin | `/api/v1/admin` | 5 |

---

## 📊 Database

Tables of this module: `users`, `user_devices`, `refresh_tokens`, `password_history`, `user_oauth_accounts`, `terms_acceptances`, `user_avatar_uploads`. Columns and relations: [`docs/DATABASE_ERD.md`](../DATABASE_ERD.md).

The first admin is set by the migration that adds `users.is_admin` (`alembic/versions/7522c9fc51ef_…`): it promotes the existing user whose email is `ADMIN_EMAIL`, and does nothing if the variable is empty (see `.env.example`).

---

## 🧪 Testing

```bash
pytest tests/unit/modules/user/    # unit tests, no database
pytest tests/integration/          # endpoint tests (need PostgreSQL)
pytest tests/security/             # CSRF, injection, auth bypass, rate limiting…
```

- Unit tests: `tests/unit/modules/user/` (1,904 collected with `pytest --collect-only` on 28 Nov 2026).
- Endpoint tests: `tests/integration/api/v1/` (for example `test_auth_routes.py`, `test_account_lockout.py`, `test_device_routes.py`, `test_handicap_routes.py`, `test_avatar_routes.py`, `test_admin_endpoints.py`).
- In-memory repositories for unit tests: `src/modules/user/infrastructure/persistence/in_memory/`.

---

## 🔗 ADRs

- [ADR-014: Handicap management system](../architecture/decisions/ADR-014-handicap-management-system.md)
- [ADR-019: Email verification system](../architecture/decisions/ADR-019-email-verification-system.md)
- [ADR-024: Password reset system](../architecture/decisions/ADR-024-password-reset-security.md)
- [ADR-027: Account lockout](../architecture/decisions/ADR-027-account-lockout-brute-force-protection.md)
- [ADR-029: Password history](../architecture/decisions/ADR-029-password-history.md)
- [ADR-030: Device fingerprinting](../architecture/decisions/ADR-030-device-fingerprinting.md)
- [ADR-039: Sessions belong to a device](../architecture/decisions/ADR-039-session-lifetime-per-device.md)
- [ADR-040: Signed CSRF token bound to the user](../architecture/decisions/ADR-040-signed-csrf-token-bound-to-user.md)
- [ADR-042: Devices checked by id, new sign-in notice](../architecture/decisions/ADR-042-devices-checked-by-id-and-new-sign-in-notice.md)
- [ADR-043: Login brake per email and network](../architecture/decisions/ADR-043-login-brake-per-email-and-network.md)
- [ADR-044: Deactivated accounts and refresh codes](../architecture/decisions/ADR-044-deactivated-accounts-and-public-refresh-codes.md)
- [ADR-045: Unverified accounts, lock rule and pending email](../architecture/decisions/ADR-045-unverified-accounts-lock-rule-and-pending-email.md)
- [ADR-048: Sign-up without enumeration, hashed links, reset brake](../architecture/decisions/ADR-048-sign-up-without-enumeration-hashed-links-and-reset-brake.md)
