# Agent prompt: Mini App Excel, diagnostics catalog, reminder timezone

Use for AllYourClients (`https://allyourclients.ru`) — Telegram Mini App + bot reminders + diagnostics catalog.

## Goals
1. Fix **Выгрузить Excel** in Telegram Mini App (statistics + client diagnostics) so the file actually downloads / opens.
2. Verify all **today’s** Mini App cabinet features: hub cards (Клиенты, Статистика), statistics date range + export, client card diagnostics delete/export, bottom nav.
3. Diagnostics catalog:
   - **Remove** test «Чтение эмоций по глазам» (`eyes`) from runnable list / hub / CRM.
   - **Add/align** OSOP from https://psytests.org/parent/osopFf-run.html with **gender selection** and scoring per source recommendations.
4. Telegram bot booking reminders: fix **wrong local time** and investigate **duplicate** reminder messages (same booking sent twice; also “6 часов” at wrong wall-clock).
5. Local e2e + live login (`kok321416x@yandex.ru`) until pass; push when asked or when completing this batch.

## Context clues (reminders)
Example (MSK expected): booking 10:00–11:00 on 09.09.2026.
- Message «через 6 часов» arrived ~09:27 → implies bot thinks booking is ~15:27 or timezone offset wrong.
- Message «через 1 час» at 14:23 for a 10:00 booking → reminder fired for wrong event clock / stale job / UTC vs Europe/Moscow mismatch.
- Duplicates at same second → double scheduler / double send path.

Check: `TIMEZONE` / `Europe/Moscow`, reminder job scheduling, booking_time stored as naive local vs UTC, specialist vs client notify, `NOTIFY_DEDUP`.

## Mini App Excel
Telegram WebView often blocks `<a download>` / blob navigation. Prefer:
- `Telegram.WebApp.downloadFile` if available, else `openLink` to absolute HTTPS export URL with session cookie, or open in `Browser` / external.
- Same fix for `/statistics/export.xlsx` and `/clients/{id}/diagnostics/export.xlsx`.
- Do not break desktop browser download.

## Diagnostics OSOP
- Study psytests OSOP form: items, gender gate, scales, interpretation bands.
- Match existing engine/catalog patterns (`app/diagnostics/`).
- Keep `osop` code if already present — replace/extend rather than duplicate.
- Remove `eyes` from `list_tests(only_runnable=True)` and any public hub cards.

## Verification order
1. Write/update this prompt if scope changes.
2. `pytest` for diagnostics catalog, reminders timezone, excel/tg helpers, mini app hub.
3. Live authenticated walk: `/tg/` → Клиенты → card → Excel; `/tg/` → Статистика → Excel; take OSOP with gender; confirm eyes gone.
4. Inspect reminder code paths + logs; add regression test for MSK wall time in message text.
5. Final smoke: login, booking, clients, statistics, diagnostics hub.

## Pass criteria
- [ ] Excel works inside Telegram Mini App WebView (and still on desktop).
- [ ] Hub has working Клиенты + Статистика; bottom nav Статистика OK.
- [ ] Eyes removed; OSOP runnable with gender and correct scoring vs psytests intent.
- [ ] Reminder message date/time matches specialist calendar local time; no duplicate spam for same reminder window.
- [ ] Live e2e green after deploy.

## Do not
- Rewrite unrelated Mini App auth.
- Commit secrets / tmp scripts with passwords.
- Claim done without live check after push.
