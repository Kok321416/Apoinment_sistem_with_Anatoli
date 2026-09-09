# Agent prompt: Statistics hub + diagnostics delete/export

Use this for AllYourClients specialist cabinet work (`https://allyourclients.ru`).

## Goal
1. Move all booking/CRM “how many / cancelled / completed” style stats off `/booking/`, `/clients/`, and similar pages into a dedicated **Статистика** section that loads only when opened.
2. On Statistics: status breakdown, date range filter, Excel export of consultations + visitor brief data.
3. On client profile: delete each diagnostics result; Excel export of brief client profile + all diagnostics (formatted workbook).

Do not rewrite unrelated booking/Telegram flows. After push, re-verify live until pass.

## Product rules

### Statistics (`/statistics/`)
- New sidenav item **Статистика** (desktop + mobile if applicable).
- Page must **not** be loaded as part of bookings/clients SSR; those pages must stop showing dashboard KPI strips (today/tomorrow/total/new/upcoming/completed counts used as “stats”).
- Keep operational lists/filters on bookings/clients; only remove the summary-stat blocks that duplicate Statistics.
- Statistics content:
  - Counts by booking status: pending, confirmed, completed, cancelled (and total).
  - Optional: consultation totals in range.
  - Date filter: `from` / `to` (inclusive, specialist timezone if available; else UTC/local site TZ).
  - Button **Выгрузить Excel**: rows = consultations in range with date/time, status, service, client name/phone/email/telegram (brief).
- Stats queries run only on `/statistics/` (and its export endpoint), not on every bookings/clients GET.

### Diagnostics (client card)
- Each result card: **Удалить** (confirm). Deletes only that specialist’s `DiagnosticAttempt`; hard delete OK.
- On client profile (CRM card): **Выгрузить Excel** — visible whenever the profile is open (diagnostics tab or header actions).
- Workbook contents:
  - Sheet or top block: brief client profile (name, phone, email, telegram, notes if present).
  - Diagnostics: one row/block per attempt — test title, date, summary, scales (score/band) in separate cells; readable columns, header styling, reasonable column widths.
- Ownership: only the card’s consultant may delete/export.

## Technical constraints
- Prefer `openpyxl` for xlsx (check with Sonatype `/check-dependency` before add).
- Reuse `bookings_hub` / booking queries; extend rather than duplicate CRM auth patterns from `client_card_detail`.
- CSRF on mutating delete.
- Russian UI labels.
- Tests: unit/e2e for statistics page + date filter + export content-type; diagnostics delete + export; bookings/clients no longer expose removed KPI blocks (or assert absence of `#bookings-dashboard` / CRM stat strip).
- Live: login → open Statistics tab → filter → export; open client → delete one result → export Excel; smoke bookings/clients/profile.

## Pass criteria
- [ ] Nav has Статистика; `/statistics/` shows status counts + date range.
- [ ] `/booking/` and `/clients/` no longer show the removed summary statistics strips.
- [ ] Excel consultations download works for chosen range.
- [ ] Delete removes attempt from card and DB; other clients unaffected.
- [ ] Client Excel has profile + diagnostics cells formatted.
- [ ] Local pytest green; after push, live e2e pass.

## Do not
- Commit secrets / tmp probe scripts.
- Claim done on preview-only or broken export.
- Mark complete before post-deploy live check.
