# 🌐 API Reference

| | |
|---|---|
| **Production base URL** | `https://api.comebackgolf.com` |
| **Local base URL** | `http://localhost:8000` |
| **Version** | 2.82.2 (`src/config/version.py`, also returned by `GET /health`) |
| **Operations** | 213 in the OpenAPI schema (`app.openapi()`) |
| **Prefix** | every business route lives under `/api/v1` |

This page is a map of the API: method, path and one line per operation, grouped by
the OpenAPI tags. Request and response schemas, field limits and examples live in
the schema itself, which is the source of truth. The CI generates it with
`app.openapi()` and compares it with the base branch (`api_contract` job, oasdiff),
so the contract cannot change unnoticed.

To generate it locally, without a database or secrets:

```bash
ENVIRONMENT=development python -c 'import json; from main import app; print(json.dumps(app.openapi(), indent=2))' > openapi.json
```

---

## 📖 Interactive documentation

| Path | What it serves |
|------|----------------|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | The OpenAPI schema |

All three are **behind HTTP Basic authentication** (`DOCS_USERNAME` /
`DOCS_PASSWORD`). Without both variables set, they answer `401`. Wrong credentials
count against a per-network limit of 20 per minute; correct ones are not counted.
None of the three appears in the schema.

---

## 🔐 Authentication, CSRF and errors

### Session cookies

The session lives only in cookies (`src/shared/infrastructure/security/cookie_handler.py`):

| Cookie | httpOnly | Lifetime | Purpose |
|--------|----------|----------|---------|
| `access_token` | yes | 15 min | JWT access token (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 15) |
| `refresh_token` | yes | 7 days | Refresh token (`REFRESH_TOKEN_EXPIRE_DAYS`, default 7) |
| `csrf_token` | **no** | 15 min | Double-submit CSRF token, readable by the frontend |

- Cookies are `SameSite=Lax`. Tokens are never returned in the body, and the
  `Authorization: Bearer` header is **not** accepted: the cookie is the only way
  to authenticate.
- `POST /api/v1/auth/refresh-token` issues a new access token (and a new CSRF token)
  from the refresh cookie.
- In the OpenAPI schema the session appears as the `APIKeyCookie` security scheme
  (`access_token` cookie). The **Session** column below comes from that declaration.

### CSRF

`src/shared/infrastructure/middleware/csrf_middleware.py` checks every `POST`, `PUT`,
`PATCH` and `DELETE` (`GET`, `HEAD` and `OPTIONS` are exempt), except on the routes in
`EXEMPT_PATHS` (`src/config/csrf_config.py`): login, register, Google sign-in, refresh,
logout, forgot/reset password, email verification and its link, the reset-token check,
the contact form, plus `/health` and the docs.

1. The `X-CSRF-Token` header must match the `csrf_token` cookie.
2. The token is signed (HMAC-SHA256 with a key derived from `SECRET_KEY`) and carries its
   issue time. When the request has a session, it must also belong to that session's
   user; without a session there is no user to check, so only step 1 applies.
3. `SameSite=Lax` on the cookies.

A failure answers `403` with `"error_code": "CSRF_VALIDATION_FAILED"`. The frontend
recovers by refreshing the session and repeating the request once.

### Login brake

On top of the rate limits, `POST /api/v1/auth/login` has a brake per email + origin
(`src/config/freno_del_login.py`, ADR-043): 5 attempts per minute, and 10 failures in
30 minutes lock that origin for that email for 30 minutes. Other origins can still
sign in.

### Error format

Errors answer `{"detail": "..."}`. Those the frontend acts on also carry an
`error_code` at the root, for example:

| Status | `error_code` | When |
|--------|--------------|------|
| 403 | `CSRF_VALIDATION_FAILED` | Missing or invalid CSRF token |
| 403 | `TERMS_NOT_ACCEPTED` | The user has not accepted the current Terms of use (`POST /api/v1/users/me/accept-terms`) |
| 403 | `EMAIL_NOT_VERIFIED` | The action requires a verified email |
| 429 | — | Rate limit exceeded |

