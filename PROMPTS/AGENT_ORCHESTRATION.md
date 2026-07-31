# Agent orchestration playbook

Stack: FastAPI + Jinja + MySQL + Telegram bot + Docker.  
Prod deploy: push `main`.

## Task intake template

```
Goal:
Scope files:
Out of scope:
Primary agent:
DoD:
Test plan:
```

## Pipeline (token-cheap)

```
User task
  → Architect (≤15-line plan, assign 1–3 agents)
  → Domain agent(s) in parallel only if file scopes do not overlap
  → QA once (tests + optional browser 375px)
  → Human: review / push
```

## Parallelism rules

Allowed in parallel:
- Visual + Backend (templates vs services)
- Calendar Schedule + Hubs (detail vs list)
- Telegram Bot + Public Booking (bot vs public HTML)

Never parallel on the same file.

## MCP usage by phase

| Phase | Allowed MCP |
|-------|-------------|
| Plan | none / light grep |
| Implement | Filesystem, Git |
| Verify | MySQL (read), Docker logs, Browser |
| Ship | GitHub PR |

## DoD checklist (any UI task)

- [ ] Desktop unchanged unless task says otherwise
- [ ] Mobile ≤768 where applicable
- [ ] TG WebView: no body scroll trap regressions
- [ ] Static `?v=` bumped
- [ ] No secrets / `data.db` in commit

## Example: mobile calendar schedule

1. Architect → Calendar Schedule (+ Visual if tokens)
2. Implement day-first ≤768; keep desktop week grid
3. QA: `/calendars/{id}/` at 375px + one TG open
4. Ship

## Example: booking gate / auth

1. Architect → Auth & OAuth + Public Booking
2. Backend only if session/API changes
3. QA: guest → login → return to `/s/...`
