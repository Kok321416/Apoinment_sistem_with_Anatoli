# Логи и команды для проверки бота и интеграций

Подключитесь к серверу по SSH и используйте команды ниже, чтобы проверить работу Telegram-бота и найти ошибки.

---

## 1. Где лежат логи бота

- **Файл** (если бот пишет в файл): в **корне репозитория** каталог `logs/`, файл `telegram_bot.log`.  
  Путь задаётся в настройках: `TELEGRAM_BOT_LOG_FILE` (по умолчанию `logs/telegram_bot.log`).
- **systemd**: если бот запущен как сервис `telegram-bot`, логи пишутся в journal.

---

## 1.1. Ошибка деплоя: `ModuleNotFoundError: No module named 'MySQLdb.constants'`

На сервере используется MySQL, а драйвер для Python — **PyMySQL**. Если при деплое бот падает с этой ошибкой:

1. В **requirements.txt** в корне репозитория должна быть строка `PyMySQL==1.1.1` (или совместимая версия).
2. В workflow деплоя после `pip install -r requirements.txt` добавлена проверка: если `import pymysql` не удаётся, деплой завершается с ошибкой.
3. Перед запуском бота выполняется проверка подключения к MySQL (Django + PyMySQL). Если она не проходит, деплой падает с сообщением «MySQL/PyMySQL check failed».
4. Лог бота перед запуском очищается (`: > bot.log`), чтобы в отчёте деплоя были только сообщения текущего запуска.

**Ошибка `cannot import name 'LANG_INFO' from 'django.conf.locale'`:** обычно значит повреждённую или неполную установку Django в venv. В деплое после установки зависимостей добавлена переустановка Django (`pip install --force-reinstall --no-cache-dir Django==...`) и проверка импорта. Если ошибка сохраняется на сервере — выполните вручную: `./venv/bin/pip install --force-reinstall --no-cache-dir Django==5.2.7`.

**Ошибка `No module named 'pip'` / `pip._vendor.packaging.markers`:** см. выше про ensurepip и отсутствие повторного вызова pip после миграций.

Если ошибка сохраняется: на сервере вручную выполните из корня репозитория:
`./venv/bin/python -c "import pymysql; pymysql.install_as_MySQLdb(); import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'appoiment_system.settings'); django.setup(); from django.db import connection; connection.ensure_connection(); print('OK')"`  
Если команда падает — проверьте, что в venv установлен PyMySQL (`./venv/bin/pip show PyMySQL`) и что в `.env` заданы корректные `DB_*` переменные.

---

## 1.2. Ошибка деплоя: «PyMySQL is required for the bot (pip install PyMySQL)»

Эта ошибка появляется, когда бот запускается **не из venv** (например, вызывается `python manage.py run_bot` без активации venv или из другого каталога).

**Что сделать:**

1. **Запускать бота только через скрипт** (он всегда использует venv проекта):
   ```bash
   cd /путь/к/корню/репозитория
   ./scripts/run_bot.sh
   ```
   В nohup/systemd тоже используйте этот скрипт:
   ```bash
   nohup ./scripts/run_bot.sh >> bot.log 2>&1 &
   ```

2. **Если на сервере при деплое вызывается `entrypoint.sh`** — в репозитории есть свой `entrypoint.sh`: он создаёт/обновляет venv, ставит зависимости, запускает миграции и стартует бота через `scripts/run_bot.sh`. Убедитесь, что на сервере после загрузки файлов вызывается именно он: `./entrypoint.sh` (из каталога приложения, можно задать `APP_DIR`).

3. В **GitHub Actions** деплой переведён на запуск бота через `scripts/run_bot.sh` и в workflow добавлен **export APP_DIR**, чтобы при запуске через nohup дочерний процесс получал путь к приложению и бот использовал правильный venv. Если ошибка «PyMySQL is required» всё же появляется в bot.log после деплоя — на сервере проверьте: `echo $APP_DIR` в том же окружении, где запускается бот; при ручном запуске используйте `export APP_DIR=/путь/к/проекту` перед `nohup ./scripts/run_bot.sh`.

---

## 1.3. Ошибка: «Превышено максимальное количество ошибок сети. Остановка.»

Бот запускается (PyMySQL OK, «Бот запущен»), но при запросах к **api.telegram.org** (getUpdates) получает сетевые ошибки (таймаут, соединение отклонено и т.п.) и после N попыток завершается.

**Что сделать:**