Every response carries an `X-Correlation-ID` header (exposed through CORS) to trace
the request in the logs.

---

## ⏱️ Rate limiting

`src/config/rate_limit.py` (ADR-038). Who is counted:

- **Routes with a session**: the user, taken from a verified access token.
- **Anonymous routes**: the network. In production that is the real client IP sent
  by Cloudflare together with its origin secret (ADR-041); an IPv6 address counts
  by its /64.
- **Every session route without its own limit**: 100 per minute per user and route
  (`DEFAULT_LIMIT`). Scoring a quick-match hole gets 300 per minute, because the
  offline queue replays a whole round at once. `/`, `/health`, the documentation,
  avatar presets and countries are exempt.

Limits on the anonymous and sensitive routes (paths relative to `/api/v1`):

| Route | Limit | Counted per |
|-------|-------|-------------|
| `POST /auth/login` | 120/minute | network (ceiling: every login costs a bcrypt hash) |
| `POST /auth/login` | 5/minute | email + origin (login brake) |
| `POST /auth/login` | 30 failed/minute | network, failures only |
| `POST /auth/google` | 30/minute | network |
| `POST /auth/register` | 30/hour | network |
| `POST /auth/verify-email` | 60/hour | network |
| `POST /auth/forgot-password`, `/auth/resend-verification`, `/auth/resend-verification-link` | 30/hour + 3/hour per email | network + email |
| `POST /auth/reset-password` | 20/hour | network |
| `POST /auth/validate-reset-token` | 30/hour | network |
| `POST /auth/refresh-token` | 30/minute | refresh session |
| `PATCH /users/security` | 10/hour (3/hour when asking for a new email) | user |
| `GET /users/search?email=` | 20/hour | user |
| Both invitation routes | 100/hour together | user |
| `POST /support/contact` | 10/day | network |
| `POST /support/contact` | 20 messages per 24 hours (`MENSAJES_POR_DIA` in `src/config/cupo_de_contacto.py`, in memory: a restart resets it); then 429 `CONTACT_QUOTA_EXCEEDED` | whole app |
| `POST /competitions` | 10/hour | user |
| `POST /handicaps/update` | 5/hour | user |
| `POST /handicaps/refresh-mine` | 10/hour | user |
| Public leaderboard and standings, competition summary | 30/minute with a session, 600/minute without | user or network |

---

## 📋 Endpoint reference

**Session**: ✅ the route declares the session cookie; 🌐 it also answers without a
session (public competitions or public data); — no session.

### Health

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/` | Basic metadata (name, version, status) | — |
| `GET` | `/health` | Deployed version, commit, branch and environment | — |

### Authentication

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/auth/register` | Register a new user | — |
| `POST` | `/api/v1/auth/verify-email` | Verify the email with the token from the email | — |
| `POST` | `/api/v1/auth/resend-verification` | Resend the verification email (with a session) | ✅ |
| `POST` | `/api/v1/auth/resend-verification-link` | Ask for a new verification link with the expired one (no session) | — |
| `POST` | `/api/v1/auth/login` | Sign in (sets the session cookies) | — |
| `POST` | `/api/v1/auth/logout` | Sign out and revoke the refresh token | ✅ |
| `POST` | `/api/v1/auth/refresh-token` | Renew the access token from the refresh cookie | — |
| `GET` | `/api/v1/auth/current-user` | Current user | ✅ |
| `POST` | `/api/v1/auth/reauthenticate` | Confirm the current password | ✅ |
| `POST` | `/api/v1/auth/forgot-password` | Request a password reset email | — |
| `POST` | `/api/v1/auth/validate-reset-token` | Check a reset token before showing the form | — |
| `POST` | `/api/v1/auth/reset-password` | Complete the password reset | — |
| `POST` | `/api/v1/auth/unlock-account` | Unlock an account manually (admin) | ✅ |
| `POST` | `/api/v1/auth/google` | Sign in or register with Google | — |
| `POST` | `/api/v1/auth/google/link` | Link a Google account | ✅ |
| `DELETE` | `/api/v1/auth/google/unlink` | Unlink the Google account | ✅ |

