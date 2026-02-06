# Логи и команды для проверки бота и интеграций

Подключитесь к серверу по SSH и используйте команды ниже, чтобы проверить работу Telegram-бота и найти ошибки.

---

## 1. Где лежат логи бота

- **Файл** (если бот пишет в файл): в **корне репозитория** каталог `logs/`, файл `telegram_bot.log`.  
  Путь задаётся в настройках: `TELEGRAM_BOT_LOG_FILE` (по умолчанию `logs/telegram_bot.log`).
- **systemd**: если бот запущен как сервис `telegram-bot`, логи пишутся в journal.

---

## 2. Проверить, работает ли бот

```bash
# Бот запущен как systemd-сервис?
sudo systemctl status telegram-bot

# Или процесс вручную (nohup)?
pgrep -af run_bot
ps aux | grep run_bot
```

Если сервис активен (`active (running)`), бот запущен. Если нет — см. раздел 5.

---

## 3. Смотреть логи бота в реальном времени

**Если используется systemd:**

```bash
# Последние 50 строк
sudo journalctl -u telegram-bot -n 50 --no-pager

# В реальном времени (Ctrl+C — выход)
sudo journalctl -u telegram-bot -f

# За последний час
sudo journalctl -u telegram-bot --since "1 hour ago" --no-pager
```

**Если логи в файл** (корень репозитория):

```bash
cd /путь/к/корню/репозитория

# Последние 100 строк
tail -100 logs/telegram_bot.log

# В реальном времени
tail -f logs/telegram_bot.log
```

---

## 4. Поиск по логам: ошибки и важные события

**Только ошибки и предупреждения:**

```bash
# systemd
sudo journalctl -u telegram-bot --no-pager | grep -E 'ERROR|WARNING|TG bot:.*FAIL|TG bot:.*error'

# файл
grep -E 'ERROR|WARNING|TG bot:.*FAIL|TG bot:.*error' logs/telegram_bot.log
```

**Успешный запуск бота:**

```bash
grep "TG bot: запуск" logs/telegram_bot.log
# или
sudo journalctl -u telegram-bot --no-pager | grep "TG bot: запуск"
```

**Подключение специалиста (интеграции):**

```bash
grep "specialist connect" logs/telegram_bot.log
# OK — успех, FAIL / ConnectionError — ошибка
```

**Подтверждение записи клиентом (кнопка в боте):**

```bash
grep "booking confirm" logs/telegram_bot.log
```

**Входящие сообщения и callback:**

```bash
grep "TG bot: сообщение\|TG bot: callback" logs/telegram_bot.log
```

---

## 5. Перезапуск бота

```bash
# Если настроен systemd (VPS с правами sudo)
sudo systemctl restart telegram-bot
sudo systemctl status telegram-bot

# Проверить логи после перезапуска
sudo journalctl -u telegram-bot -n 30 -f
```

**На виртуальном хостинге (reg.ru и др.) нет sudo** — перезапуск бота делайте вручную (nohup):

```bash
cd /путь/к/проекту
. venv/bin/activate
[ -f bot.pid ] && kill -TERM $(cat bot.pid) 2>/dev/null; rm -f bot.pid; sleep 2
nohup python manage.py run_bot >> bot.log 2>&1 &
echo $! > bot.pid
```

Если сервис не настроен — один раз выполните из корня репозитория: `./deploy_bot.sh` (см. TELEGRAM_ЧТО_СДЕЛАТЬ.md).

---

## 5.1. Миграции при push/деплое

При деплое (GitHub Actions или вручную) выполняется `./scripts/migrate.sh`:

1. **appoinment_sistem** (consultant_menu): миграции 0001–0017, затем `collectstatic`.  
   Если в БД колонки уже есть (ошибка «Duplicate column»), скрипт помечает 0016 и 0017 как применённые (`--fake`) и снова запускает `migrate` — данные не теряются.
2. **appoiment_system** (bookings, telegram_bot): миграции из корня репозитория. При конфликтах имён или «Duplicate column» скрипт правит записи в `django_migrations` и повторяет миграции.

Запуск вручную с сервера (из корня репозитория):

```bash
./scripts/migrate.sh
```

---

## 6. Что проверить в Telegram (BotFather и настройки бота)

- **Токен:** в `.env` в корне репозитория указан правильный `TELEGRAM_BOT_TOKEN` (как у @BotFather). После смены токена перезапустите бота.
- **Домен для «Подключить через браузер» (OAuth):** в BotFather у бота в настройках **Telegram Login Widget** должен быть указан домен вашего сайта (например `allyourclients.ru`), без `https://`.
- **Сайт и бот:** в `.env` задайте `SITE_URL=https://ваш-домен.ru` (обязательно со схемой `https://`). Если указать без схемы (например `allyourclients.ru`), в коде автоматически подставится `https://`, но надёжнее сразу указывать полный URL.

---

## 7. Google OAuth (вход / календарь): ошибка «doesn't comply with OAuth 2.0 policy» (400 invalid_request)

Что проверить в **Google Cloud Console** (https://console.cloud.google.com/):

1. **OAuth consent screen**  
   - **User type:** External.  
   - **Publishing status:**  
     - Либо **Testing** — тогда в «Test users» обязательно добавлен email пользователя (например superego19391939@gmail.com). Без этого вход даёт 400.  
     - Либо **In production** — тогда приложение должно пройти проверку Google (см. инструкцию в чате/документации по переводу в Production).
2. **Authorized redirect URIs** (Credentials → ваш OAuth 2.0 Client ID):  
   Должны быть **ровно** те URL, которые использует сайт (с/без завершающего слэша как в коде):
   - `https://ваш-домен.ru/accounts/google/login/callback/`
   - `https://ваш-домен.ru/integrations/google/callback`
   - `https://ваш-домен.ru/specialist/calendars/google/callback/`
3. **Название приложения** («allcliets_auth» в ошибке) задаётся в OAuth consent screen. Можно сменить на осмысленное (например имя сайта).
4. На **сайте** в продакшене в `.env` должен быть `SITE_URL=https://ваш-домен.ru`, чтобы callback строился по HTTPS (уже учтено в настройках при наличии SITE_URL).

Если после этого ошибка остаётся — добавьте пользователя в Test users (режим Testing) или переведите приложение в Production и пройдите верификацию.
