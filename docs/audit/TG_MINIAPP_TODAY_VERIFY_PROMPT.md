# Agent prompt: Verify today's Telegram Mini App features

Use after deploy on `https://allyourclients.ru` (login: specialist account).

## Scope (added 2026-09-09)
1. Mini App hub `/tg/` cards: **Клиенты**, **Статистика** (plus existing Записи / Управление).
2. Cabinet bottom nav: **Статистика**.
3. `/statistics/`: status counts, date range, Excel export.
4. `/clients/{id}/`: diagnostics tab — Excel export, delete result.
5. Excel must work **inside Telegram WebView**, not only desktop.

## Walkthrough
1. Open Mini App → `/tg/` → confirm cards Клиенты + Статистика.
2. Tap **Статистика** → change dates → **Выгрузить Excel** → file opens/downloads (no dead tap).
3. Tap **Клиенты** → open a card → **Выгрузить Excel** → file OK.
4. Diagnostics tab: delete one result (confirm), refresh — gone.
5. Bottom nav Статистика from `/booking/` or `/clients/`.
6. Smoke: `/dashboard/`, `/booking/`, hub still loads after auth.

## Fail if
- Export link no-ops in TG WebView.
- Eyes test still listed; OSOP/СОП missing gender gate.
- Reminder spam duplicates or wall-clock time ≠ calendar time.

## Commands
```text
pytest tests/test_phase8_mini_app.py tests/test_statistics_diagnostics_export_e2e.py tests/test_telegram_booking_notifications.py -q
```
Then live httpx/session walk with specialist credentials.
