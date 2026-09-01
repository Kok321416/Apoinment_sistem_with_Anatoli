# Telegram Mini App

## Entry

- URL: `https://{SITE_URL}/tg/`
- Bot Menu Button → `/tg/`
- `GET /tg/` intentionally **DB-free** (fast TTFB for WebView)

## Auth flow

```
Telegram WebView
  → telegram-webapp.js (self-hosted SDK)
  → GET /api/telegram/hub-state
  → if guest: POST /api/telegram/webapp-auth { init_data }
  → HMAC-SHA256 validation (telegram_webapp_auth.py)
  → find_or_create_user_from_webapp_async
  → Set-Cookie session (SameSite=none on HTTPS)
  → hub-state → show authenticated UI
```

## Cabinet links from hub

- `/dashboard/`, `/booking/`, `/manage/`, `/become-specialist/`

## FACT vs HYPOTHESIS

| Issue | Status |
|-------|--------|
| initData HMAC implemented | **FACT** |
| Self-hosted SDK (no CDN) | **FACT** |
| Specialist-only hub UI | **FACT** (client mode removed) |
| initData creates client-only user | **FACT** — specialist may see guest UI after silent auth |
| Cookie not persisting in WebView | **HYPOTHESIS** — needs prod Set-Cookie check |
| IPv6/AAAA DNS hang | **HYPOTHESIS** — `/health/mini-app` warns |
| Cold start >10s | **HYPOTHESIS** — Passenger+MySQL |
| sessionStorage blocks re-auth | **HYPOTHESIS** |
| Password middleware redirects TG users | **FACT** — `/accounts/password/set/` |

## Fixes applied (this session)

- Bot `/book/` → `/tg/?mode=client` (was dead redirect to `/`)

## Health

- `GET /health/mini-app` — cookie config, SDK path, frame-ancestors
- `scripts/check_mini_app_health.py`

## Recommended next steps

1. Prod verify: `curl -I https://allyourclients.ru/health/mini-app`
2. Add `GET /api/auth/me` as source of truth (reduce sessionStorage reliance)
3. Update `test_phase8_mini_app.py`
4. Exempt or async password middleware for TG cabinet routes
