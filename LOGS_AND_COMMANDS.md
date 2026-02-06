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

### Экран «Эксперты Google не проверяли это приложение»

Это предупреждение показывается, когда приложение OAuth в режиме **Testing** (тестирование). Есть два пути:

1. **Оставить Testing и добавить тестовых пользователей** (проще):  
   В Google Cloud Console → **APIs & Services** → **OAuth consent screen** → внизу раздел **Test users** → **+ ADD USERS** → добавьте email всех, кто будет подключать календарь или входить через Google (например superego19391939@gmail.com). Эти пользователи смогут войти без предупреждения; остальные увидят экран «приложение не проверено».

2. **Убрать предупреждение для всех** (для продакшена): перевести приложение в Production и пройти проверку Google. Пошагово — см. раздел **7.1** ниже.

### 7.1. Как перевести приложение в Production и пройти проверку Google

Официальные инструкции: [Submitting your app for verification](https://support.google.com/cloud/answer/13461325), [OAuth App Verification Help Center](https://support.google.com/cloud/answer/9110914).

**Шаг 1. Подготовить OAuth consent screen**

1. Откройте [Google Cloud Console](https://console.cloud.google.com/) → выберите проект приложения.
2. **APIs & Services** → **OAuth consent screen**.
3. Нажмите **Edit App** и заполните все обязательные поля (если ещё не заполнены):
   - **App name** — название приложения (отображается пользователю).
   - **User support email** — email для поддержки пользователей.
   - **App logo** (по желанию).
   - **App home page** — URL главной страницы сайта (должен быть доступен по HTTPS).
   - **App privacy policy** — ссылка на политику конфиденциальности (обязательно для Production).
   - **App Terms of Service** (если есть).
   - **Authorized domains** — добавьте домен сайта (например `allyourclients.ru`) без `https://`. Домен должен быть проверен (через Search Console или добавление DNS-записи).
   - **Developer contact information** — email, на который Google будет присылать уведомления о проверке.
4. В разделе **Scopes** оставьте только те области доступа, которые реально нужны приложению (вход через Google + календарь). Лишние scope могут усложнить проверку.
5. На каждой странице нажимайте **Save and Continue**, дойдите до **Summary** и сохраните.

**Шаг 2. Опубликовать приложение в Production**

1. На странице **OAuth consent screen** вверху отображается статус **Testing**.
2. Нажмите кнопку **Publish App**.
3. Подтвердите публикацию. Статус сменится на **In production**. После этого приложение смогут использовать любые пользователи с Google-аккаунтом, но при первом входе Google может показывать предупреждение «Эксперты не проверяли это приложение», если запрашиваются чувствительные (sensitive) или ограниченные (restricted) области доступа.

**Шаг 3. Отправить приложение на проверку (верификацию)**

1. На той же странице **OAuth consent screen** нажмите **Prepare for Verification** (или **Submit for Verification** / «Подготовить к проверке»).
2. Пройдите по шагам формы:
   - Проверьте и при необходимости обновите данные приложения, нажмите **Save and Continue**.
   - **Scope Justification** (обоснование областей доступа): если приложение запрашивает **sensitive** или **restricted** scope (например доступ к Google Calendar), нужно кратко описать, зачем приложению нужен каждый такой scope и как вы используете данные. Писать на английском предпочтительно.
   - **Demo Video** (демо-видео): для sensitive/restricted scope Google часто требует короткое видео (обычно до 5 минут), где показаны: экран согласия OAuth, вход в приложение и использование возможностей, которые требуют доступа к календарю/данным. Видео можно загрузить на YouTube (доступ «по ссылке» или «без списка») и указать ссылку в форме. Требования: [Demo video guidelines](https://support.google.com/cloud/answer/13464321#demo-video).
3. В конце нажмите **Submit for Verification**. Заявка уйдёт в команду проверки Google.

**Шаг 4. После отправки**

- Все письма от Google приходят на **Developer contact information** (и владельцам проекта). Следите за почтой.
- Проверка может занять от нескольких дней до нескольких недель. Для приложений только с **non-sensitive** scope иногда достаточно быстрой проверки (brand verification); для **sensitive/restricted** (календарь и т.п.) — полная проверка.
- Если что-то не так, Google пришлёт письмо с перечнем замечаний — нужно исправить и при необходимости отправить заявку снова.
- После успешной верификации предупреждение «Эксперты не проверяли это приложение» для вашего приложения перестаёт показываться пользователям.

**Полезные ссылки**

- [Требования к верификации](https://support.google.com/cloud/answer/13464321) (домашняя страница, политика конфиденциальности, домены, видео).
- [Когда верификация не нужна](https://support.google.com/cloud/answer/13464323).
- Для личного или внутреннего использования проще и быстрее оставаться в **Testing** и добавлять нужных пользователей в **Test users** (см. вариант 1 выше).
