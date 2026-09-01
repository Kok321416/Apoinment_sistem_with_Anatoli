# Architecture Map

```
Telegram Bot (aiogram) ──HTTP──► FastAPI /api/*
                                      │
Telegram Mini App /tg/ ──same-origin──┤
Browser (cabinet)      ──cookies──────┤
Public client /s/{slug}/ ─────────────┤
                                      ▼
                         Middleware (abuse, errors, password gate)
                                      ▼
                         Routers (async, AsyncSession)
                                      ▼
                         Services (async + legacy sync twins)
                                      ▼
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
    AsyncEngine (mysql+asyncmy)                    SyncEngine (mysql+pymysql)
    get_async_db()                                 SessionLocal, db_schema, CLI
              ▼                                               ▼
                         MySQL (prod) / SQLite (dev)
```

## Key directories

| Path | Role |
|------|------|
| `app/main.py` | FastAPI entry, middleware, startup schema |
| `app/routers/` | HTTP routes (pages, api, oauth, public_specialist) |
| `app/services/` | Business logic (~60 modules) |
| `app/models/` | SQLAlchemy ORM |
| `app/db_schema.py` | Idempotent DDL patches (sync engine) |
| `app/auth/` | Session cookies, login |
| `app/templates/` | Jinja2 HTML |
| `app/static/` | CSS/JS |
| `bot/` | Telegram bot (async api_client) |
| `tests/` | pytest (smoke, e2e, domain) |

## Data flows

### Diagnostics (profile-scoped)

```
GET /s/{slug}/diagnostics/
  → resolve consultant by slug (selectinload category)
  → require logged-in client (not gate-only)
  → ensure_diagnostics_tables
  → list_attempts_for_client
  → render diagnostics_hub.html
```

### Telegram Mini App auth

```
GET /tg/ (no DB)
  → telegram-webapp.js boot
  → POST /api/telegram/webapp-auth { init_data }
  → HMAC validate → User/SocialAccount → session cookie
  → GET /api/telegram/hub-state
  → links to /dashboard/, /booking/, /manage/
```

## Dual-stack note

HTTP layer is **fully async**. Notifications, schema patches, error logging, password middleware still use **sync** `SessionLocal` — intentional but risky under load.
