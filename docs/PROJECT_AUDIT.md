# Project Audit — Все клиенты здесь

Дата: 2026-08-01  
Ветка аудита: `track/android` @ `6e09353`  
Prod deploy: push в `main` → GitHub Actions → VPS (Passenger + bot systemd)  
Стек: FastAPI + Jinja2 + MySQL + Telegram bot + Capacitor Android  

**Статус:** P0–P4 выполнены 2026-08-01. P5: pytest; merge в `main` - только по отдельному ОК.  

---

## 1. Структура проекта

| Зона | Назначение | Оценка |
|------|------------|--------|
| `app/` | FastAPI: routers, models, services (~61), templates, static | Ядро, в порядке |
| `bot/` | Telegram bot (polling/API) | Живой |
| `tests/` | ~32 pytest-модуля | Хорошее покрытие доменов |
| `mobile/` | Capacitor Android shell | Нужен, но захламлён debug-артефактами |
| `nginx/`, `Dockerfile`, `docker-compose.yml` | Локальный/VPS docker path | Актуален |
| `passenger_wsgi.py` | Деплой reg.ru | **Не удалять** (CI проверяет импорт) |
| `scripts/` | migrate/bot/reminders + Django-era leftovers | Частично мёртвый |
| `PROMPTS/` | 14 operational/design prompts | Много завершённых планов |
| `docs/` | Design system, TG setup, audit | Держать |
| `alembic/` | Пусто | Мёртвая оболочка (схема через `db_schema.py`) |
| `certbot/`, `media/` | Пусто/почти пусто | Ок как mount points |
| `venv/`, `.pytest_cache/`, `.idea/` | Локальное | gitignored / не в remote |

### Ветки (риск)

- Активная: `track/android` (редизайн A–C).
- Prod: `main` (локально **behind** remote; redesign туда не влит).
- Есть `track/site`, `track/telegram`, `develop`, `re_fast_api_main` - риск рассинхрона.

---

## 2. Зависимости

### Python (`requirements.txt`)

Закреплены: FastAPI, uvicorn, SQLAlchemy, Alembic, PyMySQL, pytest, gunicorn, a2wsgi.  
Слабо закреплены: `Pillow>=…`, `google-auth*`, `google-api-python-client>=…`.

| Пакет | Использование | Замечание |
|-------|---------------|-----------|
| `requests` | bot, telegram, broadcast | Живой |
| `httpx` | yandex/vk auth, vk_messages | Живой; дубль HTTP-клиентов |
| Google API trio | `app/services/google_calendar.py` | Код есть; UI «Скоро» - не мёртвый пакет |
| `alembic` | в deps | Каталог миграций пуст; патчи в `db_schema.py` |
| `passlib[bcrypt]` | пароли | Следить совместимость bcrypt 4.x |

Нет корневого `package.json` / `pyproject.toml`.  
`mobile/package.json`: Capacitor 7 - ок для RuStore shell.

### Рекомендации по deps (не делать без ОК)

1. Запинить Pillow и google-* на exact/compatible ranges.  
2. Позже: bot → httpx **или** oauth → requests (один клиент).  
3. Не выкидывать Google libs, пока сервис не удалён осознанно.  
4. Не трогать gunicorn/a2wsgi - нужны Passenger.

---

## 3. Лишние / подозрительные файлы

### A. Untracked мусор (безопасно удалить локально + не коммитить)

| Файл | Почему |
|------|--------|
| `index.php`, `.section.php`, `template.php` | PHP/Bitrix-подобные leftovers, не FastAPI |
| `packaging-001.png` | Случайный asset |
| `mobile/debug-screen*.png/jpg` | Скриншоты отладки (~0.7 MB) |
| `mobile/tools/` | Локальные tools (эмулятор и т.п.) |
| `docs/agents-orchestration-diagram.png` | ~1.2 MB; опционально в git или сжать |

### B. Tracked кандидаты на удаление/архив (нужно ОК)

| Файл | Рекомендация |
|------|--------------|
| `LOGS_AND_COMMANDS.md` (~41 KB) | В `docs/archive/` или удалить; не продукт |
| `TELEGRAM_ЧТО_СДЕЛАТЬ.md` | Ops-чеклист; архив после сверки с `docs/TELEGRAM_MINI_APP_SETUP.md` |
| `.gitlab-ci.yml` | Устарело, если деплой только GitHub Actions |
| `scripts/fix_bookings_migration_names*.py` | Django-era (`manage.py shell`) |
| `scripts/convert_templates.py`, `fix_jinja_templates.py`, `russify_ui.py`, `test_templates.py` | Разовые миграции UI; проверить 0 ссылок → archive |
| Пустой `alembic/` | Удалить **или** завести реальные миграции (отдельное решение) |

### C. Оставить

- `README.md`, `AGENTS.md`, `env.example`, `passenger_wsgi.py`  
- `docs/DESIGN_AUDIT.md`, `DESIGN_SYSTEM.md`, `TELEGRAM_MINI_APP_SETUP.md`  
- `PROMPTS/COMPLIANCE_RKN.md`, `SECURITY_HARDENING.md`, `AGENT_ORCHESTRATION.md`  
- `mobile/README.md`, `SETUP_ANDROID.md`  
- `.cursor/rules/*.mdc` (сейчас untracked - **стоит закоммитить**)

### D. Локальные БД

`data.db`, `db.sqlite3` на диске есть, в `.gitignore` - ок. Не коммитить.

---

## 4. Код: долг и риски

### Уже хорошо

