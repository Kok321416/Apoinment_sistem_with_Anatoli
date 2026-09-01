# Telegram Mini App — diagnosis (Android)

Date: 2026-09-01. Repo HEAD at time of audit: current `main`.

## What caused timeouts

1. **`1f3db67`** — Mini App return path used `client=tg` + `/accounts/open-tg-app/` which then auto-navigated to `https://t.me/<bot>?startapp=…`. Android WebView UA often has **no** substring `Telegram`, so the server treated the WebView as an external browser and bounced it to `t.me` → **ERR_TIMED_OUT**.
2. **Passenger cold start** — first byte of `/tg/` after idle can exceed Telegram’s ~10s WebView budget. Browser waits longer, so the same URL “works” outside Telegram.
3. **`46b2342` + hub-state** — HTML shell is DB-free, but boot **waited on** `GET /api/telegram/hub-state` (MySQL) **before** `webapp-auth`. Slow/failed hub-state left a guest “Вход для специалиста” screen or a hung load.
4. **`sessionStorage` `tg_webapp_auth_done`** — flagged auth complete before cookie/session was proven; Android WebView often drops `SameSite` cookies, then flags blocked a second `webapp-auth` (`5dd43a9` tried to unwind this).

## Redirects to `t.me`

| Location | Behaviour |
|----------|-----------|
| `GET /tg/` | **No** HTTP redirect. 200 HTML. |
| `GET /accounts/open-tg-app/` | Redirects **on-origin** to complete/handoff (no `t.me` since `1b09b9f`). |
| Bot / site launch URLs | `https://t.me/<bot>?start=open` is for **outside** Mini App (open the bot). Must not run as `window.location` inside WebView. |
| `telegram_login.html` | Uses `WebApp.openTelegramLink` for the bot confirm button (user gesture). |

## Telegram via User-Agent

`app/services/telegram_webview.py` still checks `"telegram" in UA`. Used for CSS/SDK load (`load_telegram_webapp`) and ops alerts — **not** for `/tg/` (that route forces `load_telegram_webapp=True`). Must **not** be used to redirect to `t.me`.

Client must treat Mini App as `Telegram.WebApp.initData` present, not UA.

## Does `GET /tg/` hit MySQL?

**No** (after `866c2b9` / later cleanup): Jinja `_page_context_base` only, `user=None`, no `Depends(get_async_db)`.

## Does first paint wait on hub-state?

**Yes (bug).** `ensureHubAuth` calls `hydrateTelegramHub` first; only if `authenticated === false` does it run `webapp-auth`. That inverts the required order and couples first UI to a DB API.

## Can sessionStorage block re-auth?

**Yes, historically.** `tg_webapp_auth_done` / retry keys. `5dd43a9` stopped skipping auth when hub-state is false, but flags still exist. They must not gate auth.

## initData check (already correct)

`validate_webapp_init_data` in `app/services/telegram_webapp_auth.py`: parse_qsl → pop hash → sort `key=value` with `\n` → HMAC-SHA256(`WebAppData`, bot token) → HMAC of data_check_string → `compare_digest` → `auth_date` max age 24h. Token from `TELEGRAM_BOT_TOKEN`. Does not trust `initDataUnsafe` on the server.

Endpoint today: `POST /api/telegram/webapp-auth` (cookie session via `finish_login_json_async`).

## Planned fixes (minimal)

1. Auth **before** hub-state; never skip auth because of sessionStorage.
2. Alias `POST /api/auth/telegram`; return short-lived signed Bearer as **fallback** if cookies fail; hub-state accepts `Authorization`.
3. Hub-state: explicit `role`, `hub_available`, `reason=specialist_access_required`.
4. `GET /api/me`.
5. Loading / error / retry UI; no blank screen; 8s fetch timeout.
6. `GET /health` liveness without MySQL; `GET /health/ready` for schema.
7. Timing logs for `/tg/`, auth, hub-state, `/health`.
8. Tests for the above. No `t.me` redirect from `/tg/`.
