# Система онлайн записи — Все клиенты здесь

FastAPI + Jinja2 + MySQL + Telegram bot + Capacitor (Android / RuStore).

Prod: https://allyourclients.ru · деплой: push в `main`.

## Возможности

- Кабинет специалиста: календари, услуги, записи, клиенты, профиль
- Публичная запись клиентов
- Telegram-бот и Mini App
- OAuth (Яндекс, VK, Telegram), 2FA
- Android WebView shell (Capacitor)

## Быстрый старт

```bash
cp env.example .env
# Заполните .env (SECRET_KEY, DB_*, TELEGRAM_BOT_TOKEN, …)

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Бот (отдельный процесс):

```bash
python -m bot.run
```

Docker:

```bash
docker compose up -d
```

## Тесты

```bash
python -m pytest tests/ -q
```

## Структура

```
app/           # FastAPI (routers, models, services, templates, static)
bot/           # Telegram bot
mobile/        # Capacitor Android
tests/         # pytest
docs/          # design system, audit, TG setup
PROMPTS/       # актуальные чеклисты агентов
scripts/       # migrate / bot / reminders
```

Схема БД: runtime-патчи в `app/db_schema.py` (каталог Alembic удалён как пустой).

## Документация

- `AGENTS.md` — оркестрация агентов
- `docs/PROJECT_AUDIT.md` — аудит и план очистки
- `docs/DESIGN_SYSTEM.md` — UI-токены
- `docs/TELEGRAM_MINI_APP_SETUP.md` — Mini App
- `mobile/README.md` — Android shell
- `docs/archive/` — устаревшие планы

## Деплой

- GitHub Actions: `.github/workflows/deploy.yml` (ветка `main`)
- Web: Passenger (`passenger_wsgi.py`)
- Напоминания: cron `./scripts/run_reminders.sh`