### Users

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `PATCH` | `/api/v1/users/profile` | Update the profile | ✅ |
| `PATCH` | `/api/v1/users/security` | Update security data (password; a new email stays pending) | ✅ |
| `POST` | `/api/v1/users/me/email-change/confirm` | Confirm the pending new email | ✅ |
| `DELETE` | `/api/v1/users/me/email-change` | Cancel the pending new email | ✅ |
| `POST` | `/api/v1/users/me/accept-terms` | Accept the current Terms of use | ✅ |
| `GET` | `/api/v1/users/search` | Search a user | ✅ |
| `GET` | `/api/v1/users/search-autocomplete` | Autocomplete user search | ✅ |
| `GET` | `/api/v1/users/me/roles/{competition_id}` | My roles in a competition | ✅ |
| `GET` | `/api/v1/users/me/matches` | My match history | ✅ |
| `GET` | `/api/v1/users/me/stats` | My statistics | ✅ |
| `GET` | `/api/v1/users/me/stats/breakdown` | My strokes breakdown | ✅ |
| `GET` | `/api/v1/users/me/stats/golf-courses/{golf_course_id}` | My statistics on one course | ✅ |

### Devices

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/users/me/devices` | List active devices | ✅ |
| `DELETE` | `/api/v1/users/me/devices/{device_id}` | Revoke a device | ✅ |

### Avatars

Photo uploads (avatar and gallery) accept up to 10 MB.

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/avatar-presets` | List avatar presets | — |
| `GET` | `/api/v1/avatar-presets/{preset_id}/image` | Image of a preset | — |
| `POST` | `/api/v1/users/me/avatar/preset` | Set a preset as the active avatar | ✅ |
| `POST` | `/api/v1/users/me/avatar/upload` | Upload a new avatar photo | ✅ |
| `GET` | `/api/v1/users/me/avatar/uploads` | My avatar upload history | ✅ |
| `POST` | `/api/v1/users/me/avatar/uploads/{upload_id}/activate` | Reactivate a previous upload | ✅ |
| `GET` | `/api/v1/users/me/avatar/uploads/{upload_id}/image` | One of my uploaded photos | ✅ |
| `DELETE` | `/api/v1/users/me/avatar` | Remove the active avatar | ✅ |
| `GET` | `/api/v1/users/{user_id}/avatar` | A user's active avatar image | ✅ |

### Handicaps

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/handicaps/refresh-mine` | Refresh my handicap from the RFEG | ✅ |
| `POST` | `/api/v1/handicaps/update` | Update one user's handicap | ✅ |
| `POST` | `/api/v1/handicaps/update-multiple` | Update several users' handicaps | ✅ |
| `POST` | `/api/v1/handicaps/update-manual` | Update a handicap manually | ✅ |

### Admin

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/admin/stats` | Platform-wide statistics | ✅ |
| `GET` | `/api/v1/admin/users` | List users | ✅ |
| `PUT` | `/api/v1/admin/users/{user_id}` | Edit a user | ✅ |
| `PUT` | `/api/v1/admin/users/{user_id}/active` | Activate or deactivate an account | ✅ |
| `DELETE` | `/api/v1/admin/users/{user_id}` | Permanently delete an account | ✅ |

### Competitions

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions` | List competitions with filters | ✅ |
| `POST` | `/api/v1/competitions` | Create a competition | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}` | Get a competition | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}` | Update a competition | ✅ |
| `DELETE` | `/api/v1/competitions/{competition_id}` | Delete a competition | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}/summary` | Public summary of a competition | 🌐 |
| `PATCH` | `/api/v1/competitions/{competition_id}/stroke-play` | Change the stroke play settings | ✅ |

