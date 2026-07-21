#!/usr/bin/env bash
# Database schema is managed by existing MySQL tables (migrated from Django).
# For new deployments use: alembic upgrade head
set -e
SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_ABS/.." && pwd)"
[ -n "${APP_DIR:-}" ] && ROOT="$APP_DIR"
cd "$ROOT"

PYTHON="${ROOT}/venv/bin/python"
[ ! -x "$PYTHON" ] && PYTHON="python"

"$PYTHON" -c "
from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
print('Database connection OK')
"

"$PYTHON" -c "from app.db_schema import ensure_telegram_login_schema; ensure_telegram_login_schema(); print('Auth schema OK')"

"$PYTHON" -c "
from app.db_schema import ensure_all_schema, get_schema_health
ensure_all_schema()
health = get_schema_health()
print('App schema OK', health)
if health.get('degraded'):
    raise SystemExit('Schema degraded: ' + ', '.join(health.get('issues') or []))
"
