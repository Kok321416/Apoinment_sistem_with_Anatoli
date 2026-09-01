# Test Failure Matrix — QA Stabilization (2026-09-01)

Base commit: `a385f14`  
Full pytest after fixes: **203 passed, 0 failed**

| Test | Classification | Root Cause | Fix | Status |
|------|----------------|------------|-----|--------|
| `test_diagnostics_e2e` (6 tests) | **REAL BUG** + TEST INFRA | Starlette ≥0.40 `TemplateResponse(request, name, ctx)` vs legacy `TemplateResponse(name, ctx)` → Jinja cache `TypeError: unhashable type: 'dict'` | `CompatJinja2Templates` in `app/templating.py` | **PASS** |
| `test_site_smoke_e2e` (2 tests) | **REAL BUG** (same) | Same TemplateResponse signature mismatch | Same compat layer | **PASS** |
| `test_smoke::test_services_page_*` | **OUTDATED TEST** | `_require_user` removed; `/services/` redirects to `/manage/#services` unless `?legacy=1`; async routes | Rewrote with `get_async_db` + `_require_user_async` mocks | **PASS** |
| `test_smoke::test_booking_page_*` | **OUTDATED TEST** | Sync `get_db` override; booking route uses `get_current_user_async` | Async fixture + patch `get_current_user_async` | **PASS** |
| `test_register_email::*` | **TEST INFRA** | Register route uses `get_async_db`; test hit real SQLite without tables | Async in-memory DB fixture | **PASS** |
| `test_dual_role_acceptance::test_default_active_mode_*` | **OUTDATED TEST** | Product default for consultant is `MODE_SPECIALIST`, not `client` | Renamed + updated assertion | **PASS** |
| `test_phase9::test_self_booking_allowed` | **REAL BUG** | `book_ahead_hours or 24` treats `0` as falsy → 24h minimum | `24 if ahead is None else int(ahead)` in bookings/slots | **PASS** |
| `test_phase10::test_platform_admin_gate` | **OUTDATED TEST** | Platform admin async; patch target `require_platform_admin_async` on router module | Async DB fixture + correct patch path | **PASS** |
| `test_perf_phase_ef::test_alembic_*` | **TEST INFRA** + **REAL BUG** | `exec_module` imports `alembic.op` (fails in pytest); `003` had wrong `down_revision` | Parse revision chain from file text; fix `003_booking_source.py` | **PASS** |
| `test_admin_a8::test_kpi_stream_route_registered` | **OUTDATED TEST** | FastAPI `_IncludedRouter` hides nested paths from `app.routes` | Assert via `app.openapi()["paths"]` | **PASS** |

## Additional tests added

| Test | Purpose | Status |
|------|---------|--------|
| `test_ensure_diagnostics_tables_concurrent_calls_are_idempotent` | Race on parallel schema ensure | **PASS** |
| `test_diagnostics_result_idor_redirects_other_client` | Client B cannot read client A result | **PASS** |
| `test_phase8_mini_app` (expanded) | webapp-auth, hub-state, invalid/expired initData, new user, lost cookie | **PASS** |

## Not in original 16 but fixed during run

| Area | Issue | Fix |
|------|-------|-----|
| `app/templating.py` | TemplateResponse compat | `CompatJinja2Templates` |
| `alembic/versions/003_booking_source.py` | Broken revision chain | `down_revision = "002_async_phase_e"` |
| `app/services/bookings.py`, `slots.py` | `book_ahead_hours=0` ignored | None-safe default |

## P2 (not blocking P1 commit)

| Item | Status |
|------|--------|
| Playwright Mini App E2E | Not added — no existing Playwright infra |
| Production cookie WebView trace | **UNKNOWN** |
| Production logged-in diagnostics | **BLOCKED** — requires user session |
| `auth_done` + re-auth JS E2E | Covered by unit/API tests; browser E2E deferred |
