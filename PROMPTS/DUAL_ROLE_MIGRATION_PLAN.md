# План перехода: один User = клиент + специалист

Цель: один логин/пароль/Telegram на человека. Роли - способности + режим интерфейса, не два аккаунта.
Охват: сайт, Telegram-бот, Mini App (`/tg/`).

Статус документа: в работе. Phase 0-2 в main; Phase 3 (dedup + role labels) - в этом PR, flag NOTIFY_DEDUP по умолчанию off.  
Менять код только по фазам ниже, с feature flag и откатом.

---

## 0. Текущая реальность (факт из кода)

```
User ──Consultant── Integration.telegram_chat_id  → уведомления СПЕЦИАЛИСТУ
  │
  └── SocialAccount(telegram)  (логин на сайт; сейчас ещё пишет Integration)

Booking.telegram_id  → уведомления КЛИЕНТУ / "мои записи" в боте
Booking.link_token   → привязка TG после записи
ClientCard           → CRM внутри одного Consultant (phone|email|telegram)
Session user_id      → кабинет
Session pc_*         → гостевая запись (не User)
```

Проблемы:
1. Нет `Booking.client_user_id` - клиент не привязан к User.
2. Регистрация всегда создаёт Consultant.
3. SocialAccount connect молча пишет Integration.telegram_chat_id.
4. `Integration.telegram_chat_id` не unique; specialist lookup через `.first()`.
5. Бот при dual шлёт оба welcome и перетирает reply-клавиатуру.
6. Напоминания клиенту и специалисту независимы → при одном chat_id будет дубль.
7. Mini App: нет режима, cookie в WebView хрупкие, initData не валидируется.
8. `get_consultant` редиректит User без Consultant на `/`.

---

## 1. Целевая модель

### Identity
- Один `User` = один человек.
- Один Telegram (SocialAccount) → один User.
- Один логин/пароль → тот же User.

### Capabilities (не отдельные аккаунты)
- `has_consultant` = существует Consultant с `user_id`.
- `can_act_as_client` = всегда (после появления User или хотя бы telegram_id на booking).
- Специалист без календаря всё равно может записываться как клиент.

### Context (режим UI)
- Сайт: `session["active_mode"]` = `client` | `specialist`.
- Бот: `telegram_ui_mode` (таблица/кэш по chat_id) = `client` | `specialist`.
- Mini App: query `?mode=` или последний режим User.
- Переключатель - смена UI, не смена аккаунта.

### Данные
- `Booking.client_user_id` (nullable FK → auth_user) - каноническая связь "запись клиента".
- `Booking.telegram_id` остаётся для доставки сообщений и legacy.
- `ClientCard` остаётся CRM специалиста; при наличии client_user_id предпочитать его при матчинге.
- `Integration` только для уведомлений специалиста (явное подключение), не побочный эффект логина.

---

## 2. Карта рисков и как закрываем

| Риск | Почему больно | Митигация |
|------|---------------|-----------|
| Двойные уведомления в один чат | client telegram_id == Integration.chat_id | Dedup в notify: один chat → один шаблон или combined; не два независимых send |
| Self-booking | человек пишет сам к себе | Warn/block если `calendar.consultant.user_id == client_user_id` |
| Два Consultant на один chat_id | нет unique, `.first()` врёт | Инвентаризация дублей → unique + отказ перезаписывать чужой chat |
| Orphan User (без Consultant) | кабинет падает на get_consultant | Soft gate + режим client по умолчанию |
| Register = всегда специалист | нельзя быть "только клиентом" | Разделить signup: client / become specialist |
| Social connect пишет Integration | логин клиента включает specialist-notify | Убрать side-effect; Integration только через connect_spec / Integrations UI |
| ClientCard merge по телефону | специалист как клиент сливается с чужой карточкой | Приоритет client_user_id; ужесточить match |
| WebView cookies | Mini App не держит сессию | Phase: SameSite=None+Secure или initData auth |
| Backfill telegram_id → User | часть клиентов без аккаунта | Backfill только при SocialAccount; остальных не выдумывать |
| SocialAccount без unique (provider,uid) | дубли uid | Dedupe + unique index |
| Reschedule без TG | уже дыра | Отдельный тикет после dual (не блокирует Phase A-C) |
| Отмена SocialAccount не чистит Integration | рассинхрон | Явные правила disconnect (документировать + починить) |

---

## 3. Инварианты (нельзя нарушать)

