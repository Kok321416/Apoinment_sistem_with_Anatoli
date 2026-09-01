# Telegram Mini App — what we fixed

## Files

- `docs/telegram-miniapp-diagnosis.md` — audit
- `app/services/miniapp_token.py` — 15-minute signed Bearer (not localStorage)
- `app/routers/api.py` — `POST /api/auth/telegram` (alias of webapp-auth), `GET /api/me`, hub-state roles + Bearer
- `app/main.py` — `/health` liveness (no MySQL), `/health/ready`, request timing logs
- `app/static/js/telegram-webapp.js` — auth **before** hub-state; no sessionStorage gate; loading/error/retry
- `app/templates/public/tg_mini_app.html` — boot / error / client-denied screens
- `app/templates/components/telegram_webapp.html` — cache `?v=26`
- `tests/test_phase8_mini_app.py`, `tests/test_smoke.py`

## Root causes in code

1. After `1f3db67`, WebView could be sent to `t.me` (Android UA often has no “Telegram”). Already stopped in `1b09b9f` / `open-tg-app` stays on-origin.
2. Boot called **hub-state (MySQL) first**, then maybe webapp-auth. Slow DB → guest login or hang.
3. `sessionStorage` could skip a second auth after a lost Android cookie.
4. `/health` hit MySQL — bad for keepalive that should keep Passenger warm cheaply.

## Auth flow now

1. `GET /tg/` — HTML only, no DB, no redirect.
2. `Telegram.WebApp.ready()` / `expand()`.
3. If `initData` → `POST /api/auth/telegram` (HMAC initData, cookie session + `access_token`).
4. Then `GET /api/telegram/hub-state` with cookie and `Authorization: Bearer …`.
5. Specialist → hub. Client → «нет доступа к кабинету специалиста». Failure → error + Повторить.

Android no longer depends on User-Agent, `t.me` redirects, or `sessionStorage` “auth done”. Bearer is in-memory only, 15 minutes.

## Manual check

1. Wait for deploy, force-close Telegram, Menu **Открыть**.
2. Specialist Telegram account → cabinet cards.
3. Client-only Telegram → access-denied copy, not an infinite login form.
4. `/health` must be fast 200 `{"status":"ok"}`. Slow `/tg/` in logs: `path=/tg/ elapsed_ms=`.

## Logs

- `ERR_TIMED_OUT` before HTML: Passenger cold start (`elapsed_ms` missing or huge on first `/tg/`). Infra, not JS.
- White screen: JS boot error → should now show retry UI.
- Auth fail: `webapp-auth signature_ok=0` or `elapsed_ms` on `/api/auth/telegram`.

## Remaining infra risk

reg.ru Passenger sleep can still exceed Telegram’s ~10s budget. `/health` + keepalive ping `/tg/` mitigate; they cannot guarantee zero cold starts.
