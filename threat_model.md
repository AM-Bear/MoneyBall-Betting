# Threat Model

## Project Overview

MONEYLINE is a public, autoscale-deployed FastAPI and React/Vite baseball research and betting-analysis desk. The backend (`backend/main.py`) serves public/authenticated API routes, MLB data integrations, model calculations, a Postgres-backed pick/parlay record store, and optional Google OAuth, while `artifacts/moneyline` is the browser client. User accounts, sessions, password resets, OAuth linking, and Stripe billing are implemented in the backend.

## Assets

- **User accounts and sessions** -- credentials, session cookies, password-reset tokens, OAuth identities, and account metadata. Compromise permits access to private research and billing operations.
- **Private research and record data** -- tracked picks, parlays, billing/access state, and any user-associated records. Cross-user disclosure or mutation would violate account isolation.
- **Billing and entitlements** -- Stripe customer/subscription identifiers and research-access state. Unauthorized checkout, portal access, or entitlement changes can cause financial or access-control impact.
- **Application and integration secrets** -- database URL, session/password-reset signing material, Google OAuth credentials, mail credentials, and Stripe keys. Disclosure can enable impersonation, database access, or billing abuse.
- **MLB/external data and service availability** -- outbound API trust, model inputs, and backend capacity. SSRF, resource exhaustion, or tampering can affect users and integrity of prices/records.

## Trust Boundaries

- **Browser to public API** -- all request bodies, query parameters, headers, cookies, and redirect inputs are attacker-controlled. The server must authenticate and authorize protected operations independently of the React UI.
- **Unauthenticated to authenticated** -- auth, OAuth callbacks, password reset, and billing entry points cross this boundary and need secure token/session handling, CSRF protection where applicable, and rate limits.
- **User to admin/privileged operations** -- billing, record grading, and account changes must enforce the exact subject, object, and role relationship server-side.
- **Backend to Postgres** -- request-derived values must not permit injection or unscoped reads/writes; private records must be filtered by the authenticated user.
- **Backend to external services** -- MLB, Google OAuth, mail, and Stripe calls use server-held credentials or trusted responses. User-controlled URLs must not select arbitrary destinations.
- **Backend to static/browser responses** -- requested paths and stored/user data cross into file serving or HTML/JS rendering and must not enable traversal or script injection.

## Scan Anchors

- **Production entry points:** `backend/main.py` FastAPI app and `backend/serve_spa.py`; auth routes are in `backend/auth_routes.py` and OAuth in `backend/oauth.py`.
- **Highest-risk areas:** `backend/auth.py`, `auth_routes.py`, `auth_store.py`, `oauth.py`, `billing.py`, `record_store.py`, `main.py` routes, outbound fetches in `feeds.py`/OAuth, and static/SEO handlers.
- **Public vs authenticated:** `backend/auth.py` defines public API paths; the application-wide session gate protects all other API routes. Auth callback/reset and health/static paths need separate review.
- **Dev-only areas:** `artifacts/mockup-sandbox` and test/mockup code are not production scope unless a deployment path demonstrates reachability.

## Threat Categories

### Spoofing

Login, sessions, password reset, OAuth state, and account linking must establish an unforgeable, expiring, revocable subject. Cookies must have appropriate Secure/HttpOnly/SameSite attributes, and reset/OAuth tokens must be single-use, scoped, and rate-limited. Public auth endpoints must not disclose account existence or permit takeover.

### Tampering

Prices, picks, parlays, grading inputs, entitlements, and account fields must be validated and calculated server-side. Database operations must use parameterized queries and scope records to the authenticated user. Stripe webhooks must be cryptographically verified before changing billing state.

### Information Disclosure

Private record and account data must be returned only to the owning authenticated user. Secrets, reset tokens, OAuth credentials, database errors, and PII must not leak through responses, logs, static files, or browser bundles. Static serving must be confined to the built frontend directory.

### Denial of Service

Public routes, authentication, feed refreshes, computational simulations, regex processing, and outbound calls need bounded input, response/body sizes, timeouts, and rate controls. User-controlled patterns or URLs must not allow catastrophic regex work or internal-network probing.

### Elevation of Privilege

Every sensitive handler must enforce server-side object and function authorization; client route guards and hidden controls are not sufficient. Billing access, record grading, role/entitlement fields, password reset, and OAuth account linking must not trust client-supplied identity or scope.

### Repudiation

Sensitive account, billing, pick, grading, and entitlement actions should retain reliable actor and timestamp context without logging credentials or tokens. Webhook and external-provider events should be authenticated and auditable.