1. Один `telegram_id` / SocialAccount.uid → максимум один User.
2. Один `Integration.telegram_chat_id` → максимум один Consultant (после Phase 1 cleanup).
3. Уведомление всегда маркировано ролью: "Ваша запись" vs "К вам запись".
4. Reply-клавиатура бота соответствует `telegram_ui_mode`, не "последнему победившему".
5. Создание Consultant - явное действие, не скрытый side-effect логина клиента.
6. Существующие специалисты не теряют кабинет и Integration после миграции.
7. Гостевая запись (`pc_*`) продолжает работать без регистрации.

---

## 4. Фазы перехода

Каждая фаза: код + тесты + чеклист на staging → prod. Rollback описан. Feature flag: `DUAL_ROLE_V1=1`.

### Phase 0 - Инвентаризация (только чтение)

Скрипты/SQL (без изменения поведения):
- Users без Consultant.
- Integrations с одинаковым `telegram_chat_id`.
- Bookings где `telegram_id` == чей-то Integration.telegram_chat_id (уже dual).
- Bookings с telegram_id и matching SocialAccount.
- Дубли SocialAccount (provider, uid).

Критерий готовности: отчёт сохранён, дубли chat_id разобраны вручную (или список на фикс).

Rollback: N/A.

---

### Phase 1 - Схема additive only

Изменения БД (nullable, без ломания старого кода):
1. `bookings.client_user_id` FK → `auth_user.id` NULL.
2. `auth_user` или отдельная таблица prefs: `telegram_ui_mode`, `web_active_mode` (опционально; можно начать с session-only).
3. После dedupe: UNIQUE(`socialaccount_socialaccount.provider`, `uid`).
4. После cleanup дублей: UNIQUE(`integrations.telegram_chat_id`) WHERE NOT NULL (или app-level enforce).

Код: писать/читать новые поля, но старые пути работают как раньше.

Тесты: миграция вверх/вниз; модель Booking.client_user_id.

Rollback: drop nullable column / indexes.

---

### Phase 2 - Backfill identity

Идемпотентный скрипт:
```
для Booking с telegram_id и client_user_id IS NULL:
  найти SocialAccount(provider=telegram, uid=telegram_id)
  если найден → client_user_id = account.user_id
```

Не создавать User на каждый telegram_id без аккаунта (иначе спам-аккаунты).

Критерий: % привязанных bookings зафиксирован; повторный прогон не меняет данные.

Rollback: `UPDATE bookings SET client_user_id = NULL`.

---

### Phase 3 - Уведомления: каналы + dedup (критично до UX)

Файлы: `app/services/telegram.py`, call sites в `pages.py`, `api.py`, `send_reminders`.

Правила:
1. `notify_client(booking)` - шаблон CLIENT, chat = booking.telegram_id (или User.social).
2. `notify_specialist(booking)` - шаблон SPECIALIST, chat = Integration.
3. Если оба chat_id равны (нормализовать str/int):
   - reminders: слать **одно** combined или только specialist + короткая пометка "и вы клиент";
   - status change: аналогично;
   - new booking: специалисту сразу; клиенту после confirm - если тот же chat, не дублировать смыслом.
4. Префиксы в copy обязательны.

Feature flag `NOTIFY_DEDUP=1`.

Тесты: unit на "same chat → один send"; разные chat → два send.

Rollback: flag off.

---

### Phase 4 - Развязка Telegram link механизмов

Файлы: `telegram_auth.py`, integrations pages, api connect.

1. SocialAccount login/connect **не** пишет `Integration.telegram_chat_id`.
2. Integration только: `connect_spec_*`, форма в Integrations, явная кнопка.
3. Disconnect SocialAccount ≠ disconnect Integration (и наоборот) - явные отдельные действия + UI текст.
4. При попытке занять chat_id, уже занятый другим Consultant → ошибка.

Критерий: специалист может логиниться как клиент TG, не ломая/не включая чужие notify.

Rollback: временно вернуть side-effect только для signup specialist.

---

### Phase 5 - Auth / регистрация

1. Signup "клиент": User (+ SocialAccount), **без** Consultant.
2. Signup "специалист" / "Стать специалистом": создаёт Consultant + Integration stub.
3. `get_consultant`: не слепой 302 на `/`; для client mode - свои страницы; для specialist routes без Consultant - CTA "создать профиль специалиста".
4. Dashboard: если нет Consultant → client home / become specialist.
5. Логин один: email+password или Telegram → тот же User.

Тесты: client signup без Consultant; become specialist; orphan User UX.

Rollback: flag `FORCE_CONSULTANT_ON_SIGNUP=1`.

---

### Phase 6 - Сайт: режим и кабинет клиента

1. Session `active_mode`; переключатель в header (виден если has_consultant).
2. Client mode:
   - "Мои записи" (по client_user_id, fallback telegram_id через SocialAccount);
   - запись к специалистам с автозаполнением контактов из User;
   - при create_public_booking писать client_user_id если залогинен.
