# After apt install redis-server (preferred on VPS):
#   systemctl enable --now redis-server
#   echo 'REDIS_URL=redis://127.0.0.1:6379/0' >> /path/to/app/.env
#   restart web app (Passenger/uvicorn)
#
# Apply indexes:
#   cd /path/to/app && .venv/bin/alembic upgrade head
#
# Telegram webhook (aiogram inside FastAPI):
#   1. Generate TELEGRAM_WEBHOOK_SECRET (long random) in .env
#   2. Restart web app — startup calls setWebhook to
#      https://<SITE_URL>/telegram/webhook/<secret>
#   3. Stop and disable separate bot polling unit (systemctl stop/disable ...),
#      otherwise Telegram returns 409 Conflict.
#   Dev without webhook: leave TELEGRAM_WEBHOOK_SECRET empty and run
#      python -m bot.run
#
# Health check:
#   curl -s https://allyourclients.ru/health
#   expect redis.mode redis|memory|memory-fallback
