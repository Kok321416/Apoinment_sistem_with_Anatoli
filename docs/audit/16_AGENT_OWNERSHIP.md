# Agent Ownership

Work in order: **AUDIT → FINDINGS → PLAN → OWNERSHIP → IMPLEMENT → TEST**

| Agent | Scope | Key files | Current priority |
|-------|--------|-----------|------------------|
| **Architect** | Structure, deps, tech debt | `main.py`, `deps.py`, `docs/audit/` | Document dual sync/async policy |
| **Backend** | API, services, middleware | `routers/`, `services/` | Fix missing `await` in platform_admin |
| **Database** | SQLAlchemy, schema, queries | `database.py`, `db_schema.py`, `models/` | MissingGreenlet, diagnostics schema |
| **Telegram Mini App** | WebApp, initData, mobile | `telegram-webapp.js`, `api.py`, `tg-webapp.css` | Cookie/session, cold start |
| **Diagnostics** | Profile diagnostics feature | `public_specialist.py`, `diagnostics_service.py` | Deploy P0 fix, expand tests |
| **Security** | Auth, CSRF, secrets | `auth/`, `security/`, `config.py` | TG initData validation audit |
| **QA** | Tests, regression | `tests/` | diagnostics e2e, mini app smoke |
| **DevOps** | Deploy, nginx, Passenger | `scripts/`, prod env | Schema ensure on deploy, health probes |

## File conflict rules

- Only **Database** agent edits `diagnostics_service.py` + `db_schema.py` for schema issues
- Only **Telegram** agent edits `telegram-webapp.js` + `tg-webapp.css` without backend auth changes
- Cross-cutting changes (e.g. password middleware) need **Architect** approval in plan

## Open-source references (patterns, not blind copy)

| Topic | Reference approach |
|-------|-------------------|
| FastAPI async SQLAlchemy | SQLAlchemy 2.0 async docs; `selectinload` for relationships |
| Telegram WebApp auth | Official Telegram `initData` HMAC validation |
| Production FastAPI | Separate sync engine for migrations; async for requests |
