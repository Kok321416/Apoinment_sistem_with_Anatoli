# Система онлайн записи консультантов

FastAPI приложение для управления записями на консультации.

## Возможности

- Регистрация и авторизация (email, Google, Telegram)
- Управление календарями и временными окнами
- Публичная страница записи клиентов
- Telegram-бот (запись, мои записи, уведомления)
- Google Calendar синхронизация
- Напоминания в Telegram (cron)

## Технологии

- FastAPI + Uvicorn
- SQLAlchemy + MySQL
- Jinja2 templates
- Docker & Docker Compose
- Nginx

## Быстрый старт

```bash
cp env.example .env
# Заполните .env (TELEGRAM_BOT_TOKEN, SECRET_KEY, DB_*)

pip install -r requirements.txt
uvicorn app.main:app --reload
```

В другом терминале:

```bash
python -m bot.run
```

## Структура

```
app/           # FastAPI приложение
  main.py      # Точка входа
  routers/     # HTTP маршруты
  models/      # SQLAlchemy модели
  services/    # Бизнес-логика
  templates/   # HTML шаблоны
bot/           # Telegram бот
scripts/       # run_bot.sh, run_reminders.sh
```

## Деплой

- Docker: `docker compose up -d`
- VPS (reg.ru): GitHub Actions deploy.yml
- Напоминания: cron `./scripts/run_reminders.sh` каждые 15-30 мин