3. Specialist mode: текущий кабинет без регрессий.
4. Middleware: specialist URLs требуют mode=specialist + Consultant.
5. Публичный `/s/{slug}/` для гостя без изменений.

Критерий: специалист может записаться к другому специалисту под своим логином и видеть запись в "Мои записи".

Rollback: спрятать switcher, всегда specialist UI для has_consultant.

---

### Phase 7 - Telegram-бот

Файлы: `bot/bot.py`, `bot/copy.py`, API endpoints.

1. `/start` без обеих клавиатур сразу.
2. Capabilities:
   - client_if: есть bookings по telegram_id ИЛИ SocialAccount;
   - specialist_if: Integration ИЛИ User.has_consultant + linked TG.
3. Если обе → inline/reply: выбрать режим; сохранить mode.
4. Клавиатура строго по mode; кнопка "Сменить роль".
5. Команды `/appointments` и `/spec_next` проверяют mode или capabilities.
6. Все bot-сообщения о записях используют те же CLIENT/SPECIALIST шаблоны что сайт.
7. Deep links:
   - `link_*` - клиентский bind;
   - `connect_spec_*` - specialist Integration;
   - `login_*` - auth без смены роли насильно.

Критерий: dual-пользователь не теряет клиентские кнопки после /start.

Rollback: старый /start dual overlay.

---

### Phase 8 - Mini App

1. `/tg/` - определение User (cookie или позже initData) + mode switcher.
2. Кнопки: Записаться / Мои записи / Кабинет (если specialist).
3. WebApp URL: `/tg/?mode=client|specialist`.
4. Menu Button остаётся `/tg/`.
5. Session в WebView:
   - короткосрочно: проверить SameSite=None; Secure; документировать;
   - правильно: validate Telegram `initData` → создать/найти User → выдать session.
6. Password middleware: не ломать WebApp entry (exempt `/tg/` already check; client flows).

Критерий: Open из списка чатов (Main Mini App) открывает hub с понятным режимом.

Rollback: статичный `/tg/` без switcher.

---

### Phase 9 - Бизнес-правила и полировка

1. Self-booking policy (block или confirm dialog).
2. ClientCard: при client_user_id не merge слепо по phone.
3. Reschedule → Telegram notify (закрыть дыру).
4. Audit log для смены Integration.chat_id.
5. Метрики: dual users count, dedup hits, orphan users.

---

### Phase 10 - Broadcast (рассылки из админки)

**Не в dual v1 UX**, но закладывается сразу после стабильных chat_id и dedup.

Зависимости: Phase 3 (dedup) + Phase 4 (развязка TG) + каркас Admin A0/A1  
(см. `PROMPTS/ADMIN_PLATFORM_PLAN.md`).

Суть:
1. Админ пишет текст → очередь → бот шлёт по сегменту роли.
2. Сегменты: все / только клиенты / только специалисты / dual / тест-себе.
3. Один chat_id = одно сообщение (даже если dual).
4. Rate limit Telegram, retry 429, лог доставки.
5. Opt-in флаг «получать новости» (по умолчанию off или on - решить до релиза).

Детали UI/API: раздел Telegram в админ-платформе.  
Инструкция для продакшена после заливки: `PROMPTS/TELEGRAM_ADMIN_OPS.md` (заполнить чеклистом при релизе).

---

### Phase 11 - Качество информационных сообщений Telegram

Отдельно от dual-роутинга: все transactional + broadcast тексты привести к единому стандарту.

1. Единый стиль copy (заголовок роли, emoji-бюджет, короткие абзацы, без длинных тире).
2. HTML parse_mode + экранирование; кнопки WebApp где уместно.
3. Разные шаблоны: new booking / confirm / cancel / reminder / broadcast / system.
4. Превью в админке перед отправкой.
5. A/B не в v1; сначала один канонический набор в `bot/copy.py` + `app/services/telegram.py`.

Связано с Admin раздел Telegram (превью) и с Phase 3 (маркировка роли).

---

### Phase 12+ - Платформенная админка (epic)

Полный центр управления SaaS (Stripe/Linear-уровень) - **отдельный эпик**, не блокер dual-role.

Дорожная карта, дизайн-токены, RBAC, имперсонация, Telegram-центр:  
→ `PROMPTS/ADMIN_PLATFORM_PLAN.md`

Минимум для рассылок (можно раньше полного Dashboard):
- Admin A0 foundation (доступ `is_staff` / `is_superuser`)
- Admin A1 Telegram Center + Broadcast UI

---

## 5. Порядок зависимостей (нельзя переставлять)