### Competitions: state transitions

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/competitions/{competition_id}/activate` | `DRAFT` → `ACTIVE` | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/close-enrollments` | `ACTIVE` → `CLOSED` | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/reopen-enrollments` | `CLOSED` → `ACTIVE` | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/start` | `CLOSED` → `IN_PROGRESS` | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/revert-status` | `IN_PROGRESS` → `CLOSED` | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/complete` | `IN_PROGRESS` → `COMPLETED` | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/revert-to-in-progress` | `COMPLETED` → `IN_PROGRESS` | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/cancel` | Any state → `CANCELLED` | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/captains` | Name the captains (closes enrollments) | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/handicap-updates` | Update handicaps from the RFEG | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/handicap-updates/schedule` | Schedule the handicap update | ✅ |
| `DELETE` | `/api/v1/competitions/{competition_id}/handicap-updates/schedule` | Cancel the scheduled handicap update | ✅ |
| `GET` | `/api/v1/competitions/me/handicaps-not-updated` | My handicaps not updated from the RFEG | ✅ |

### Competitions: golf courses

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions/{competition_id}/golf-courses` | List the competition's courses | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/golf-courses` | Add a course | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/golf-courses/reorder` | Reorder the courses | ✅ |
| `DELETE` | `/api/v1/competitions/{competition_id}/golf-courses/{golf_course_id}` | Remove a course | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}/course-tees` | Tee set fixed on each course for each gender | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/courses/{golf_course_id}/tee` | Fix a course's tee set for everyone of a gender | ✅ |

### Enrollments

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions/{competition_id}/enrollments` | List enrollments | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/enrollments` | Join a public competition | ✅ |
| `POST` | `/api/v1/enrollments/{enrollment_id}/approve` | Approve an enrollment | ✅ |
| `POST` | `/api/v1/enrollments/{enrollment_id}/reject` | Reject an enrollment | ✅ |
| `POST` | `/api/v1/enrollments/{enrollment_id}/cancel` | Cancel an enrollment | ✅ |
| `POST` | `/api/v1/enrollments/{enrollment_id}/withdraw` | Withdraw from a competition | ✅ |
| `POST` | `/api/v1/enrollments/{enrollment_id}/remove` | Remove an enrolled player | ✅ |
| `PUT` | `/api/v1/enrollments/{enrollment_id}/handicap` | Set a custom handicap | ✅ |
| `DELETE` | `/api/v1/enrollments/{enrollment_id}/handicap` | Remove the custom handicap | ✅ |
| `PUT` | `/api/v1/enrollments/{enrollment_id}/name-preference` | Choose alias or real name in this competition | ✅ |
| `GET` | `/api/v1/enrollments/{enrollment_id}/tees` | Tee sets of an enrollment, course by course | ✅ |
| `PUT` | `/api/v1/enrollments/{enrollment_id}/tee` | Change an enrollment's tee set | ✅ |
| `PUT` | `/api/v1/enrollments/{enrollment_id}/courses/{golf_course_id}/tee` | Change an enrollment's tee set on one course | ✅ |

### Invitations

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions/{competition_id}/invitations` | List a competition's invitations | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/invitations` | Invite by user ID | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/invitations/by-email` | Invite by email | ✅ |
| `GET` | `/api/v1/invitations/me` | My invitations | ✅ |
| `POST` | `/api/v1/invitations/{invitation_id}/respond` | Accept or decline an invitation | ✅ |
| `POST` | `/api/v1/invitations/{invitation_id}/cancel` | Cancel an invitation | ✅ |

### Competitions: teams

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/competitions/{competition_id}/teams` | Assign teams | ✅ |
| `DELETE` | `/api/v1/competitions/{competition_id}/teams` | Undo the teams | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/teams/{team}/captain` | Fill a team's captain seat | ✅ |
| `PUT` | `/api/v1/competitions/{competition_id}/teams/{team}/vice-captain` | Name a team's vice-captain | ✅ |

### Competitions: draft

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions/{competition_id}/draft` | View the draft room | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/draft` | Run the draw and open the draft room | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/draft/picks` | Pick a player | ✅ |

