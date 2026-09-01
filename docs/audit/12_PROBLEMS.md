# Problem Register

## P0 — Critical

### P0-1 MissingGreenlet on diagnostics hub
- **Status:** Fixed locally (pending deploy)
- **Component:** diagnostics / SQLAlchemy
- **File:** `app/services/diagnostics_service.py` — `ensure_diagnostics_tables`
- **Root cause:** `ensure_diagnostics_schema(bind=async_conn)` called `inspect().has_table()` on asyncmy-adapted connection → `pool_pre_ping` → `await_only()` outside greenlet
- **Impact:** 500 on `GET /s/{slug}/diagnostics/`
- **Fix:** Remove inspect on async bind; sync ensure in thread; async `create_all` only inside `run_sync`
- **Status:** Fixed locally (pending deploy)

### P0-2 Missing diagnostic tables on prod
- **Component:** database / deploy
- **Root cause:** `ensure_schema_patches` runs once; failed `create_all` not retried; `_SCHEMA_PATCHES_ATTEMPTED` guard
- **Impact:** ProgrammingError table doesn't exist (prior error)
- **Fix:** Runtime `ensure_diagnostics_schema` + startup `ensure_all_schema`
- **Status:** Mitigated in code; verify on prod

### P0-3 Platform admin client detail broken
- **File:** `app/routers/platform_admin.py` ~673
- **Problem:** `platform_client_detail_async(...)` without `await`
- **Impact:** Admin client pages non-functional
- **Status:** Fixed (await added)

### P0-4 Admin audit never written
- **File:** `app/routers/platform_admin.py` (28 calls)
- **Problem:** `write_admin_audit_async(...)` without `await`
- **Impact:** Empty audit log
- **Status:** Fixed (await added)

## P1 — High

### P1-1 Telegram Mini App session not sticking
- **Hypothesis:** `SESSION_SAME_SITE` not `none` on HTTPS, or cookie blocked in WebView
- **Check:** `/health/mini-app`, browser devtools in TG

### P1-2 Mini App cold start / DNS
- **Hypothesis:** Passenger+MySQL slow TTFB; IPv6 AAAA hang on mobile
- **Check:** `scripts/check_mini_app_health.py`

### P1-3 initData creates client-only users
- **Impact:** Specialist sees guest hub after silent auth until full login
- **File:** `telegram_webapp_auth.py`

### P1-4 Password-set middleware interrupts TG users
- **File:** `app/main.py` password_required_middleware
- **Impact:** Redirect to `/accounts/password/set/` inside WebView

### P1-5 Lazy load `service.calendar` in catalog API
- **File:** `app/services/services_catalog.py`
- **Status:** Fixed — calendar_name from preloaded map

### P1-6 Dead `/book/` bot link
- **File:** `bot/keyboards.py`, `bot/bot.py`, `bot/handlers/commands.py`
- **Status:** Fixed — points to `/tg/?mode=client`

## P2 — Medium

- Sync OAuth HTTP in async callbacks (`oauth.py`)
- Duplicate `list_errors_async` in `platform_errors.py`
- Stale tests: `test_phase8_mini_app.py` expects removed UI
- `appointment_system/` Django scaffold untracked, unrelated

## P3 — Low

- `datetime.utcnow()` deprecation warnings
- FastAPI `on_event` deprecated → lifespan
- Global `overflow-wrap` was breaking mobile text (fixed in 45765be)
