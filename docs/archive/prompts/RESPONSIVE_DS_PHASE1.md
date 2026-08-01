# Responsive Design System - Phase 1

## Approach
Do not invent a second mobile site. Strengthen shared tokens + `responsive.css`, then fix cascade hotspots (hubs, admin, calendars, TG shell already shipped).

## Audit summary (severity)
| Sev | Issue | Status |
|-----|-------|--------|
| P0 | Admin tables bleed horizontally | Fixed via contained overflow + min-width |
| P0 | Avatar crop under sticky header (z-index 80 vs 200) | Fixed → `--z-modal` |
| P0 | Hub grids `minmax(360/380px)` overflow phones | Fixed → `min(100%, …)` |
| P1 | Admin week head/body scroll desync | Fixed → shared `.pa-week__scroll` |
| P1 | Drawer `100vw` overflow | Fixed → `100%` + safe-area |
| P1 | Toast/FAB ignore safe-area | Fixed |
| P1 | Modal z-index magic numbers | Normalized to tokens |
| P1 | Admin missing box-sizing / viewport-fit | Fixed |
| P2 | Fluid type incomplete (h3/body fixed) | Tokens now clamp() across scale |
| P2 | Touch targets / form gaps | Coarse pointer + stack gap rules |
| P2 | Hub CSS duplication | Primitives `.hub-layout` / `.hub-stats` / `.grid-auto-cards` added; migrate hubs gradually |

## Files touched
- `tokens.css`, `responsive.css`, `components.css`, `app.css`
- hubs: calendars, services, clients, bookings, specialist-bookings, calendar-schedule
- admin: `admin-platform.css`, layout, bookings_calendar template
- cache bust: `main.css?v=18`, `app.css?v=26`, admin tokens/css

## Out of scope this phase (next)
- Full hub CSS merge into one `hub-shared.css` (delete duplicated media blocks)
- Specialist month calendar list-fallback view
- Admin nav hamburger
- Landing deep polish
- Automated visual regression across 14 viewports

## Rules kept
No backend / route / API / brand color / identity changes.
