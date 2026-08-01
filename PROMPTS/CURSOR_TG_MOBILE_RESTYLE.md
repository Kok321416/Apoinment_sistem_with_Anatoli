# Промпт для Cursor: редизайн Telegram Mini App + приложение на телефон

Скопируй блок ниже в новый чат Cursor (Agent). Цель: визуал как у сайта, функционал не ломать.

---

## Промпт

```
Контекст продукта
SaaS «Все клиенты здесь» (allyourclients.ru): FastAPI + Jinja + MySQL + Telegram bot + Capacitor Android.
Прод деплой: push в main. Репо мультиагентное: AGENTS.md, .cursor/rules/*.mdc.
Дизайн-система: docs/DESIGN_SYSTEM.md, tokens в app/static/css/tokens.css.
Продукт только light theme. Референсы: Cal.com, Linear, Notion, Cursor empty workspace.

Задача
Переделать визуал Telegram Mini App и мобильного приложения (Capacitor WebView / remote URL) под дизайн основного кабинета сайта.
Функционал, роуты, auth bridge, bot commands, запись, кабинет - сохранить.
Не делать новый продукт с нуля. Это restyle + UX alignment.

Что входит в scope

1) Telegram Mini App
- app/static/css/tg-webapp.css
- app/static/js/telegram-webapp.js (только если нужно для UI bridge: theme, MainButton, viewport; логику auth не ломать)
- app/templates/components/telegram_webapp.html
- app/templates/public/tg_mini_app.html, tg_apps.html
- страницы кабинета/записи внутри body.tg-webapp (layouts app/booking)
- sticky scroll shell #tg-scroll-root не ломать

2) Приложение на телефон (Capacitor)
- mobile/capacitor.config.json (светлый splash/status bar уже #FFFFFF - сохранить)
- UI идёт с remote https://allyourclients.ru - значит правки веба = правки приложения
- не трогать нативную бизнес-логику без нужды; иконки launcher отдельно, если попросим

3) Общий визуал
- использовать токены: фон #FFFFFF/#FAFAFA, текст #0A0A0A, muted #737373, accent #111111, border #E5E5E5
- убрать/не возвращать purple neon, glassmorphism, тяжёлые glow, тёмную тему
- контраст: фон светлее, текст темнее (не серое на сером)
- карточки, кнопки, empty states, sidenav/bottom nav как на сайте
- touch targets >= 44px
- motion 150-250ms, без прыжков layout

Что НЕ делать
- не менять API контракты, CSRF, OAuth, TOTP, booking business rules
- не ломать Telegram WebApp initData / login bridge
- не форсить dark theme из Telegram themeParams поверх сайта
- не делать admin mobile hamburger
- не коммитить .env / data.db
- не рефакторить весь репо «заодно»
- Browser MCP / широкий explore - только после кода, один раз smoke

Порядок работы (Architect -> Visual + Telegram Bot logic if needed)
1. Короткий план <=15 строк: какие файлы CSS/templates/JS в scope.
2. Сверить текущий tg-webapp.css с tokens.css и app.css cabinet shell.
3. Restyle Mini App shell:
   - header/bg force light
   - списки (записи, услуги, клиенты, календари) - читаемые карточки
   - toolbar без лишнего поиска, если уже убрали на web
   - empty/skeleton: [hidden] не перебивать display:flex/grid (display:none !important)
4. Публичная запись в TG WebView: те же booking steps, визуал booking.css + tg overrides.
5. Capacitor: проверить splash/status bar light; если UI remote - достаточно web deploy.
6. Bump ?v= на изменённых static assets.
7. Smoke:
   - / открытие Mini App shell
   - логин/сессия не ломается
   - кабинет: dashboard, calendars, services, booking list
   - bottom nav / drawer на mobile width 375
8. Commit + push main только если я явно попросил; иначе покажи diff и стоп.

DoD
- Mini App и телефонное приложение визуально в одной светлой стилистике с сайтом
- функционал записи и кабинета работает
- нет «серый текст на сером»
- нет регрессии Telegram bridge и sticky scroll
- краткий список изменённых файлов в ответе

Сначала план и список файлов. Код только в scope. Не читай весь репозиторий.
```

---

## Короткая версия (если лимит)

```
Restyle Telegram Mini App + Capacitor phone app to match allyourclients.ru light design system (tokens.css, Cal.com/Linear/Notion). Keep all functionality: auth bridge, booking, cabinet hubs. Scope: tg-webapp.css, telegram templates/JS bridge only if needed, mobile capacitor light chrome. No dark theme, no purple neon, touch >=44px, fix hidden+display bugs, bump ?v=. Plan <=15 lines, then implement, smoke at 375px. Do not commit unless I ask.
```

---

## После прогона

Проверь вручную:
1. Открыть Mini App из бота
2. Кабинет специалиста на телефоне / Capacitor
3. Создать/открыть запись
4. Контраст карточек и empty states
```
