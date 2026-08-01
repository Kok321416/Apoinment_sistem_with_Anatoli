# Agent orchestration — Appointment SaaS

Prod: `https://allyourclients.ru` · deploy: push to `main` · DB: **MySQL** (not Postgres).

## How to run work

1. **Architect** receives the task → splits scope → assigns one **domain agent** per file zone.
2. Domain agent implements **only its scope** (see `.cursor/rules/*.mdc`).
3. **QA** runs smoke/tests/browser **once**, after code is ready.
4. **Architect** merges narrative + test plan; human approves push.

Reference workflow: `PROMPTS/AGENT_ORCHESTRATION.md`.  
Compliance / RKN checklist: `PROMPTS/COMPLIANCE_RKN.md`.  
Diagram: `docs/agents-orchestration-diagram.png`.

## Agent roster

| Agent | Role | Owns |
|-------|------|------|
| **Architect** | Plan, scope, merge | No code by default |
| **Backend** | API, services, models | `app/routers/`, `app/services/`, `app/models/` |
| **Database** | Schema, indexes, queries | `app/db_schema.py`, `app/database.py` |
| **Visual** | UI web + Telegram WebView | `app/templates/`, `app/static/css/`, UI JS |
| **Public Booking** | Client booking funnel | `public/*`, `booking.css`, `public-*.js` |
| **Hubs** | Specialist CRM pages | calendars/booking/clients/profile/services hubs |
| **Calendar Schedule** | Slots editor | `calendar_detail`, `calendar-*.js/css` |
| **Telegram Bot** | Bot logic, Mini App bridge | `bot/`, `telegram-webapp.js` (logic only) |
| **Auth & OAuth** | Login, sessions, social | `app/auth/`, `oauth.py`, `auth.css`, login templates |
| **Platform Admin** | Admin panel (desktop) | `platform_admin/*`, `admin-platform.css` |
| **Performance** | Cache, slow paths | `response_cache.py`, `ttl_cache.py`, KPI hot paths |
| **Security** | CSRF, RBAC, secrets | `app/security/`, auth hardening |
| **QA** | Tests, browser checks | `tests/`, Playwright/Browser MCP |
| **DevOps** | Docker, CI, deploy | `docker-compose.yml`, `.github/workflows/` |
| **Compliance** | 152-ФЗ / РКН, согласия, legal docs | `legal_copy.py`, cookie consent, privacy/terms |
| **Mobile** | PWA, Capacitor Android / RuStore, `/apps/` | `mobile/`, `apps_copy.py`, PWA manifest; see `PROMPTS/MOBILE_APP.md` |
| **Product Designer** | UX spec before Visual/Mobile UI | mocks, DoD; rule `product-designer.mdc` |

## Long-lived tracks (GitHub)

| Branch | Focus |
|--------|--------|
| `track/site` | Website, landing, PWA, `/apps/` |
| `track/telegram` | Bot + Telegram Mini App |
| `track/android` | Capacitor shell, RuStore packaging |
| `main` | Production (push deploys) |

Mobile checklist: `PROMPTS/MOBILE_APP.md`.

## Token economy (mandatory)

- **Architect** writes a short plan (≤15 lines); does **not** read whole repo.
- **One domain agent per task** unless Architect explicitly splits into parallel non-overlapping scopes.
- Read **only files in scope**; use `grep`/`glob` before opening large files.
- **No** second full-repo explore subagent if the first already returned paths.
- **QA / Browser MCP** only after implementation; not during design.
- **MySQL MCP**: `SELECT`, `SHOW`, `EXPLAIN` only — no `INSERT`/`UPDATE`/`DELETE`/`DROP`.
- **Docker MCP**: prefer `logs --tail 200`, not unbounded follow.
- **GitHub MCP**: for PR/CI, not for browsing unrelated repos.
- Do **not** commit `data.db` or `.env`.
- Bump `?v=` on changed static assets.

## MCP as agent hands

Copy `.cursor/mcp.json.example` → `.cursor/mcp.json` and fill credentials locally (file is gitignored).

| MCP | Used by | Purpose |
|-----|---------|---------|
| Git / GitHub | Architect, QA, DevOps | diff, PR, CI |
| Docker | DevOps, Backend, QA | compose up, logs |
| MySQL | Database, Backend | schema, explain |
| Browser | Visual, QA, Public Booking | mobile 375px, TG flows |

## Open-source references (methodology, not runtime deps)

- Roles / crews: [CrewAI](https://github.com/crewAIInc/crewAI), [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
- Stateful workflows: [LangGraph](https://github.com/langchain-ai/langgraph)
- Autonomous PRs (optional): [OpenHands](https://github.com/OpenHands/OpenHands), [Aider](https://github.com/Aider-AI/aider)
- E2E mobile: [Playwright](https://github.com/microsoft/playwright)
- Capacitor (Android shell): [ionic-team/capacitor](https://github.com/ionic-team/capacitor)

## Out of scope for agents unless user asks

- Force push to `main`
- Admin mobile hamburger (admin is desktop-only)
- Committing secrets or `data.db`
