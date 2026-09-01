# Testing

## Current coverage

- ~49 test files
- Diagnostics: 8 tests (7 e2e + 1 schema regression)
- Telegram: `test_telegram_social_duplicate.py`, `test_phase8_mini_app.py` (stale)
- Async smoke: `test_async_db_smoke.py`, `test_site_smoke_e2e.py`

## Added this session

| Test | Purpose |
|------|---------|
| `test_diagnostics_schema_async.py` | MissingGreenlet regression — schema ensure on async session |

## Gaps (priority)

### P1
- Mini App auth flow integration test
- Platform admin client detail (after await fix)

### P2
- Playwright `/tg/` mobile viewport (390×844)
- Catalog API with calendar_id set
- Diagnostics invite + authz

## Run commands

```bash
.venv\Scripts\python.exe -m pytest tests/test_diagnostics_e2e.py tests/test_diagnostics_schema_async.py -q
.venv\Scripts\python.exe -m pytest tests/ -q --ignore=appointment_system
```

## pytest config

- `asyncio_mode = auto` in `pytest.ini`
- MySQL marker for integration tests
