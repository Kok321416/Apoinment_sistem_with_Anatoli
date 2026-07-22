# План ускорения сайта (TTFB / first paint / кабинет)

Цель: страницы открываются за **1–3 с** после warm-start, а не за **8–15 с**.
Функционал сохраняем; режем лишние блокировки и cold start.

Связано с хостингом: reg.ru + Passenger + MySQL (`/var/www/u3390636/data/www/allyourclients.ru`).

---

## 1. Почему сейчас ~10 секунд (корневые причины)

### A. Cold start Passenger (главный виновник «все страницы долго»)
На shared-хостинге Python-воркер **засыпает** после простоя.
Первый HTTP-запрос поднимает процесс, импортирует FastAPI/SQLAlchemy, иногда трогает схему.
Симптом: `/`, `/login/`, `/dashboard/` - все одинаково медленные после паузы;
повторный заход быстрее. `/health` тоже медленный = cold start, не вёрстка.

### B. MySQL на каждый запрос
Почти каждый роут: `Depends(get_db)` + `get_current_user` + middleware
`password_required` (ещё одна сессия БД для залогиненных).
`pool_pre_ping=True` = лишний `SELECT 1` на checkout.
На reg.ru connect к MySQL часто 0.3–2 с.

### C. Внешние ресурсы в `<head>`
- Google Fonts (раньше блокировали рендер; сейчас async через `media=print`)
- `telegram-web-app.js` на кабинете и booking (сеть до telegram.org)
- Метрика отложена - ок

### D. UI «тёмный экран» на лендинге (отдельно от TTFB)
Секции ниже hero были с `opacity: 0` до JS (`.reveal`) +
`content-visibility` (`.section--defer`) → при скролле чёрный экран на секунды.
**Исправлено в коде:** контент виден сразу, reveal без скрытия по умолчанию.

### E. Shared hosting лимиты
CPU/RAM/I/O общие; несколько Passenger workers; нет постоянного keepalive
процесса как на VPS с systemd.

---

## 2. Уже сделано (этот PR)

| Изменение | Эффект |
|-----------|--------|
| Лендинг: убраны `reveal` / `section--defer` с контента | Нет чёрного экрана при скролле |
| Reveal CSS progressive (контент виден без JS) | Безопасно на других страницах |
| `/` без MySQL для гостя | Быстрее TTFB главной |
| Telegram WebApp JS не грузится на landing/privacy/terms | Меньше сетевых запросов |
| Google Fonts не блокируют first paint | Раньше виден текст |

---

## 3. План работ (по приоритету)

### P0 - Ops (сегодня, без кода) — убрать cold start
1. **Cron keep-alive каждые 5 мин** (панель reg.ru → Планировщик):
   ```cron
   */5 * * * * curl -fsS -o /dev/null https://allyourclients.ru/health
   ```
2. После деплоя вручную один раз открыть `/health` и `/`.
3. Замерить: DevTools Network → документ HTML → Waiting (TTFB).
   Цель warm: TTFB < 1.5 с.

### P1 - Backend (код, 1–2 дня)
1. **Не открывать DB в middleware**, если нет `session user_id`
   (уже частично так; проверить все пути).
2. **Объединить** password_required + get_current_user в один DB round-trip на запрос.
3. **Кэш session user** в `request.state` на время одного HTTP-запроса.
4. Опционально: `pool_pre_ping` только после idle > N сек (или pool_recycle короче).
5. Публичные страницы (`/guide/`, `/privacy/`, `/terms/`, login GET) —
   без DB для гостя (как лендинг).

### P2 - Frontend assets (0.5–1 день)
1. Self-host Inter (woff2) или system-ui stack на landing —
   ноль зависимости от fonts.googleapis.com.
2. Кабинет: грузить `telegram-web-app.js` **только** если UA Telegram / Mini App.
3. Свести CSS: меньше `@import` cascade; критичный CSS inline для hero (опционально).
4. Проверить, что static отдаётся с Cache-Control (уже есть middleware).

### P3 - Хостинг (если P0+P1 мало)
1. VPS / отдельный процесс uvicorn+systemd вместо «засыпающего» Passenger.
2. Redis session / локальный unix-socket MySQL если DB remote.
3. CDN для `/static/` (Cloudflare) — ускоряет CSS/JS, не TTFB HTML.

### P4 - Не трогать ради скорости
- Админ SSE KPI - только staff
- Broadcast worker - cron, не HTTP
- Метрика - уже deferred

---

## 4. Как мерить (обязательно)

На проде после keep-alive:

```bash
# TTFB главной (гость)
curl -o /dev/null -s -w "TTFB:%{time_starttransfer} Total:%{time_total}\n" https://allyourclients.ru/

# Cold vs warm: подождать 15 мин без запросов, снова curl, потом сразу ещё раз
curl -o /dev/null -s -w "TTFB:%{time_starttransfer}\n" https://allyourclients.ru/health
```

В браузере: Network → документ → Waiting (TTFB) vs Content Download.
Если Waiting = 8 с, а Download = 50 мс → проблема сервер/Passenger/MySQL, не CSS.

---

## 5. Definition of Done по скорости

| Сценарий | Цель |
|----------|------|
| `/` гость, warm | TTFB < 1.5 с, ниже fold виден сразу |
| `/login/`, warm | TTFB < 2 с |
| `/dashboard/` залогинен, warm | TTFB < 2.5 с |
| После 20 мин простоя + keep-alive | нет «10 с» |
| Cold без keep-alive | допустимо до 5–8 с один раз |

---

## 6. Порядок внедрения

```
1. Deploy текущих фиксов лендинга
2. Cron keep-alive /health
3. Замер TTFB
4. P1 backend (guest pages без DB, request-scoped user)
5. P2 Telegram JS только в Mini App + self-host fonts
6. Если всё ещё >5 с warm → миграция с Passenger на VPS/systemd
```