1. **Проверить доступ к Telegram API с сервера:**
   ```bash
   curl -I --connect-timeout 10 https://api.telegram.org
   ```
   Если команда падает или таймаут — на сервере или в сети заблокирован/недоступен Telegram. Нужно открыть исходящий HTTPS до api.telegram.org (порт 443) или использовать VPN/прокси на сервере.

2. **Устойчивость бота** в коде уже повышена: больше попыток (50), увеличен таймаут запроса (60 сек), пауза между повторами при ошибках (30 сек и выше). После обновления кода и перезапуска бота временные сбои сети реже приводят к остановке.

3. **Webhook вместо long polling:** если у сайта есть постоянный HTTPS-адрес, можно перейти на [webhook](https://core.telegram.org/bots/api#setwebhook): Telegram сам отправляет обновления на ваш URL, исходящие запросы к getUpdates не нужны. В настройках проекта задаётся `TELEGRAM_USE_WEBHOOK=True` и `TELEGRAM_WEBHOOK_URL=https://ваш-домен/api/telegram/webhook/` (и реализуется соответствующий endpoint).

---

## 1.4. Ошибка деплоя: `ModuleNotFoundError: No module named 'urllib3'`

При старте бота Django загружает django-allauth → Google provider → `requests` → `urllib3`. На части хостингов в venv не оказывается `urllib3` (зависимость `requests` может не установиться полностью).

**Что сделано:** в **requirements.txt** добавлена явная зависимость `urllib3>=1.26.0,<3`. После следующего деплоя пакет будет установлен.

Если ошибка появится снова: на сервере вручную выполните `./venv/bin/pip install "urllib3>=1.26.0,<3"` и перезапустите бота (`./scripts/run_bot.sh`).

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

## 5.1.1. SITE_URL — ссылки «Записаться» и «Регистрация» в боте

Кнопки бота («Записаться», «Регистрация», «Открыть на сайте») ведут на ваш сайт. URL берётся из переменной **SITE_URL** (в `.env` или в настройках приложения на хостинге).

**Если кнопки открывают не тот сайт или пустую страницу:**

1. Убедитесь, что на сервере в окружении приложения задано:  
   `SITE_URL=https://allyourclients.ru` (или ваш реальный домен, без слэша в конце).
2. В GitHub Secrets для деплоя должен быть задан **SITE_URL** с тем же значением.
3. После изменения перезапустите бота (см. раздел 5).

Без правильного SITE_URL ссылки в боте могут вести на localhost или старый адрес.

---

## 5.1.2. Как реализованы напоминания (связь с настройками календаря)

Напоминания отправляет **не бот**, а команда Django **send_booking_reminders** (приложение consultant_menu). Она должна запускаться по расписанию (cron).

### Схема работы

1. **Настройки календаря**  
   Специалист в разделе «Календари» → выбранный календарь → «Настройки» задаёт:
   - **Первое напоминание за (часов)** — например 24 (за сутки);
   - **Второе напоминание за (часов)** — например 1 (за час).  
   Значения хранятся в модели Calendar: `reminder_hours_first`, `reminder_hours_second`.

2. **Запуск команды (cron)**  
   Периодически (рекомендуется каждые 15–30 минут) на сервере выполняется команда. Она:
   - выбирает активные записи (статус pending/confirmed, дата в будущем);
   - для каждой записи берёт **часы из календаря этой записи** (у каждого календаря свои настройки);
   - если до времени консультации осталось примерно N часов (окно ±30 мин), отправляет напоминание в Telegram клиенту и/или специалисту;
   - выставляет флаги `reminder_24h_sent` / `reminder_1h_sent` (и для специалиста), чтобы не слать повторно.

3. **Кому приходят напоминания**  
   - **Клиенту** — если у записи заполнен `telegram_id` (клиент подтвердил Telegram по ссылке после записи или в боте).  
   - **Специалисту** — если в разделе «Интеграции» на сайте подключён Telegram (у консультанта есть Integration с `telegram_chat_id`).

Таким образом, механизм **автоматизирован** (запуск по cron) и **жёстко связан с настройками календаря**, которые задаёт специалист.

### Запуск вручную

Из корня репозитория (после `chmod +x scripts/run_reminders.sh`):

```bash
./scripts/run_reminders.sh
```

Либо из каталога appoinment_sistem:

```bash
cd /путь/к/проекту/appoinment_sistem
../venv/bin/python manage.py send_booking_reminders
```

### Автоматизация (cron)

1. **Путь к проекту** — замените на фактический путь на сервере (где лежит репозиторий).  
   Примеры: `/var/www/Online_appointment_for_consultations`, `/home/username/Online_appointment_for_consultations`.

2. **Один раз выполните на сервере:**
   ```bash
   # Создать каталог для логов
   mkdir -p /путь/к/проекту/logs
   # Сделать скрипт исполняемым
   chmod +x /путь/к/проекту/scripts/run_reminders.sh
   ```

3. Добавьте в crontab (`crontab -e`) строку (подставьте **свой** путь к проекту вместо `/путь/к/проекту`):

```cron
*/20 * * * * /путь/к/проекту/scripts/run_reminders.sh >> /путь/к/проекту/logs/reminders.log 2>&1
```

**Пример с реальным путём** (если проект развёрнут в `/var/www/Online_appointment_for_consultations`):

```cron
*/20 * * * * /var/www/Online_appointment_for_consultations/scripts/run_reminders.sh >> /var/www/Online_appointment_for_consultations/logs/reminders.log 2>&1
```

Это запуск каждые 20 минут. Можно использовать `*/15` или `*/30`. Готовый пример: `scripts/cron_reminders.example`.

На виртуальном хостинге (reg.ru и др.) настройка cron обычно доступна в панели управления (раздел «Планировщик» / «Cron»).

#### Reg.ru: если сайт в www/allyourclients.ru, venv в data/

На reg.ru домашний каталог по SSH — это `/var/www/u3390636/data`. Проект часто лежит в `www/allyourclients.ru`, а venv — в `data/venv`. Скрипт `run_reminders.sh` автоматически подхватывает venv из каталога на уровень выше (`../venv`), если в корне проекта venv нет.

**Один раз на сервере:**
```bash
export PROJECT_ROOT="/var/www/u3390636/data/www/allyourclients.ru"
mkdir -p "$PROJECT_ROOT/logs"
chmod +x "$PROJECT_ROOT/scripts/run_reminders.sh"
```

**Строка для cron** (в панели reg.ru «Планировщик» или `crontab -e`):
```cron
*/20 * * * * /var/www/u3390636/data/www/allyourclients.ru/scripts/run_reminders.sh >> /var/www/u3390636/data/www/allyourclients.ru/logs/reminders.log 2>&1
```

Проверка вручную:
```bash
/var/www/u3390636/data/www/allyourclients.ru/scripts/run_reminders.sh
```

---

## 5.2. Стили не обновляются (всё ещё фиолетовый цвет, кэш)

Тема сайта задаётся в `consultant_menu/static/consultant_menu/css/style.css` (серый/белый/чёрный). Если после обновления кода вы по-прежнему видите старые фиолетовые цвета:

1. **На сервере после деплоя** обязательно выполните сбор статики (в скрипте деплоя обычно уже есть, но можно вручную):
   ```bash
   cd appoinment_sistem
   python manage.py collectstatic --noinput
   ```
   Тогда обновлённый `style.css` попадёт в `staticfiles/` и будет отдаваться пользователям.

2. **Кэш браузера:** сделайте принудительное обновление страницы: **Ctrl+F5** (Windows/Linux) или **Cmd+Shift+R** (Mac). Либо откройте сайт в режиме инкогнито.

3. **В коде** к ссылке на CSS добавлен параметр `?v=2` — при следующем изменении темы можно увеличить версию (например `?v=3`), чтобы браузеры заново загрузили файл стилей.

---

## 5.3. Конфликт при слиянии develop и main (home.html)

**Автоматически оставить вариант develop при слиянии:**  
Находясь в ветке **develop**, выполните слияние с **main** с опцией «в конфликтах брать нашу версию»:

```bash
git checkout develop
git pull origin develop
git merge main -X ours -m "Merge main into develop (keep develop version on conflicts)"
```

Опция **`-X ours`** означает: при любом конфликте оставлять версию из текущей ветки (develop). Конфликты не появятся, правки из main подтянутся там, где нет конфликта. Если нужно наоборот (при слиянии develop в main оставлять main) — делайте merge на main и используйте `-X ours` там (тогда «ours» = main).

---

При слиянии **без** `-X ours` Git может показать конфликт в `consultant_menu/templates/consultant_menu/home.html`:

- **develop:** полная HTML-страница (`<!DOCTYPE>`, `<head>`, `<link ... style.css ?v=2>`, `<body>`, контент, футер).
- **main:** одна строка `{% extends 'header.html' %}` (шаблон-наследник).

**Как разрешить:** оставьте вариант **develop** (полную страницу). Файл `header.html` в проекте не содержит `<body>` и блоков для `{% block content %}`, поэтому вариант с `extends` приведёт к пустой или сломанной странице.

1. Откройте `appoinment_sistem/consultant_menu/templates/consultant_menu/home.html`.
2. Удалите маркеры конфликта (`<<<<<<< develop`, `=======`, `>>>>>>> main`) и весь фрагмент со стороны **main** (строку `{% extends 'header.html' %}`).
3. Оставьте весь код со стороны **develop** (от `<!DOCTYPE html>` до `</html>` включительно).
4. Сохраните файл, выполните `git add appoinment_sistem/consultant_menu/templates/consultant_menu/home.html` и завершите слияние (`git commit`).

Итоговое начало файла должно быть таким:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    ...
    <link rel="stylesheet" href="{% static 'consultant_menu/css/style.css' %}?v=2">
</head>
<body>
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

### Консультации не отображаются в Google Calendar после подключения

Если вы подключили Google Calendar в разделе «Интеграции», но новые записи не появляются в календаре:

1. **Настройки проекта:** в `settings.py` должны быть заданы `TIME_ZONE = "Europe/Moscow"` (или ваш часовой пояс) и `USE_TZ = True`. В `.env` при необходимости можно задать `TIMEZONE=Europe/Moscow`.
2. **Новые записи:** события создаются **при создании новой записи** (публичная запись на сайте или через бота). Старые записи, созданные до подключения календаря, в Google не переносятся.
3. **Проверка:** создайте тестовую запись после подключения календаря и обновите Google Calendar (календарь «Основной» или выбранный в интеграциях). Если события по-прежнему нет — проверьте логи сервера на сообщения `consultant_menu Google Calendar: ошибка создания события` (неверный токен, нет прав и т.д.).
4. **Права доступа:** при подключении календаря должен быть выдан scope `https://www.googleapis.com/auth/calendar.events`. Если вы подключали только вход через Google (без календаря), зайдите снова в «Интеграции» и нажмите «Подключить Google Calendar».

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
   - **Authorized domains** — добавьте домен сайта (например `allyourclients.ru`) **без** `https://`. Домен обязательно должен быть **верифицирован** в Google Search Console (см. раздел **7.2** ниже).
   - **Developer contact information** — email, на который Google будет присылать уведомления о проверке.
4. В разделе **Scopes** оставьте только те области доступа, которые реально нужны приложению (вход через Google + календарь). Лишние scope могут усложнить проверку.
5. На каждой странице нажимайте **Save and Continue**, дойдите до **Summary** и сохраните.

### 7.2. «The website of your home page URL is not registered to you» — верификация домена

Если при проверке Google пишет, что сайт (home page URL) не зарегистрирован на вас, нужно **подтвердить владение доменом** через **Google Search Console**. Без этого верификация приложения не пройдёт.

**Пошагово:**

1. Откройте [Google Search Console](https://search.google.com/search-console) и войдите под тем же Google-аккаунтом, который является **владельцем (Owner)** или **редактором (Editor)** проекта в Google Cloud Console (тот, где создано OAuth-приложение).

2. Добавьте ресурс (сайт):
   - Нажмите **«Добавить ресурс»** / **Add property**.
   - Выберите **«Домен»** (Domain), если хотите верифицировать сразу весь домен (например `allyourclients.ru`), **или** **«Префикс URL»** (URL prefix), например `https://allyourclients.ru/`.

3. **Способ верификации домена** (для типа «Домен»):
   - Google покажет **DNS-запись** (TXT), которую нужно добавить у регистратора домена (там, где куплен allyourclients.ru).
   - Зайдите в панель управления доменом → DNS / DNS-записи → добавьте запись типа **TXT** с именем и значением, которые указал Search Console.
   - Подождите несколько минут (иногда до 24 часов), затем в Search Console нажмите **«Проверить»** (Verify).

4. **Способ верификации по URL (префикс):**
   - Можно вместо домена добавить ресурс «Префикс URL»: `https://allyourclients.ru`.
   - Тогда Google предложит верификацию через HTML-файл (скачать файл, положить в корень сайта) или через HTML-тег в `<head>` главной страницы. Выполните один из вариантов и нажмите «Проверить».

5. После успешной верификации домен будет считаться «вашим» для Google. Вернитесь в **Google Cloud Console** → **OAuth consent screen** → **Authorized domains** и убедитесь, что там указан домен **без** `https://` (например `allyourclients.ru`).

6. В письме от Google выберите **«I have fixed the issues»** → **«Request re-verification for your branding»**, чтобы отправить заявку на повторную проверку. После верификации домена в Search Console повторная проверка обычно проходит.

**Важно:** Владельцем или редактором в GCP и верификатором в Search Console должен быть один и тот же аккаунт Google (или добавьте нужный аккаунт в оба места).

Подробнее: [Verify your site ownership (Search Console)](https://support.google.com/webmasters/answer/9008080), [Verification requirements — Domain](https://support.google.com/cloud/answer/13464321#verified-domain-requirement).

---

**Шаг 2. Опубликовать приложение в Production**

1. На странице **OAuth consent screen** вверху отображается статус **Testing**.
2. Нажмите кнопку **Publish App**.
3. Подтвердите публикацию. Статус сменится на **In production**. После этого приложение смогут использовать любые пользователи с Google-аккаунтом, но при первом входе Google может показывать предупреждение «Эксперты не проверяли это приложение», если запрашиваются чувствительные (sensitive) или ограниченные (restricted) области доступа.

**Шаг 3. Отправить приложение на проверку (верификацию)**

1. На той же странице **OAuth consent screen** нажмите **Prepare for Verification** (или **Submit for Verification** / «Подготовить к проверке»).
2. Пройдите по шагам формы:
   - Проверьте и при необходимости обновите данные приложения, нажмите **Save and Continue**.
   - **Scope Justification** (обоснование областей доступа): если приложение запрашивает **sensitive** или **restricted** scope (например доступ к Google Calendar), нужно кратко описать, зачем приложению нужен каждый такой scope и как вы используете данные. Писать на английском предпочтительно.
   - **Demo Video** (демо-видео): для sensitive/restricted scope Google часто требует короткое видео. Подробный чек-лист — в разделе **7.1.3** ниже. Официальные требования: [Demo video guidelines](https://support.google.com/cloud/answer/13464321#demo-video).
3. В конце нажмите **Submit for Verification**. Заявка уйдёт в команду проверки Google.

### 7.1.3. Требования к демо-видео для проверки Google (чтобы убрать «небезопасно» / «приложение не проверено»)

Видео нужно для приложений с **sensitive** или **restricted** scope (в т.ч. доступ к Google Calendar). Загрузите на YouTube (доступ «по ссылке» или «без списка») и укажите ссылку в форме верификации.

**Что обязательно показать в видео:**

1. **Полный поток OAuth**  
   Показать **экран согласия Google (OAuth Consent Screen)** — страницу, где пользователь нажимает «Разрешить» / «Allow». На экране должны быть видны **те же самые scope**, которые запрашивает приложение (например доступ к календарю). В левом нижнем углу экрана согласия **язык должен быть переключён на English**.

2. **То же приложение, что на проверке**  
   В кадре должны быть те же **название приложения и брендинг**, что указаны в OAuth consent screen (тот же домен, тот же сайт).

3. **Функции, которые используют запрошенные scope**  
   После входа показать, **как приложение использует доступ к календарю** (или другим данным): например вход на сайт → раздел «Интеграции» → «Подключить Google Calendar» → создание/просмотр записей и отображение их в Google Calendar. Должен быть виден **сквозной сценарий**: от нажатия «Войти через Google» / «Подключить календарь» до реального использования данных (записи в календаре).

**Краткий чек-лист перед загрузкой:**

- [ ] В кадре виден экран согласия Google (OAuth consent) с переключённым на **English**.
- [ ] На экране согласия видны те же scope, что запрашиваете (например calendar.events).
- [ ] Показан ваш сайт/приложение с тем же названием и доменом, что в настройках OAuth.
- [ ] Показано использование доступа к календарю: подключение календаря и создание/отображение событий в Google Calendar.
- [ ] Видео до 5 минут, без лишнего контента; звук/титры по желанию, но сценарий должен быть понятен проверяющему.

**Шаг 4. После отправки**

- Все письма от Google приходят на **Developer contact information** (и владельцам проекта). Следите за почтой.
- Проверка может занять от нескольких дней до нескольких недель. Для приложений только с **non-sensitive** scope иногда достаточно быстрой проверки (brand verification); для **sensitive/restricted** (календарь и т.п.) — полная проверка.
- Если что-то не так, Google пришлёт письмо с перечнем замечаний — нужно исправить и при необходимости отправить заявку снова.
- После успешной верификации предупреждение «Эксперты не проверяли это приложение» для вашего приложения перестаёт показываться пользователям.

**Полезные ссылки**

- [Требования к верификации](https://support.google.com/cloud/answer/13464321) (домашняя страница, политика конфиденциальности, домены, видео).
- [Когда верификация не нужна](https://support.google.com/cloud/answer/13464323).
- Для личного или внутреннего использования проще и быстрее оставаться в **Testing** и добавлять нужных пользователей в **Test users** (см. вариант 1 выше).
