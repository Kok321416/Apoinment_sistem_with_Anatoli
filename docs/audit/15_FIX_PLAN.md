# Fix Plan (prioritized)

## Immediate (this week)

1. **Deploy MissingGreenlet fix** (`diagnostics_service.py`, `db_schema.py`)
2. **Prod one-shot:** `python -c "from app.db_schema import ensure_diagnostics_schema; ensure_diagnostics_schema()"`
3. **Platform admin:** add missing `await` on `platform_client_detail_async`, `write_admin_audit_async`
4. **Verify** `/s/spec/diagnostics/` on prod after deploy

## Short term (2 weeks)

5. Mini App: verify cookies (`SESSION_SAME_SITE=none`, HTTPS), run `/health/mini-app`
6. Fix `/book/` bot keyboard → correct URL or remove
7. `selectinload(Service.calendar)` in catalog API
8. Move password middleware to async path or exempt TG cabinet routes
9. Update stale Mini App tests and docs

## Medium term

10. Reduce sync `SessionLocal` in async request path (notify/errors can stay threaded)
11. Expand diagnostics tests (invite flow, BDI, authz on results)
12. CI job: `pytest tests/test_diagnostics_e2e.py` + smoke on every push

## Regression checklist after diagnostics fix

- [ ] GET hub logged-in client
- [ ] Submit BHS test
- [ ] View result
- [ ] Specialist opens own diagnostics (no self-link)
- [ ] Tables missing → auto-create without 500
