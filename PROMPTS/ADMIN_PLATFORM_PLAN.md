# План: Admin Platform - центр управления «Все клиенты здесь»

Статус: формирование плана (код не начинать, пока dual-role Phase 0-3 не стабильны).

Это **не** «ещё одна страница в кабинете специалиста».  
Это внутренний **платформенный** продукт для владельца сервиса: пользователи, записи, платежи, Telegram, ошибки, безопасность.

Референсы UX: Stripe Dashboard, Linear, Vercel, Clerk, Supabase.  
Дизайн: существующая DS сайта (`app/static/css/tokens.css`) - тёмная тема, glass, `#7D5CFF` / `#4AA8FF` / `#0B0D12`.

Исходные продуктовые промпты пользователя сохранены как требования-максимум ниже.  
Реализация - **только по фазам A0→An**. Один монолитный PR на весь список = провал.

Связано:
- Dual-role: `PROMPTS/DUAL_ROLE_MIGRATION_PLAN.md` (Phase 10 Broadcast, Phase 11 copy)
- Операции после прода: `PROMPTS/TELEGRAM_ADMIN_OPS.md`

---

## 1. Принципы (senior constraints)

1. **RBAC с первого дня** - даже если сначала только Super Admin. Не хардкодить «если email == …».
2. **Никогда не показывать/хранить plaintext пароли** - только reset / invalidate sessions / last password change.
3. **Имперсонация только у Super Admin**, с красным баннером и audit log.
4. **Telegram-рассылки не раньше** dual Phase 3 (dedup) + понятных сегментов ролей.
5. **Наблюдаемость > красота** на старте: ошибки, логи, статус бота важнее анимированных графиков.
6. **Тот же CSS tokens**, без Bootstrap-таблиц «из коробки».
7. Всё админское под префиксом `/platform-admin/` (не путать с Django admin и не светить в публичном меню).
8. Доступ: `User.is_staff` / `is_superuser` + будущая таблица `AdminRole` / permissions.
9. Мутации админа → audit event (кто, что, до/после, IP).
10. Массовые действия - через job queue, не синхронный HTTP на 10k строк.

---

## 2. Целевая карта разделов (product max)

Левое меню (иконки SVG, активный пункт - градиент DS):

| Раздел | MVP? | Комментарий |
|--------|------|-------------|
| Dashboard | A2 | KPI карточки; live metrics позже |
| Пользователи | A2 | поиск, карточка, block/reset |
| Специалисты | A2 | обёртка над Consultant + stats |
| Клиенты | A3 | агрегация ClientCard + client_user_id |
| Записи | A3 | список + статусы; calendar UI позже |
| Календари | A3 | read + disable |
| Услуги | A4 | |
| Подписки / Платежи / Промокоды | A5+ | когда billing появится в домене |
| Email | A4 | лог исходящих + retry |
| **Telegram** | **A1** | **первый killer-feature после foundation** |
| Аналитика / Метрики | A4 | |
| Логи / Ошибки | A2 | критично для ops |
| Безопасность | A3 | сессии, failed logins |
| Интеграции / Настройки | A4 | SMTP, OAuth, cron flags |
| Поддержка | A5 | тикеты (если появятся) |

Header: логотип + «Admin» | Ctrl+K поиск | уведомления | профиль админа.

---

## 3. Дизайн-система админки

Использовать токены сайта (не изобретать вторую палитру):

| Token / значение | Назначение |
|------------------|------------|
| `--bg-900` `#0B0D12` | фон |
| `--surface-*` / `#171C2B` | карточки |
| `--accent-primary` `#7D5CFF` | primary |
| `--accent-secondary` / `#4AA8FF` | secondary accent |
| radius 18-22px | карточки |
| glass + soft shadow | «парящие» поверхности |
| motion 200ms | hover lift |

