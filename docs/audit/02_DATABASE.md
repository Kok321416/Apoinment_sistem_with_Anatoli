# Database / SQLAlchemy Rules

## Dual engine architecture

| Layer | Engine | Driver | Use for |
|-------|--------|--------|---------|
| HTTP (FastAPI) | `create_async_engine` | `mysql+asyncmy` | All routers via `get_async_db()` |
| Schema / CLI | `create_engine` | `mysql+pymysql` | `db_schema.py`, commands, sync legacy |

**Rule:** Never call `inspect()` or sync ORM on connections from `AsyncSession` except inside `conn.run_sync()` with **DDL only** (`create_all`), not `has_table()`.

## AsyncSession settings

```python
expire_on_commit=False  # app/database.py — reduces post-commit attribute access issues
pool_pre_ping=True      # both engines — OK with SQLAlchemy 2.x + asyncmy
```

## MissingGreenlet prevention

1. Use `selectinload` / `joinedload` when serializing ORM objects in async routes
2. Prefer scalar dicts (`attempt_to_view`) over passing ORM to templates
3. `specialty_code_for_consultant` checks `sa_inspect` for unloaded category
4. Sync work off event loop: `asyncio.to_thread()` for pymysql schema ops

## Schema ensure

- **Deploy:** `ensure_all_schema()` on startup + `bootstrap_on_import()`
- **Safety net:** `ensure_diagnostics_schema()` via sync engine in thread pool
- **Runtime:** `ensure_diagnostics_tables(db)` — sync thread + async `create_all` in `run_sync` (no inspect on async bind)

## Migrations

No Alembic in repo. Schema changes via `db_schema.py` patches. Risk: failed patch marked attempted, not retried until explicit ensure.

## Known risky patterns

| Location | Risk |
|----------|------|
| `serialize_service` + `service.calendar` | Fixed: pass `calendar_name` from preloaded map |
| `platform_admin.py` missing `await` | Fixed |
| `password_required_middleware` | Sync SessionLocal in async path |
