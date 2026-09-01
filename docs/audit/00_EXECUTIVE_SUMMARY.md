# Executive Summary — Project Audit (2026-09-01)

## Project

**allyourclients.ru** — FastAPI appointment/cabinet platform for specialists (psychologists, coaches). Clients access specialists via public profiles `/s/{slug}/`. Telegram Mini App at `/tg/`.

**Stack:** FastAPI + Jinja2 + SQLAlchemy 2 async (asyncmy/MySQL prod, aiosqlite tests) + sync pymysql for schema/CLI + aiogram bot.

**State: 6/10** — core specialist cabinet works; diagnostics and Mini App have production incidents; dual sync/async stack creates recurring SQLAlchemy issues.

## What works

- Specialist cabinet: dashboard, bookings, clients CRM, manage (calendars/services), profile
- Public specialist profiles, booking flow, slots
- Telegram bot + webhook mode
- Telegram Mini App shell (`/tg/`), initData auth API
- Platform admin (mostly async)
- 49 test files; diagnostics e2e (7 tests)

## Critical issues (P0)

| ID | Issue |
|----|-------|
| P0-1 | `GET /s/{slug}/diagnostics/` — MissingGreenlet (fixed locally, not deployed) |
| P0-2 | Diagnostic tables may be missing on prod MySQL until schema ensure runs |
| P0-3 | `platform_client_detail_async` missing `await` in platform admin |
| P0-4 | `write_admin_audit_async` never awaited — audit log empty |

## High (P1)

- Telegram Mini App: cookies/SameSite, cold start, specialist-only hub vs client initData login
- `/book/` bot link dead (redirects to `/`)
- `service.calendar` lazy load risk on `/services/catalog`
- Sync `SessionLocal` in async middleware (password gate) blocks event loop
- Stale tests/docs for client cabinet mode (removed)

## Latest production error (fixed in working tree)

**MissingGreenlet** on `GET /s/spec/diagnostics/` — root cause: `inspect().has_table()` called on async-adapted MySQL connection inside `ensure_diagnostics_tables()`. Fix: sync schema via pymysql in thread pool; async DDL via `create_all` only inside `run_sync` without `inspect`.

## Next steps

1. Deploy MissingGreenlet fix
2. Run `ensure_diagnostics_schema()` on prod once
3. Fix platform admin missing `await`s
4. Mini App health check: `/health/mini-app`, cookies, IPv6 DNS
5. Add regression test for ensure_diagnostics_tables on MySQL-like path

See `12_PROBLEMS.md`, `15_FIX_PLAN.md`, `16_AGENT_OWNERSHIP.md`.