### Competitions: rounds and schedule

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/competitions/{competition_id}/rounds` | Create a round | ✅ |
| `PUT` | `/api/v1/competitions/rounds/{round_id}` | Update a round | ✅ |
| `DELETE` | `/api/v1/competitions/rounds/{round_id}` | Delete a round | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}/schedule` | Get the competition schedule | ✅ |
| `POST` | `/api/v1/competitions/{competition_id}/schedule/configure` | Configure the schedule | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/places` | Take a place in a time slot | ✅ |
| `DELETE` | `/api/v1/competitions/rounds/{round_id}/places/{user_id}` | Release a place in a time slot | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/waiting-list` | Join a time slot's waiting list | ✅ |
| `DELETE` | `/api/v1/competitions/rounds/{round_id}/waiting-list/{user_id}` | Leave a time slot's waiting list | ✅ |
| `GET` | `/api/v1/competitions/me/assigned-places` | Places the waiting list assigned to me | ✅ |
| `POST` | `/api/v1/competitions/me/assigned-places/{round_id}/acknowledge` | Acknowledge a place assigned by the waiting list | ✅ |

### Competitions: envelopes

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `PUT` | `/api/v1/competitions/rounds/{round_id}/envelope` | Hand in your team's envelope | ✅ |
| `GET` | `/api/v1/competitions/rounds/{round_id}/envelopes` | View a session's envelopes | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/envelopes/reveal` | Open a session's envelopes | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/envelopes/reset` | Redo a session's envelopes | ✅ |
| `GET` | `/api/v1/competitions/me/pending-envelopes` | My envelopes not handed in | ✅ |
| `GET` | `/api/v1/competitions/me/sessions-without-matches` | My sessions left without matches | ✅ |

### Competitions: matches (match play)

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/competitions/rounds/{round_id}/matches/generate` | Generate matches | ✅ |
| `GET` | `/api/v1/competitions/matches/{match_id}` | Match detail | ✅ |
| `PUT` | `/api/v1/competitions/matches/{match_id}/status` | Update a match's status | ✅ |
| `POST` | `/api/v1/competitions/matches/{match_id}/walkover` | Declare a walkover | ✅ |
| `PUT` | `/api/v1/competitions/matches/{match_id}/players` | Reassign a match's players | ✅ |

### Competitions: match play scoring

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/competitions/matches/{match_id}/scoring-view` | Scoring view of a match | ✅ |
| `POST` | `/api/v1/competitions/matches/{match_id}/scores/holes/{hole_number}` | Record a hole score | ✅ |
| `POST` | `/api/v1/competitions/matches/{match_id}/scorecard/submit` | Submit the scorecard | ✅ |
| `PUT` | `/api/v1/competitions/matches/{match_id}/concede` | Concede a match | ✅ |
| `POST` | `/api/v1/competitions/matches/{match_id}/players/{player_id}/withdraw` | Withdraw a player from a fourball | ✅ |
| `POST` | `/api/v1/competitions/matches/{match_id}/players/{player_id}/reinstate` | Undo a fourball player's withdrawal | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}/leaderboard` | Competition leaderboard | 🌐 |

