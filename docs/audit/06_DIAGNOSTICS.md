# Diagnostics System

## Routes (profile-scoped)

| Method | Path | Auth |
|--------|------|------|
| GET | `/s/{slug}/diagnostics/` | Logged-in client |
| GET | `/s/{slug}/diagnostics/tests/{code}/` | Logged-in client |
| POST | `/s/{slug}/diagnostics/tests/{code}/submit/` | Logged-in client + CSRF |
| GET | `/s/{slug}/diagnostics/results/{id}/` | Owner of attempt |

Legacy `/diagnostics/` redirects to profile or home.

## Feature gate

`FEATURE_DIAGNOSTICS` enabled for consultant categories `psychologist` and `general`.

## Tables

- `client_specialist_links`
- `diagnostic_invitations`
- `diagnostic_attempts`

## Call chain (hub GET)

```
specialist_diagnostics_hub
  → resolve_consultant_by_slug_async (selectinload category)
  → consultant_has_feature
  → _require_logged_in_client
  → ensure_diagnostics_tables
  → touch_client_specialist_link (skip if specialist views own hub)
  → list_attempts_for_client
  → attempt_to_view (dict, no ORM in template)
  → page_context_async
```

## Production incidents

### P0-1: Table missing (ProgrammingError)
- **Cause:** Schema patch failed silently on deploy
- **Fix:** `ensure_diagnostics_schema()` + runtime ensure

### P0-2: MissingGreenlet
- **FACT:** Stack trace in asyncmy pool ping during `inspect().has_table()` on async connection
- **ROOT CAUSE:** `ensure_diagnostics_schema(bind=async_conn)` inside `run_sync`
- **FIX:** Async path uses `create_all` only; inspect only on sync pymysql engine in thread pool
- **VERIFY:** `tests/test_diagnostics_schema_async.py`, `test_diagnostics_e2e.py` (8 tests)

## Tests

- 7 e2e flows in `test_diagnostics_e2e.py`
- 1 regression in `test_diagnostics_schema_async.py`

## Gaps (P2)

- Invite flow `/d/{token}/`
- BDI end-to-end
- Result authorization negative tests
- Feature disabled 404 test
