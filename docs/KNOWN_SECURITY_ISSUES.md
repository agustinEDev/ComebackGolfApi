# Known Security Issues

> Known security risks that are accepted on purpose, and the ones already resolved.
> Last review: 28 Nov 2026 (v2.82.0).

---

## 🔒 Accepted risks

### Invitation duplicate check can confirm a guessed email (accepted, 14 Nov 2026)

**Context:** phase 6 audit, B-01/B-03. Organizers no longer see the email of a player
invited by user id, nor whether a typed email has an account.

**Residual risk:** the duplicate-pending check runs on the invitee's email in both ways of
inviting, so it can confirm a guessed email in either direction:
- an organizer who invited player U by id (still pending) types a guessed email into
  "invite by email": "a pending invitation already exists" means it is U's;
- an organizer who invited a guessed email (still pending) invites players by id: the same
  answer for player V means the email is V's.

**Why it is accepted (owner's decision, 14 Nov 2026):** the attacker must guess the exact
address and test it against a pending invitation of their own. Every attempt to invite,
including one that ends in the duplicate answer, counts towards a per-user brake of 100
requests an hour on the two invite routes. Hiding it would need a fake
success, which an earlier attempt showed to be distinguishable (the invitation list, a
repeated try).

**Related:** inviting by email someone already enrolled still says so, as before:
organizers already see their enrolled players' emails.

---

## ✅ Resolved

### CVE-2024-23342 - ecdsa Minerva timing attack

`ecdsa` came in as a transitive dependency of `python-jose`. JWT handling moved to
`PyJWT`, and `ecdsa` is no longer in `requirements.lock`. Even before, the risk was low:
tokens are signed with HS256 (`ALGORITHM` is fixed in `src/config/settings.py`, ADR-047),
never with elliptic-curve algorithms.

- CVE: https://nvd.nist.gov/vuln/detail/CVE-2024-23342

### SBOM generator dependencies resolved on each run

Accepted on 14 Nov 2026 (phase 6 audit, INF-04): the `sbom_generation` job installed
`cyclonedx-bom` with its transitive dependencies resolved on each run. The job now installs
it with `pip install --require-hashes -r .github/sbom-tools.lock`, a hash-pinned lock
compiled from `.github/sbom-tools.txt`.

---

## 📊 Summary

| Risk | Status |
|------|--------|
| Invitation duplicate check can confirm a guessed email | Accepted (14 Nov 2026) |
| CVE-2024-23342 (ecdsa) | Resolved: dependency removed |
| SBOM generator dependencies unpinned | Resolved: hash-pinned lock |
