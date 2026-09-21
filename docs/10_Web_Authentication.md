# Web login and API authentication

Browser operations use a server-side administrator session. CSV prediction uploads and normal page requests automatically send the HttpOnly cookie, with a CSRF header for writes. Users do not paste an API token into the prediction form. External Python/curl integrations continue to use bearer tokens or `X-API-Key` with their existing scopes.

## Setup and migration

Add these settings to the ignored root `.env` (choose your own strong, unique password; do not commit it):

```dotenv
EDGEML_WEB_USERNAME=admin
EDGEML_WEB_PASSWORD=choose-a-long-unique-web-password
EDGEML_WEB_COOKIE_SECURE=false
```

Keep the existing `EDGEML_API_TOKEN` for integrations, separate from the web password. Local launchers read these settings through `start-dev.bat`; stop the existing local services and relaunch `start-dev-redis.bat` or `start-dev.bat`. Do not run duplicate backends on the same port. Direct uvicorn invocation requires exporting the environment or using `python -m uvicorn app.main:app --reload --env-file ..\.env` from `backend`. The batch loader expects unquoted `NAME=value` lines; long randomly generated alphanumeric passwords avoid CMD metacharacter and quote handling differences.

For Docker, rebuild/redeploy the project using `deploy-docker.bat` to replace the old frontend bundle and pass the new backend environment. Later credential-only changes require recreating the backend, not rebuilding the frontend. This migration removes `VITE_EDGEML_API_TOKEN` from source, Docker build arguments, and launchers. Rotate previously browser-embedded integration tokens after migrating if those bundles were distributed.

Open the frontend and sign in using the web account. Its session permits all current administrator operations, including API-token management. The toolbar provides Sign out. On session expiry the login screen returns; in-progress form state is reset and requests are not automatically replayed. API-only installations without `EDGEML_WEB_PASSWORD` keep accepting valid integration tokens but show a configuration prompt in the web UI.

## Session behavior

- Random session credentials are stored only as SHA-256 digests in the existing configured SQLite database. Sessions are shared across backend processes using that database and survive application restarts.
- Cookies are HttpOnly, SameSite=Strict, scoped to `/api`, and optionally Secure. They have an absolute lifetime of eight hours (`EDGEML_WEB_SESSION_SECONDS`, 300–86400 seconds). Local launchers use the default duration; export a custom duration before launch if needed.
- Login rotates the current browser session. Logout deletes the server record. Changing the web username or password invalidates existing sessions; session records contain a PBKDF2-derived credential fingerprint, never the raw password.
- Login allows at most five attempts per client IP in five minutes, including successful attempts. Counters use SQLite and are shared across processes. Forwarded IP headers are not trusted; deployments behind a proxy may share one rate-limit bucket.
- Session-authenticated writes require a per-session `X-CSRF-Token`. The status endpoint restores it after a reload. Login/logout also require `X-EdgeML-Login: 1` and reject supplied untrusted origins. Authentication responses are not cached.
- Explicit invalid API credentials are rejected even if a browser session is present. The web session does not change managed token scope enforcement.

## HTTPS and reverse proxy

Serve the UI and `/api` through the same origin. Vite's proxy and the bundled nginx configuration already do this. For deployed HTTPS, set `EDGEML_WEB_COOKIE_SECURE=true` and set `EDGEML_WEB_ALLOWED_ORIGINS` to a JSON array of exact public origins, such as `["https://edgeml.example.com"]`. Configure the proxy to route `/api` to the backend. Origins are used to validate browser login, not to bypass authentication. Do not enable Secure cookies on plain HTTP development hosts.

This is a single-administrator login, not a multi-user identity platform. SSO, individual accounts, role-based browser permissions, MFA, and a session-management UI remain future work.

## Explicit anonymous development (R05)

`EDGEML_ANONYMOUS_API` defaults to `false`: business APIs return `401` without credentials, even on a new installation or after the last token expires/is revoked. The public session-status endpoint reports `required=true`; a browser without a configured password shows setup guidance. Health probes and session login/status remain public.

Only for intentional local development, set `EDGEML_ANONYMOUS_API=true` and clear both `EDGEML_API_TOKEN` and `EDGEML_WEB_PASSWORD` in `.env`. Restart the local launcher, or recreate Docker Backend after passing the updated configuration. Existing credentials take priority over the flag. Managed-token counts do not affect this policy: in explicit anonymous mode, creating a managed token does not protect otherwise anonymous requests. Invalid supplied tokens still fail; token administration still requires valid administrator credentials.

When migrating an old anonymous installation, either configure the web password (recommended) or explicitly opt into the development mode. Keep `EDGEML_ANONYMOUS_API=false` for deployed use.

## Endpoints and verification

| Endpoint | Behavior |
| --- | --- |
| `GET /api/auth/session` | Login requirements and current session state; CSRF token returned only for an authenticated session |
| `POST /api/auth/session` | `{ "username": "admin", "password": "..." }`; requires `X-EdgeML-Login: 1`; sets session cookie |
| `DELETE /api/auth/session` | Requires `X-EdgeML-Login: 1` and live session CSRF header; revokes session and clears cookie |

Regression tests cover authenticated multipart CSV prediction, missing CSRF rejection, anonymous API rejection, unchanged bearer access, invalid credentials, login throttling, cookie attributes, session expiry/rotation/revocation, password changes, and sessions shared across app instances. Run `python -m pytest tests/test_web_session.py tests/test_api_tokens.py tests/test_api.py -q` in the backend environment. Run `npm run build` in frontend for type/build verification.