```
0 inventory
 → 1 schema
 → 2 backfill
 → 3 notify dedup          ← обязательно до агрессивного dual UX
 → 4 decouple TG links
 → 5 register split
 → 6 site mode + my bookings
 → 7 bot mode
 → 8 mini app + initData
 → 9 policies
 → 10 broadcast (после Admin A0/A1 + dedup)
 → 11 message quality (можно частично параллельно с 3/7)
 → 12+ admin platform epic (см. ADMIN_PLATFORM_PLAN.md)
```

Нарушение порядка = дубли сообщений и сломанные кабинеты в проде.  
Рассылки до Phase 3 = спам dual-пользователям.

---

## 6. Чеклист приёмки (E2E)

### A. Только специалист (регрессия)
- [ ] Логин email, кабинет, календари, записи
- [ ] Integration TG, новая запись → одно specialist-уведомление
- [ ] Reminder специалисту
- [ ] Bot /start → specialist (или выбор, если когда-то был клиентом)

### B. Только клиент
- [ ] Signup без Consultant
- [ ] Запись /s/..., confirm TG
- [ ] Bot: мои записи / история
- [ ] Нет доступа к /calendars без become specialist

### C. Dual (главный сценарий)
- [ ] Один User, один password, один TG
- [ ] Есть Consultant + хотя бы одна запись как клиент к другому специалисту
- [ ] Сайт: переключатель режимов работает
- [ ] Бот: выбор режима, клавиатура не перетирается молча
- [ ] Напоминание: нет двух почти одинаковых сообщений подряд без маркировки
- [ ] Status confirm/cancel: понятные шаблоны, без флуда
- [ ] Mini App Open → hub, можно уйти в client и specialist потоки

### D. Edge
- [ ] Self-booking: ожидаемое поведение (block/warn)
- [ ] Попытка занять чужой Integration.chat_id → ошибка
- [ ] Disconnect login TG не убивает Integration без подтверждения
- [ ] Гостевая запись без аккаунта всё ещё работает

---

## 7. Ключевые файлы

| Область | Файлы |
|---------|--------|
| Модели | `app/models/core.py`, `app/models/auth.py` |
| Notify | `app/services/telegram.py`, `app/commands/send_reminders.py` |
| Auth TG | `app/services/telegram_auth.py`, `app/routers/oauth.py` |
| Booking | `app/services/bookings.py`, `app/routers/public_specialist.py` |
| Gates | `app/deps.py`, `app/auth/session.py`, `app/main.py` |
| Pages | `app/routers/pages.py` |
| API bot | `app/routers/api.py` |
| Bot | `bot/bot.py`, `bot/copy.py` |
| Mini App | `app/templates/public/tg_mini_app.html`, `app/static/js/telegram-webapp.js` |

---

## 8. Оценка сложности (ориентир)

| Phase | Риск | Сложность |
|-------|------|-----------|
| 0-2 | низкий | низкая |
| 3 notify dedup | высокий | средняя |
| 4 link decouple | высокий | средняя |
| 5 register | средний | средняя |
| 6 site mode | средний | высокая |
| 7 bot | средний | средняя |
| 8 mini app auth | высокий | высокая |
| 9 polish | низкий | низкая |
| 10 broadcast | средний | средняя (+ очередь) |
| 11 message quality | низкий | средняя |
| 12+ admin epic | высокий | очень высокая (много PR) |

Самые опасные места: Phase 3 и 4. Без них dual UX в боте/сайте создаст жалобы на спам и "пропали уведомления".

---

## 9. Что сознательно НЕ входит в dual v1

- Два бота / два токена на роли.
- Обязательная регистрация всех гостей.
- Полный aiogram rewrite (можно параллельно, не блокер dual).
- Mobile native app.
- Удаление legacy таблицы `clients` (можно позже).
- Полная админка Stripe-уровня целиком одним PR (только по `ADMIN_PLATFORM_PLAN.md`).
- Рассылки без opt-in политики и без dedup.

---

## 10. Связанные документы

| Документ | Зачем |
|----------|--------|
| `PROMPTS/ADMIN_PLATFORM_PLAN.md` | Эпик админ-центра платформы + Telegram-раздел |
| `PROMPTS/TELEGRAM_ADMIN_OPS.md` | Инструкция админу после деплоя (рассылки, сегменты) |
| `docs/TELEGRAM_MINI_APP_SETUP.md` | Mini App / BotFather |

---

## 11. Решение для старта работ

Рекомендуемый первый PR после утверждения плана:
**Phase 0 + Phase 1 + каркас notify dedup (flag off)**  
без смены UX регистрации и без переключателя на сайте.

После стабилизации на проде → Phase 3 flag on → 4 → 5 → 6/7/8 → 10/11 с Admin A0/A1.
