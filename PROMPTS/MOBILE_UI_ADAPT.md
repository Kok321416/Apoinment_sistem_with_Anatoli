# Mobile / Telegram Mini App UI adapt

Промпт для Cursor Agent: адаптация готового сайта под телефон, Mini App и Capacitor, без ломки функционала.

## Как запускать

1. Новый чат → Agent.
2. Вставь блок «Промпт» ниже.
3. Прикрепи: `@AGENTS.md` `@app/static/css/tokens.css` и страницы из scope.
4. Только план без кода: в начало добавь `Сначала только UX-план, код не писать до моего OK.`

## Промпт

```
Роль: сеньор product designer + frontend (Jinja/CSS/JS) для Appointment SaaS.

Стек: FastAPI + Jinja2 + static CSS/JS + Telegram Mini App + Capacitor Android (тот же сайт в WebView). БД/API не ломать. Админ-панель desktop-only - не трогать.

Цель: адаптировать уже готовый UI под три клиента с одним функционалом:
1) Telegram Mini App
2) Android-приложение (Capacitor WebView)
3) мобильный браузер (≤768px)
Desktop (≥1024) не ломать без необходимости.

Оркестрация (AGENTS.md):
- Сначала короткий UX-план (Product Designer, ≤15 строк): экраны, проблемы, DoD.
- Потом Visual (+ Calendar Schedule / Hubs / Public Booking по зонам файлов).
- QA/Browser только после правок: 375px + проверка TG shell (#tg-scroll-root).
- Читать только файлы в scope; bump ?v= у изменённых CSS/JS.
- Не коммитить без просьбы. Не трогать data.db / .env.

Сохранить: весь функционал, сценарии, API, тексты по смыслу, тёмные токены tokens.css, бренд. Не изобретать новый бренд и не копировать «AI-look» (фиолетовые градиенты, cream+serif, glassmorphism).

Проблемы (обязательно закрыть):
A) Календарь / слоты / форма записи на мобиле неудобны: всё критичное должно читаться в одном первом экране; дальше - вертикальный скролл с явной индикацией «какой блок сейчас открыт» (sticky step/section header или progress: Услуга → День → Время → Контакты и т.п.). Day-first / list, не горизонтальные desktop-сетки.
B) Вкладки вроде «Услуги» и другие хабы: кривой перенос текста, обрезанные заголовки, «сжатый desktop» - сделать настоящий mobile layout (одна колонка, touch ≥44px, нормальный line-clamp/wrap, без горизонтального overflow).
C) Mini App: safe-area, не ломать sticky scroll shell, единый вид с телефоном.

Метод работы (как сеньор):
1) Сам найди 3–5 сильных open-source референсов UX (не тащить их код как зависимость) по темам: appointment booking mobile, calendar day picker, CRM services list mobile, Telegram Mini App UX. Примеры направлений: Cal.com (mobile booking), Calendly-like funnels, Notion/Linear mobile density patterns, Telegram WebApp samples - выбери актуальные GitHub-репо сам через web search, кратко запиши что берёшь (паттерны, не копипаст).
2) Пройди ключевые маршруты глазами (и Browser MCP после кода): /book/, календарь специалиста, /services/, /calendars/, /booking/, /my-bookings/, /tg/, профиль. Зафиксируй баги адаптива.
3) Внедри mobile-first правки в CSS/templates/JS в scope Visual/Hubs/Calendar/Public Booking. Предпочтительно shared patterns в tokens/responsive/hub-shared/tg-webapp, без дублирования на каждую страницу.
4) Самопроверка: нет горизонтального скролла на 375; формы помещаются в первый экран по смыслу; при скролле видно активный блок; тексты не ломаются; TG и Capacitor не регрессируют auth/deep links.

Порядок внедрения:
1. Календарь + публичная запись (самый болезненный UX)
2. Услуги и остальные specialist hubs
3. Общая шапка/меню/карточки навигации
4. Mini App polish (tg-webapp.css + shell)

DoD:
- [ ] Mobile ≤768: календарь/запись - day-first, один экран на шаг или sticky индикатор секции
- [ ] Услуги и хабы: читаемый текст, без «кривого desktop»
- [ ] Touch targets ≥44px
- [ ] TG safe-area + #tg-scroll-root ок
- [ ] Desktop без регресса основных сценариев
- [ ] ?v= bumped; короткий тест-план для QA

Начни с аудита 2–3 худших экранов + мини-плана, затем сразу правь календарь/запись. Источники с GitHub выбирай сам; в ответе кратко перечисли какие паттерны взял и куда применил.
```

## Scope (ориентир)

| Зона | Файлы |
|------|--------|
| Calendar Schedule | `calendar-schedule.css`, `calendar_detail*`, `calendar-*.js` |
| Public booking | `booking.css`, `public/*`, `public-*.js` |
| Services hub | `services.html`, `services-catalog.css`, `services-page.js` |
| Hubs shared | `hub-shared.css`, `*-hub.css`, app header |
| Mini App shell | `tg-webapp.css`, `telegram-webapp.js` |
| Tokens | `tokens.css`, `responsive.css` |

Out of scope: `platform_admin/*`, bot business logic (кроме UI copy), schema/API breaking changes.

## Audit 2026-08-01 (календарь + услуги)

### Референсы (паттерны, не код)
- [cal.com](https://github.com/calcom/cal.com): day-first / slots focus on small screen, sticky step awareness, меньше лишнего скролла после выбора даты
- Telegram Mini Apps UI kit methodology (см. `PROMPTS/TELEGRAM_MINIAPP_UI.md`): safe-area, touch ≥44px

### Найдено
| Экран | Проблема |
|-------|----------|
| `/calendars/{id}/` | Недельная сетка `min-width: 640px` как primary на телефоне; копирайт «редактор справа»; настройки сверху и длинный скролл без индикатора секции |
| `/services/` | List-вид в ряд ломает текст; toolbar/filters desktop; analytics labels wrap плохо |
| `/s/.../c/.../` запись | 3 панели в столбец без sticky «какой шаг»; после выбора даты не ясно, что дальше |

### Сделано в этой итерации
- Calendar: day chips + скрытие week-grid ≤768, sticky progress (День / Настройки / Параметры), settings accordion on mobile
- Services + hub-shared: stacked cards, wrap titles, toolbar column, touch 44px
- Public book: sticky step progress + scroll-to-next after service/date

### QA план
- [ ] 375px: календарь - чипы дней, редактор, без горизонтального скролла сетки
- [ ] 375px: услуги - заголовки читаемы, фильтры в колонку
- [ ] 375px: публичная запись - sticky 1/2/3, после даты скролл к времени
- [ ] ≥1024: week grid + 3-col book layout без регресса
- [ ] TG WebView: safe-area, `#tg-scroll-root` ок