- `/health` + schema health  
- In-memory rate limit + hardening middleware  
- TrustedHost  
- CSRF на формах  
- `response_cache` / TTL cache (есть тесты)  
- Cabinet shell + bottom nav + TG denser (фазы A–C на `track/android`)  
- 26+ smoke / много domain tests  

### Проблемы / anti-patterns

1. **Два HTTP-стека** (`requests` + `httpx`) - лишняя поверхность.  
2. **Схема БД без Alembic-истории** - `db_schema.py` патчи; откаты сложнее.  
3. **In-memory rate limit / cache** - не шарится между uvicorn workers (compose: `--workers 2`).  
4. **Нет Sentry/метрики** в коде (только логи/health).  
5. **Django-хвосты** в scripts и комментариях `.gitignore`.  
6. **Hero glow / emoji leftovers** частично вычищены, не везде.  
7. **Ветки** - redesign не на `main` → prod без фаз A–C.  

### Безопасность (кратко)

- `.env` ignored; `env.example` без секретов - ок.  
- Не найдено явных токенов в tracked tree (выборочно).  
- Stack traces: проверить DEBUG=False на prod (deploy secrets).  
- CORS: сайт Jinja-first; API для bot - проверить allowlist отдельно при рефакторе.

---

## 5. Документация (MD triage)

| Категория | Файлы | Действие |
|-----------|-------|----------|
| Продукт | README | Обновить после очистки |
| Оркестрация агентов | AGENTS.md, PROMPTS/AGENT_ORCHESTRATION | Оставить |
| Дизайн | docs/DESIGN_* , GPT_LOGO, CALCOM_THEME, MOBILE_UI | Оставить актуальные |
| Compliance/Security | COMPLIANCE_RKN, SECURITY_HARDENING | Оставить |
| Завершённые планы | DUAL_ROLE_*, ADMIN_PLATFORM_*, RESPONSIVE_DS_*, BOT_FULL_AUDIT, PERF_SPEED, TELEGRAM_ADMIN_OPS | `docs/archive/prompts/` |
| Ops dump | LOGS_AND_COMMANDS, TELEGRAM_ЧТО_СДЕЛАТЬ | Архив или удалить |

**Не удалять пачкой все PROMPTS** без вашего списка - часть ещё рабочая.

---

## 6. Конфиги

| Файл | Статус |
|------|--------|
| `.gitignore` | Ок для .env/venv/db; добавить `*.php` в корне?, `mobile/debug-screen*`, `packaging-*.png` |
| `docker-compose.yml` | Рабочий; workers=2 без Redis - учесть rate limit |
| GitHub Actions | Deploy на `main` - источник правды |
| `.gitlab-ci.yml` | Кандидат на удаление |
| `mobile/.gitignore` | node_modules/gradle ignored |

---

## 7. UI: TMA / Mobile / Responsive (разрыв)

Уже на `track/android`:

- Sidebar + workspace, bottom nav, empty/skeleton, sheet motion, TG denser CSS, theme light/dark.

Пробелы относительно brief / TelegramUI:

| Платформа | Есть | Нет / слабо |
|-----------|------|-------------|
| TMA | `tg-webapp.js/css`, safe-area, denser cabinet | Полный TelegramUI kit; аудит MainButton/BackButton/Haptic на всех экранах |
| Capacitor Android | Shell + deep links (ранее) | Offline SW; RuStore release pipeline polish |
| Mobile web | Bottom nav, day-first calendar, touch 44px | Полный a11y pass; lazy images везде |
| Desktop | Cabinet Linear-like | Не ломать при mobile-правках |

Референсы (методология, не копипаст React):

- [TelegramUI](https://github.com/telegram-mini-apps-dev/TelegramUI)  
- [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)  
- [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)  

Стек Jinja - паттерны CSS/JS, не перенос Next.js.

---

## 8. План действий (после ОК)

### P0 - Safe cleanup (30–60 мин)

1. Удалить untracked PHP/png/debug screens.  
2. Дописать `.gitignore`.  
3. Закоммитить `.cursor/rules` + `mcp.json.example`.  
4. Не трогать runtime.

### P1 - Docs hygiene

1. `docs/archive/` для старых PROMPTS + LOGS.  
2. Обновить README (запуск, тесты, ветки, mobile).  

### P2 - Dead code scripts

1. Удалить/архивировать Django-era scripts после `rg` на 0 usages.  
2. Решение по пустому `alembic/` и `.gitlab-ci.yml`.  

### P3 - Runtime harden (осторожно)

1. Pin deps.  
2. Документировать multi-worker + in-memory limits.  
3. Опционально: Redis позже (не блокер).  

### P4 - TMA / mobile UI gap-fill

1. Аудит `telegram-webapp.js` vs BackButton/MainButton.  
2. Выровнять list cells под TelegramUI density.  
3. PWA manifest/offline - точечно.  

### P5 - QA

1. `pytest` полный.  
2. Browser: 375 / 768 / 1440 + TG WebView.  
3. Merge `track/android` → `main` только после вашего approve (prod).  

---

## 9. Out of scope сейчас (явно)

- Force-push / rewrite history  
- Полный SPA router  
- Переписывание на React/TelegramUI npm  
- Удаление Google Calendar кода без продуктового решения  
- Массовое обновление major FastAPI без регрессионных тестов  

---

## 10. DoD аудита

- [x] Структура описана  
- [x] Список мусора и MD triage  
- [x] Deps и риски  
- [x] План P0–P5  
- [ ] Очистка - ждёт ОК  
- [ ] Merge в main - ждёт ОК  