UI-паттерны:
- KPI card: иконка, значение, delta %, sparkline placeholder
- Data list: виртуальный скролл при >500 строк
- Drawer / slide-over для деталей сущности
- Skeleton loading, без резких скачков layout
- Mobile: sidebar collapse; приоритет tablet+

---

## 4. Фазы реализации

### A0 - Foundation (обязательный каркас)

- Роутер `/platform-admin/`, layout `admin_app.html`, CSS `admin-platform.css`
- Gate: `require_platform_admin` (`is_staff` или `is_superuser`)
- Таблица `admin_audit_log` (actor_user_id, action, entity, payload_json, ip, created_at)
- Заглушка Dashboard «скоро»
- Feature flag `PLATFORM_ADMIN_ENABLED=1`
- Тесты: non-staff → 403/redirect; staff → 200

**Без A0 нельзя** открывать Telegram-рассылки в UI.

Rollback: flag off + скрыть роут.

---

### A1 - Telegram Center + Broadcast (приоритет продукта)

Зависимости: dual Phase 3+4; желательно Phase 7 mode labels.

Функции:
1. Статистика: подключено Integration / client telegram_id / ошибки доставки / last send.
2. Список последних исходящих (из `telegram_outbox` или log table).
3. **Композер рассылки:**
   - аудитория: all_unique | clients_only | specialists_only | dual | test_self
   - текст + превью (как в Telegram)
   - schedule (optional v1.1)
   - dry-run: count recipients
4. Очередь `telegram_broadcast_jobs` + worker/cron chunk send (~25-30/sec)
5. Dedup chat_id внутри job
6. Opt-in: `User.notify_broadcast` или Integration/Client preference (решение зафиксировать до кода)
7. Кнопка «отправить одному» по user id / telegram id

Модели (эскиз):
```
TelegramBroadcastJob(id, created_by, audience, text, status, created_at, started_at, finished_at)
TelegramBroadcastRecipient(job_id, chat_id, user_id?, status, error, sent_at)
TelegramOutbox / DeliveryLog для transactional тоже (позже унифицировать)
```

Критерий приёмки:
- Админ отправил test_self → получил в свой TG
- specialists_only не дублирует dual дважды
- 429 обрабатывается backoff
- Всё в audit log

Связь: Dual Phase 10.  
Инструкция для людей: `TELEGRAM_ADMIN_OPS.md`.

---

### A2 - Users + Errors + базовый Dashboard

Пользователи:
- поиск email/phone/telegram/id/name
- карточка: поля User + Consultant summary + social links
- действия: block/unblock, force password reset email, end sessions (когда session store появится), edit contacts
- **нет** показа password hash как «пароля»
- «Войти как» (impersonate) - только superuser, red banner, audit

Ошибки:
- приём 5xx/traceback в structured log store (или чтение файлов логов на первом этапе)
- статусы: new / in_progress / fixed / ignore

Dashboard KPI (read-only SQL): users total, new today, consultants, bookings today.  
Графики - простые SVG/Chart.js без перфекционизма.

---

### A3 - Clients / Specialists / Bookings / Calendars / Security

- Специалисты: stats (clients, bookings, cancel rate) - то, что уже можно посчитать из БД
- Клиенты платформы: после dual `client_user_id` + ClientCard aggregate
- Записи: фильтры, смена статуса с notify (через существующие сервисы)
- Календари: список, ссылка на public slug
- Безопасность: failed logins (если логируем), active admin sessions list

Calendar drag&drop Google-level - **не A3**, отдельный подэпик A3b.

---

### A4 - Email / Analytics / Settings / Integrations

- Email delivery log + resend
- Метрики DAU/WAU (на событиях; нужны event hooks)
- Settings UI для env-backed flags (осторожно: секреты только mask/edit)
- OAuth/SMTP/Telegram bot token status (connected / missing), без вывода секретов целиком

---

### A5+ - Billing, Support, Backups, Enterprise

Подписки, платежи, промокоды, MRR/ARR, support inbox, manual backup trigger, saved views, WebSocket live - когда домен биллинга и поддержки реально существует в коде.

