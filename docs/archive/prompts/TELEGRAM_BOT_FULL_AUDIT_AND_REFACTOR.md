# Промпт: полный аудит и рефакторинг Telegram-бота

> Скопируйте блок ниже целиком в чат с самой сильной доступной моделью (Claude Opus / GPT‑5.x / аналог).
> Режим: Agent / Coding с доступом к репозиторию.
> Цель первого прохода: **только анализ + архитектура + план**. Код менять только после явного подтверждения.

---

## PROMPT START

Ты — principal engineer / staff backend architect с экспертизой в:
- Telegram Bot API (webhook, polling, deep links, Login Widget, inline/reply keyboards, FSM, rate limits, idempotency)
- Python async backend (FastAPI, SQLAlchemy, Redis, background workers)
- Product architecture для SaaS CRM записи клиентов
- Mobile-ready API design (будущее iOS/Android приложение)
- Security (HMAC, token rotation, least privilege, PII)
- Ops (systemd, Docker, cron, observability, zero-downtime deploy)

### Контекст продукта

Проект: система онлайн-записи специалистов `All Your Clients` / `allyourclients.ru`.
Стек сайта: FastAPI + SQLAlchemy + Jinja templates + MySQL (production, Passenger/reg.ru) / SQLite (dev).
Telegram используется для:
1. Клиентов: подтверждение записи, «мои записи», напоминания, вход/регистрация на сайт.
2. Специалистов: уведомления о новых записях, статусах, напоминания, deep-link подключение интеграций.
3. Auth: Telegram Login Widget + deep-link login/signup/connect.

В будущем будет мобильное приложение. Любая архитектура бота должна опираться на **единый backend API**, пригодный и для web, и для Telegram, и для mobile.

### Текущая архитектура (факт из репозитория)

Бот сейчас:
- Отдельный процесс long-polling: `python -m bot.run`
- Raw Telegram Bot API через `requests` (НЕ aiogram / НЕ python-telegram-bot)
- БД напрямую НЕ использует
- Ходит в FastAPI по HTTP с HMAC (`BOT_API_SECRET`) или fallback `X-Bot-Token`
- Уведомления и напоминания в основном шлёт сам сайт (`app/services/telegram.py` + cron `app.commands.send_reminders`)

Ключевые файлы:
- Bot: `bot/run.py`, `bot/bot.py`, `bot/api_client.py`, `bot/config.py`, `bot/copy.py`
- Site API: `app/routers/api.py`, `app/security/bot_api.py`
- Notifications: `app/services/telegram.py`
- Auth TG: `app/services/telegram_auth.py`, `app/routers/oauth.py`
- Models: `Booking.telegram_id`, `Booking.link_token`, `Integration.telegram_*`, `TelegramLoginRequest`, `SocialAccount`
- Ops: `deploy/telegram-bot.service.example`, `scripts/run_bot.sh`, `scripts/run_reminders.sh`, `.github/workflows/deploy-bot.yml`
- Docs (частично устарели): `TELEGRAM_ЧТО_СДЕЛАТЬ.md`, `LOGS_AND_COMMANDS.md`

Известные pain points:
- Docs drift (Django leftovers)
- Дублирование send-логики (бот + сайт)
- Polling + риск 409 Conflict при двух инстансах
- Нет webhook-режима в коде
- Фрагментация identity клиента (telegram_id vs SocialAccount vs ClientCard.telegram)
- Fallback auth на bot token при пустом `BOT_API_SECRET`
- ThreadPoolExecutor без ordering per chat
- Reminder flags названы `*_24h_*` / `*_1h_*`, но окна берутся из настроек календаря
- docker-compose не всегда прокидывает секреты
- Нет mobile-ready event/notification contract

### Жёсткие цели аудита

Нужен **полный аудит + целевая архитектура + поэтапный план рефакторинга/переписывания**.
Можно полностью переписать бота. Критерий выбора решений: **максимальная эффективность, надёжность, скорость разработки и готовность к mobile**.

Приоритеты (по убыванию):
1. Надёжность доставки сообщений и отсутствие дублей
2. Безопасность (HMAC, secrets, deep-link TTL, least privilege)
3. Единый backend-контракт для Web / Telegram / Mobile
4. Скорость отклика бота и UX
5. Операционная простота на shared hosting / VPS
6. Расширяемость (новые события, мультиканальность, push в будущем)

### Что нужно сделать на первом этапе (ТОЛЬКО АНАЛИЗ)

Не пиши продакшен-код и не делай массовый рефакторинг, пока не выдашь полный отчёт и не получишь подтверждение.

#### Часть A. Inventory (карта текущего функционала)

1. Полный список команд, callback_data, deep-link payload, reply-кнопок.
2. Sequence diagrams для ключевых флоу:
   - клиент записался → подтвердил Telegram → получает напоминания
   - специалист подключил уведомления
   - login/signup/connect через Telegram
   - изменение статуса записи на сайте → сообщение в Telegram
   - cron reminders
