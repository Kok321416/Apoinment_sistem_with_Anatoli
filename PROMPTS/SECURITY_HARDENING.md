"""Security hardening references for the Security agent.

Methodology (high-star / industry):
- OWASP Cheat Sheet Series — https://cheatsheetseries.owasp.org/
- OWASP Top 10 — https://owasp.org/www-project-top-ten/
- openai/skills FastAPI web server security (~23k) —
  https://github.com/openai/skills/blob/main/skills/.curated/security-best-practices/references/python-fastapi-web-server-security.md
- tiangolo/fastapi (~80k+) security docs —
  https://github.com/tiangolo/fastapi
- encode/starlette TrustedHost / Session —
  https://github.com/encode/starlette
- sqlmap (attacker tool, for awareness) —
  https://github.com/sqlmapproject/sqlmap
- Playwright for abuse/smoke checks —
  https://github.com/microsoft/playwright

Stack facts for this repo:
- FastAPI + SQLAlchemy ORM + MySQL 8 (parameterized queries).
- App-level rate limits + nginx limit_req (not full CDN/WAF DDoS).
- CSRF on HTML state-changing forms; bot API uses HMAC.

Do NOT change product UX when hardening. Prefer fail-soft 429 with Retry-After.
"""
