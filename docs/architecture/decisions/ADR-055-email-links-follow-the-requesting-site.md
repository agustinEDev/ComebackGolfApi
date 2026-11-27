# ADR-055: Email Links Follow the Site the Request Came From

**Status:** Accepted
**Date:** November 25, 2026
**Context:** Shared infrastructure, email; Security - OWASP A01, A05
**Author:** Agustín Estévez

---

## Context

Since ADR-054 the API is served under two domains while the product is renamed to
Comeback Golf. Emails, though, built every link and loaded their header image from
`FRONTEND_URL`, a single address. Someone who asked for a password reset on
`www.comebackgolf.com` got a link to the other site, where neither their session nor
their installed app lives. ADR-054 listed this as a known limitation.

At the same time the emails take the new brand: a header image per kind of email (the
logo over a faint drawing), served by the frontend.

## Decision

1. **`FRONTEND_URL` is a comma-separated list**, the main site first. A single value
   behaves as before.
2. **An email about one's own account uses the site its request came from**
   (verification, password reset, email change, security notices). It is the same
   choice as the cookie domain: the request's `Host` selects one of the configured
   cookie domains, and the frontend address under that domain is used. The address is
   **chosen from the list, never built from the `Host`**, so a forged header cannot send
   a link carrying a token to a foreign domain.
3. **Everything else uses the main site, the first entry**: emails received by someone
   else (invitations, friend requests, handicap notices), emails with no request behind
   them (scheduled notices) and a `Host` that belongs to no site. Whoever invites from
   one site does not choose the site the invitee enters by. A background email keeps the
   site of the request that started it: the task copies the request's context.
4. **Outside development the app does not start** if an entry is not an https address of the
   site alone: no path, query, fragment or credentials. The message never shows the value.
5. **The header image is one composed picture per kind of email**
   (`/images/correo/cabecera-<drawing>.png`, served by the frontend from the only
   folder it opens to other origins), because mail clients
   cannot overlap images. Its cell keeps the background colour and the image carries the
   brand name as alternative text, so an email with images blocked still reads well. It
   is the only image.

## Consequences

- The password-reset link, built by its use case, receives the address per request from
  the composition root.
- The header images must be deployed in the frontend before the backend that references
  them: backend and frontend ship in the same release, frontend assets first.
- On the day of the migration the order of `FRONTEND_URL` is swapped, and with it where
  every email to a third party and every scheduled notice points.
- Emails already delivered keep pointing to the domain they were sent with, so the old
  domain has to keep serving the app for as long as those links may be opened.

## References

- ADR-054 (cookie domain chosen per request), ADR-019 (email verification)
- `src/shared/infrastructure/http/dominio_de_las_cookies.py` (`web_de_la_peticion`)
- `src/shared/infrastructure/email/email_layout.py`