3. Матрица ответственности: что делает бот-процесс, что делает сайт, что делает cron.
4. Матрица identity: как связываются User / SocialAccount / Booking.telegram_id / Integration.telegram_chat_id / ClientCard.telegram.
5. Список API endpoints bot↔site, auth, timeout, idempotency, ошибки.

#### Часть B. Quality audit

Проверь и оцени по шкале 1–10 с доказательствами из кода:
- Architecture fitness
- Security
- Reliability / idempotency
- Performance / concurrency
- Observability (logs, metrics, tracing)
- DX / maintainability
- UX bot flows
- Mobile-readiness
- Ops / deploy safety
- Documentation accuracy

Для каждой проблемы дай:
- severity: Critical / High / Medium / Low
- impact
- root cause
- evidence (file + symbol)
- proposed fix
- effort (S/M/L)
- risk of change

#### Часть C. Target architecture (рекомендация)

Сравни минимум 3 варианта и выбери один как primary recommendation:

Вариант 1. Улучшить текущий raw Bot API + polling (минимальный риск)
Вариант 2. Переписать на aiogram 3.x + webhook + Redis FSM (современный Python-стандарт)
Вариант 3. Event-driven: сайт публикует domain events → worker/bot consumer → Telegram; mobile потом подключается к тем же events/API
Вариант 4. Hybrid (если лучше): например webhook на FastAPI endpoint + thin bot adapters

Для каждого варианта оцени:
- latency
- hosting constraints (Passenger/reg.ru, отдельный процесс бота)
- стоимость поддержки
- готовность к mobile push/notifications
- безопасность
- миграционный риск

**Обязательные требования к целевой архитектуре:**
1. Единый Notification/Event service на backend (не дублировать send в боте и сайте).
2. Idempotent delivery (message keys / outbox / dedupe).
3. Контракт API versioned (`/api/v1/...`) для bot и future mobile.
4. Чёткий identity model пользователя (один canonical `telegram_user_id`).
5. Deep links с TTL, one-time tokens, revoke.
6. Rate-limit и retry policy для Telegram API.
7. Structured logging + correlation_id между web request и bot message.
8. Feature flags для постепенного rollout.
9. Возможность webhook (prod) и polling (dev/fallback).
10. Подготовка к mobile: auth session, device tokens, notification preferences, same booking events.

#### Часть D. Refactor / rewrite plan

Составь поэтапный план (не «переписать всё сразу»):

Phase 0. Freeze + baseline metrics (что логировать сейчас)
Phase 1. Security & reliability hotfixes (без смены фреймворка)
Phase 2. Unified notification layer + outbox/idempotency
Phase 3. Bot rewrite на выбранном стеке
Phase 4. API cleanup for mobile
Phase 5. Docs/ops cleanup + delete legacy Django leftovers
Phase 6. Hardening (load, retries, alerting)

Для каждой фазы:
- цель
- конкретные файлы
- acceptance criteria
- rollback plan
- test plan
- deploy notes

#### Часть E. Mobile readiness blueprint

Отдельно опиши, как Telegram-слой должен эволюционировать в сторону mobile app:
- shared domain events: BookingCreated, BookingConfirmed, BookingRescheduled, ReminderDue, SpecialistConnected
- notification preferences per channel (telegram / push / email)
- auth linking: telegram account ↔ app user
- что НЕ должно жить в боте (бизнес-логика записи, слоты, цены, права доступа)

#### Часть F. Decision record

В конце дай ADR-стиль:
1. Рекомендуемый стек бота (и почему)
2. Рекомендуемый transport (webhook vs polling)
3. Рекомендуемый pattern доставки уведомлений (sync send vs outbox/worker)
4. Что запрещено делать дальше (anti-patterns)
5. Top-10 задач в порядке выполнения

### Формат ответа

Отвечай на русском.
Структура строго:

1. Executive summary (10–15 строк)
2. Current system map
3. Critical findings (таблица)
4. Scorecard
5. Target architecture (схема текстом/mermaid)
6. Options comparison table
7. Recommended decision
8. Phased roadmap
9. Mobile blueprint
10. Immediate next actions (что делать в ближайшие 48 часов)
11. Open questions (только если без ответа нельзя проектировать дальше)

### Правила качества

- Не выдумывай файлы и endpoints: сначала прочитай репозиторий.
- Любой вывод подтвержди путём к файлу и краткой цитатой/символом.
- Не предлагай «магические» enterprise-решения без учёта текущего хостинга.
- Если решение конфликтует с shared hosting — явно скажи и предложи pragmatic path.
- Не начинай код-рефакторинг в этом ответе.
- Если находишь устаревшие docs — перечисли, что удалить/переписать.
- Считай, что можно полностью заменить бота, но миграция должна быть безопасной для production пользователей.

### Критерий успеха первого прохода

После твоего ответа команда должна понимать:
1. Что именно сейчас сломано/хрупко.
2. Какую архитектуру выбрать.
3. В каком порядке переписывать.
4. Как не потерять текущие флоу клиентов и специалистов.
5. Как сразу заложить фундамент под mobile app.

Начни с чтения кода и только потом пиши отчёт.

## PROMPT END