### Competitions: tee groups and stroke play

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/competitions/rounds/{round_id}/groups/generate` | Generate a time slot's groups | ✅ |
| `GET` | `/api/v1/competitions/rounds/{round_id}/groups` | View a time slot's groups | ✅ |
| `DELETE` | `/api/v1/competitions/rounds/{round_id}/groups` | Delete a time slot's groups | ✅ |
| `PUT` | `/api/v1/competitions/rounds/{round_id}/groups/order` | Reorder a time slot's groups | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/groups/players` | Move a player to another group | ✅ |
| `POST` | `/api/v1/competitions/rounds/{round_id}/groups/close` | Close a time slot's groups (organizer) | ✅ |
| `GET` | `/api/v1/competitions/{competition_id}/groups/me` | My groups in a competition | ✅ |
| `PUT` | `/api/v1/competitions/groups/{group_id}/markers` | Change a group's markers | ✅ |
| `GET` | `/api/v1/competitions/groups/{group_id}/scoring-view` | The group, ready to score | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/scores/holes/{hole}` | Score a hole in a group | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/scorecard` | Hand in the scorecard | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/scorecard/retire` | Retire from the group | ✅ |
| `PUT` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/holes/{hole}` | Correct a hole (organizer) | ✅ |
| `DELETE` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/holes/{hole}` | Clear what was scored on a hole (organizer) | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/no-show` | Mark as no-show (organizer) | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/retire` | Retire a player (organizer) | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/reopen` | Reopen a scorecard (organizer) | ✅ |
| `POST` | `/api/v1/competitions/groups/{group_id}/players/{user_id}/validate-scored` | Validate the holes of a player without a marker (organizer) | ✅ |
| `GET` | `/api/v1/competitions/rounds/{round_id}/standings` | Standings of a time slot | 🌐 |
| `GET` | `/api/v1/competitions/{competition_id}/standings` | Overall standings | 🌐 |
| `GET` | `/api/v1/competitions/{competition_id}/standings/scratch` | Scratch standings | 🌐 |

### Golf courses

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/golf-courses` | List golf courses | ✅ |
| `GET` | `/api/v1/golf-courses/{golf_course_id}` | Get a golf course | ✅ |
| `POST` | `/api/v1/golf-courses/request` | Request a new golf course | ✅ |
| `PUT` | `/api/v1/golf-courses/{golf_course_id}` | Propose an update to a golf course | ✅ |
| `GET` | `/api/v1/golf-courses/{golf_course_id}/hole-map` | Hole map (GeoJSON) | ✅ |
| `GET` | `/api/v1/golf-courses/{golf_course_id}/hole-map/samples` | List hole samples | ✅ |
| `POST` | `/api/v1/golf-courses/{golf_course_id}/hole-map/samples/{hole_number}` | Submit a hole sample | ✅ |
| `POST` | `/api/v1/golf-courses/{golf_course_id}/hole-map/reports/{hole_number}` | Report a problem with a hole | ✅ |

### Golf courses: administration

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/golf-courses/admin` | Create a golf course directly | ✅ |
| `GET` | `/api/v1/golf-courses/admin/pending` | List pending golf courses | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{golf_course_id}/approve` | Approve a golf course | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{golf_course_id}/reject` | Reject a golf course | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{clone_id}/approve-update` | Approve a proposed update | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{clone_id}/reject-update` | Reject a proposed update | ✅ |
| `GET` | `/api/v1/golf-courses/admin/hole-maps/pending` | List pending hole maps | ✅ |
| `GET` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-map` | Hole map for review | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-map/approve` | Approve a hole map | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-map/reject` | Reject a hole map | ✅ |
| `GET` | `/api/v1/golf-courses/admin/hole-reviews` | List hole reviews | ✅ |
| `GET` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-reviews` | Hole review of a course | ✅ |
| `PUT` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-lines/{hole_number}` | Save a hole line | ✅ |
| `DELETE` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-lines/{hole_number}` | Reopen a hole | ✅ |
| `DELETE` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-reports/{report_id}` | Discard a hole report | ✅ |
| `DELETE` | `/api/v1/golf-courses/admin/{golf_course_id}/hole-samples/{sample_id}` | Delete a hole sample | ✅ |

### Quick matches

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/quick-matches` | Create a quick match | ✅ |
| `POST` | `/api/v1/quick-matches/start` | Create and start a quick match | ✅ |
| `GET` | `/api/v1/quick-matches/me` | List my quick matches | ✅ |
| `GET` | `/api/v1/quick-matches/{quick_match_id}` | Quick match detail | ✅ |
| `GET` | `/api/v1/quick-matches/{quick_match_id}/shared` | A friend's finished quick match (read-only) | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/start` | Start a quick match | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/complete` | Complete a quick match | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/cancel` | Cancel a quick match | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/hide` | Hide it from my history | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/participants` | Add a friend | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/participants/guest` | Add a guest | ✅ |
| `DELETE` | `/api/v1/quick-matches/{quick_match_id}/participants/{target_participant_id}` | Remove a participant | ✅ |
| `PATCH` | `/api/v1/quick-matches/{quick_match_id}/participants/{target_participant_id}/handicap` | Set a participant's handicap | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/holes/{hole_number}/score` | Score my own hole | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/participants/{target_participant_id}/holes/{hole_number}/score` | Score a hole for another participant | ✅ |
| `POST` | `/api/v1/quick-matches/{quick_match_id}/stats-exclusion` | Leave this match out of my statistics | ✅ |
| `DELETE` | `/api/v1/quick-matches/{quick_match_id}/stats-exclusion` | Count this match in my statistics again | ✅ |