До тех пор в меню можно показать disabled «скоро» или скрыть.

---

## 5. Роли (RBAC target)

| Роль | Суть |
|------|------|
| Super Admin | всё + impersonate + settings secrets |
| Administrator | users/bookings/telegram без impersonate |
| Support | read users, reset password, reply support |
| Finance | payments (когда будут) |
| Moderator | block content / users limited |
| Developer | errors, logs, system status |
| Viewer | read-only dashboard |

v1: только Super Admin + Administrator. Остальные роли - schema ready, UI later.

---

## 6. Безопасность (обязательный чеклист)

- [ ] CSRF на всех POST админки
- [ ] Rate limit на login admin и broadcast send
- [ ] Audit на impersonate start/stop
- [ ] Нет plaintext паролей; reset через token email
- [ ] Секреты в UI замаскированы
- [ ] Broadcast dry-run обязателен перед first send на prod
- [ ] Platform admin не доступен из публичной навигации
- [ ] 2FA для admin (желательно до открытия рассылок на всю базу)

---

## 7. Производительность

- Пагинация / cursor pagination везде
- Virtual list для больших таблиц
- Broadcast только через очередь
- Lazy charts
- Никаких N+1 на карточке пользователя (joinedload)

Live WebSocket/SSE - после A2, не блокер MVP.

---

## 8. Порядок относительно dual-role

```
Dual 0-1 schema
 → Dual 3 dedup
 → Dual 4 link decouple
 → Admin A0 foundation          (можно чуть раньше, без рассылок)
 → Admin A1 Telegram + Dual 10  (рассылки)
 → Dual 11 message quality      (шаблоны + превью в A1)
 → Admin A2 users/errors
 → …
```

Нельзя: включить массовую рассылку «всем» до dedup и уникальности chat сегментов.

---

## 9. Оценка

| Phase | Сложность | Риск |
|-------|-----------|------|
| A0 | средняя | низкий |
| A1 Telegram/Broadcast | высокая | высокий (бан бота / спам) |
| A2 Users/Errors | высокая | средний |
| A3 domain ops | высокая | средний |
| A4+ | очень высокая | зависит от billing |

---

## 10. Требования-максимум (из промптов) - backlog map

Ниже зафиксировано, чтобы ничего не потерять. Пометка [A#] = целевая фаза.

**Shell:** sidebar, header, Ctrl+K, notifications drawer [A0-A2]  
**Dashboard KPI + charts + server health** [A2 / A4]  
**Users full CRM + history + IP/device** [A2; device/IP нужен middleware сбора]  
**Impersonation + red bar** [A2]  
**Password tools без раскрытия** [A2]  
**Specialists/Clients stats** [A3]  
**Bookings Google Calendar UX** [A3b]  
**Payments/Subscriptions/Promo** [A5]  
**Telegram center + mass send** [A1]  
**Email center** [A4]  
**Errors with traceback triage** [A2]  
**Audit logs** [A0 schema, A2 UI]  
**Security sessions/JWT** [A3; JWT если появится]  
**Settings all integrations** [A4]  
**RBAC multi-role** [A0 stub, A3 full]  
**Bulk ops + export CSV/XLSX/PDF** [A2-A3]  
**Support center** [A5]  
**Backup/restore UI** [A5]  
**SSE/WebSocket live** [A4]

---

## 11. Definition of Done для «можно пользоваться в проде»

Минимум для твоего сценария «пишу пост → уходит по ролям»:

1. Dual Phase 3+4 на проде  
2. Admin A0+A1 на проде  
3. Opt-in политика согласована  
4. Пройден dry-run + test_self  
5. Заполнен и проверен `TELEGRAM_ADMIN_OPS.md`  
6. 2FA или хотя бы сильный единственный superuser + audit  

Полный Stripe-dashboard - **не** DoD для первой админки.
