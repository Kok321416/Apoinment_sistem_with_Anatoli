# Database / SQLAlchemy Rules

## Dual engine architecture

| Layer | Engine | Driver | Use for |
|-------|--------|--------|---------|
| HTTP (FastAPI) | `create_async_engine` | `mysql+asyncmy` | All routers via `get_async_db()` |
| Schema / CLI | `create_engine` | `mysql+pymysql` | `db_schema.py`, commands, sync legacy |

**Rule:** Never call `inspect()` or sync ORM on connections from `AsyncSession` except inside `conn.run_sync()` with **DDL only** (`create_all`), not `has_table()`.

## Getting an async session

| Context | Use |
|---------|-----|
| Request handler | `db: AsyncSession = Depends(get_async_db)` |
| Outside a request (SSE, threads, CLI) | `async with async_session() as db` |
| Tests / scripts | `configure_async_sessionmaker(factory)` + `reset_async_sessionmaker()` |

**Rule:** the engine and session factory in `app/database.py` are private. Reaching for them directly
(`_ensure_async_engine`, `_AsyncSessionLocal`) broke unrelated callers and test setup on every rename,
and hand-rolled sessions leaked when a caller forgot to close. `tests/test_database_session_contract.py`
fails if a module goes back to the private names.

## Settings

`get_settings()` returns one object per process (`app/config.py`), because modules capture it at
import: a second instance would leave them reading stale config. Override it in place — via
`settings_overrides(...)` or monkeypatch — and never rely on `cache_clear()` producing a fresh object.
Overrides set on the object shadow class defaults, so tests restore instance state after each test
(`tests/conftest.py`); `tests/test_settings_identity_contract.py` pins the invariant.

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