### Friends

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/friends/me` | List my friends | ✅ |
| `POST` | `/api/v1/friends/requests` | Send a friend request | ✅ |
| `GET` | `/api/v1/friends/requests/me` | My pending friend requests | ✅ |
| `POST` | `/api/v1/friends/requests/{friendship_id}/respond` | Respond to a friend request | ✅ |
| `DELETE` | `/api/v1/friends/{friendship_id}` | Remove a friendship | ✅ |
| `POST` | `/api/v1/friends/{user_id}/block` | Block a user | ✅ |
| `PUT` | `/api/v1/social/activity-sharing` | Turn achievement sharing on or off | ✅ |

### Profiles and feed

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/users/{user_id}/profile` | A player's profile | ✅ |
| `GET` | `/api/v1/users/{user_id}/activity` | A player's published achievements | ✅ |
| `GET` | `/api/v1/users/{user_id}/games-together` | Games you finished with a friend | ✅ |
| `GET` | `/api/v1/users/me/feed` | My activity feed | ✅ |
| `GET` | `/api/v1/users/me/feed/unseen-count` | How much is new in my feed | ✅ |
| `PUT` | `/api/v1/users/me/feed/seen` | Mark the feed as seen | ✅ |

### Profile photos

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/users/me/photos` | Upload a photo to my gallery | ✅ |
| `DELETE` | `/api/v1/users/me/photos/{photo_id}` | Delete one of my photos | ✅ |
| `GET` | `/api/v1/users/{user_id}/photos` | A player's photo gallery | ✅ |
| `GET` | `/api/v1/users/{user_id}/photos/{photo_id}/image` | A photo's image | ✅ |

### Countries

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `GET` | `/api/v1/countries` | List active countries | — |
| `GET` | `/api/v1/countries/{country_code}/adjacent` | List adjacent countries | — |

### Support

| Method | Path | Description | Session |
|--------|------|-------------|---------|
| `POST` | `/api/v1/support/contact` | Contact form (emailed to the app's mailbox) | — |

---

## 🔗 Related

- Routers: `src/modules/*/infrastructure/api/v1/` and `src/shared/infrastructure/api/v1/`
- Registration of every router and its prefix: `main.py`
- Rate limits: `src/config/rate_limit.py`
- Module guides: [`docs/modules/user-management.md`](modules/user-management.md),
  [`docs/modules/competition-management.md`](modules/competition-management.md)
- Integration tests of the API: `tests/integration/api/v1/`
- Architecture decisions: [`docs/architecture/decisions/`](architecture/decisions/)
