# Agent prompt: Psychological diagnostics (client + specialist)

Use this when debugging or verifying diagnostics on AllYourClients (`https://allyourclients.ru`).

## Goal
Make client take → save → view and specialist CRM view fully functional. Do not change unrelated product areas unless needed to reach diagnostics; if you touch shared auth/booking, re-smoke them at the end.

## Client path (must work)
1. Open specialist public profile `/s/{slug}/` → «Перейти к диагностике».
2. If not logged in → welcome `/s/{slug}/welcome/?next=.../diagnostics/` → Telegram or contact form, then **real login** (gate alone is NOT enough).
3. Hub `/s/{slug}/diagnostics/` — list runnable tests + «История результатов».
4. Intro `/s/{slug}/diagnostics/tests/{code}/` → Run `/run/` wizard → Submit POST.
5. Result `/s/{slug}/diagnostics/results/{id}/` — scales visible; **not** preview/`unsaved` banner.
6. Return to hub — new attempt in history; open «Подробнее».

Invite alternate: `/d/{token}/` → login → `/d/{token}/start/` → test/hub.

Runnable codes: `bhs`, `bdi`, `wcq`, `schmischek`, `osop`, `eyes`.

## Specialist path (must work)
1. Login as specialist → `/clients/` → button «Диагностика» → `/clients/{id}/#diagnostics`.
2. Card tab «Диагностика»: history, scale cards, «Ссылка на диагностику» (invite API).
3. Open result (CRM `/diagnostics/results/{id}/` or card panel) — dual-role must **not** bounce away from CRM results.

## Pass criteria
- Submit commits `DiagnosticAttempt` with `status=completed`, linked `client_card_id`.
- Client hub history shows attempt; specialist card shows same.
- No 500 / MissingGreenlet on `/clients/{id}/` or hub.
- No yellow «результат не сохранён» after successful take.
- Invite API returns `{ok:true,url:...}` (not 500/schema).

## Fragile spots to watch
- Async ORM lazy-load / session **rollback** → MissingGreenlet in hub/CRM templates (rehydrate consultant after dirty session).
- Diagnostics tables missing on **async** bind → submit falls back to `/results/preview/` (unsaved); invite 500.
- Process-wide `_DIAGNOSTICS_DDL_READY` must not skip probing the request session bind.
- Async `create_all` must **commit** (SQLite rolls back DDL on session close).
- Prefer SAVEPOINT (`begin_nested`) over full `rollback()` on missing-table reads.
- Welcome gate without User account → redirect loop.
- Feature flag: psychologist/general only.
- Invite CSRF / use_count on start not on complete.

## Verification order
1. `pytest tests/test_diagnostics_*.py -q`
2. Live authenticated walk (client take + specialist CRM + invite).
3. Check server/app logs for exceptions on submit, hub, invite, `/clients/{id}/`.
4. Final smoke: login, profile, clients list, one booking page load if auth shared.

## Do not
- Rewrite unrelated booking/UI.
- Commit secrets/credentials.
- Mark done if only preview (unsaved) works.
- Claim prod fixed before deploy + live re-check.
