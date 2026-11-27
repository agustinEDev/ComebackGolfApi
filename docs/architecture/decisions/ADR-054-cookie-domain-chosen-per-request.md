# ADR-054: The Cookie Domain Is Chosen per Request, from an Allow-list

**Status:** Accepted
**Date:** November 24, 2026
**Context:** Shared infrastructure; Security - OWASP A01, A05, A07
**Author:** Agustín Estévez

---

## Context

The frontend reads the CSRF cookie from `www` (double-submit), so the API sets its
cookies for the whole site (`Domain=` the old domain), not only for `api`. That
domain was a single fixed value in `COOKIE_DOMAIN`.

The product is being renamed and will move to `comebackgolf.com`. Serving the frontend
from the new domain against the old domain's API cannot work: the cookies belong to
another site, they are not sent with its requests, and Safari blocks third-party cookies
outright. The API has to be reachable under the new domain too, and then a fixed cookie
domain is wrong for one of the two.

## Decision

1. **`COOKIE_DOMAIN` is a comma-separated allow-list**, the default first:
   `.comebackgolf.com,.<old domain>`. A single value behaves as before; empty
   means no `Domain` attribute (local, Kind).
2. **Each request gets the entry its `Host` belongs to** (`api.comebackgolf.com` →
   `.comebackgolf.com`). The host is normalised (case, port, trailing dot) and must
   equal the entry or end with a dot plus the entry. Of several that match, the most
   specific wins.
3. **The domain is chosen, never built from the `Host`.** A host that matches nothing
   gets the first entry.
4. **One place decides**: `get_cookie_domain()` in `cookie_handler`, used when setting
   and when deleting the four cookies that carry a domain (access, refresh, CSRF,
   device). The re-authentication cookie has no domain and does not change.
5. **The `Host` travels in a context variable** set by a pure ASGI middleware
   (`DominioDeLasCookies`). Only routes write cookies today; it is registered outside
   every `add_middleware` one, so that one writing a cookie on the way back would see
   it too. The two `@app.middleware` ones wrap it and must not set cookies.
6. **A malformed entry stops the boot outside development** (`arranque_seguro`): with
   a scheme, a port, a `;` separator or a bare TLD. It used to go out as written, browsers dropped the
   cookie and nobody could sign in, with no error anywhere.

## Why this is safe

- A forged `Host` can only make the response name another entry of the list. Browsers
  discard a cookie whose `Domain` is not the site that sent it, so nothing is gained.
- No cookie attribute changes: `HttpOnly`, `Secure` and `SameSite` stay as they were.
- The two sites do not share a session. Cookies set under one domain are not sent to
  the other; signing in on both means two sessions and two devices.
- Requests through today's host get today's domain: with one entry, or with the current
  one first, the output is identical to before.

## Consequences

- Adding a domain is configuration, no code. Order matters: deploy; register the new
  redirect URI with Google; extend `COOKIE_DOMAIN`, `FRONTEND_ORIGINS` and
  `GOOGLE_REDIRECT_URI`; and only then expose the new host. Exposed earlier, sign-in
  answers 200 but the browser drops the cookies, and Google rejects the exchange.
- Tokens are not bound to the domain that issued them: a cookie set through one host
  is valid through the other. Harmless while both domains are ours. **The old domain
  must not be let go** while browsers may still hold its cookies (refresh, 7 days;
  device, 1 year): whoever held `api.` there would receive them. Retire it by removing
  its entry and its origin from `FRONTEND_ORIGINS` together, and keep the registration
  for more than a year after, or revoke sessions and devices first.
- Links in emails still come from `FRONTEND_URL`, a single value: they point to one
  frontend until that variable is moved.
- `GOOGLE_REDIRECT_URI` is a list too, one per frontend: Google rejects the exchange
  unless it gets the URI the code was requested with. The one under the request's
  cookie domain is chosen; the first if none is. A malformed entry stops the boot.
- The new Cloudflare zone needs the `X-Origin-Verify` rule (ADR-041); without it the
  client IP is not trusted through that domain and its rate limit is shared.
- Code that sets a cookie outside a request (none today) gets the first entry.

## Alternatives rejected

- **Host-only cookies (no `Domain`)**: the frontend on `www` could not read the CSRF
  cookie.
- **A second API deployment for the new domain**: two services and a second database
  for what is one application, or two services writing to one database.
- **Passing the request to every cookie helper**: a dozen call sites to change, and
  the next one written would forget it.
