# Запуск проекта на хостинге reg.ru (через Git и консоль)

Проект адаптирован под **Python 3.10.x** и **Django 4.2 LTS** (типичный стек на reg.ru).
База данных: **MySQL**.

Ниже 2 варианта запуска:

1) **Без Docker (shared/VPS, когда можно ставить пакеты в venv)** — чаще всего это то, что нужно на reg.ru.  
2) **Через Docker (VPS)** — если у вас полный доступ и Docker разрешён.

---

## Вариант A — запуск без Docker (Python 3.10 + MySQL reg.ru)

### 1A. Требования

- Python **3.10.x**
- Доступ к MySQL (данные из панели reg.ru)
- SSH-доступ (чтобы выполнять команды)

### 2A. Клонирование репозитория

```bash
cd ~
git clone https://github.com/ВАШ_ЛОГИН/РЕПОЗИТОРИЙ.git appointment-system
cd appointment-system
```

### 3A. Виртуальное окружение и зависимости

```bash
python3 --version
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> В `requirements.txt` используется **PyMySQL** (pure-python), чтобы установка работала на хостингах без компилятора и dev-пакетов.

### 4A. `.env` под MySQL reg.ru

```bash
cp env.example .env
nano .env
```

Заполните по данным reg.ru:

- `DB_NAME` = имя базы (например `u3390636_default`)
- `DB_USER` = логин (например `u3390636_default`)
- `DB_PASSWORD` = пароль
- `DB_HOST` = `localhost` (если так указано в панели)
- `DB_PORT` = `3306`
- `SECRET_KEY` = сгенерированная строка
- `ALLOWED_HOSTS` = ваш домен/поддомен (например `allyourclients.ru,www.allyourclients.ru`)

Сгенерировать `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 5A. Миграции и статика

```bash
cd appoinment_sistem
python manage.py migrate
python manage.py collectstatic --noinput
```

### 6A. Запуск Gunicorn (минимальный)

```bash
gunicorn appoinment_sistem.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

Чтобы оставить в фоне:

```bash
nohup gunicorn appoinment_sistem.wsgi:application --bind 127.0.0.1:8000 --workers 2 > gunicorn.log 2>&1 &
```

Дальше домен должен быть настроен (через панель/прокси хостинга) на проксирование к `127.0.0.1:8000`.

---

## Вариант B — запуск через Docker (VPS)

### 1B. Требования на хостинге

- **VPS** или сервер с SSH (обычный shared-хостинг с одним MySQL не подойдёт — нужен Docker).
- Установлены **Docker** и **Docker Compose**.
- Открыты порты **80** (HTTP) и **22** (SSH).

---

### 2B. Клонирование репозитория

Подключитесь по SSH к серверу и выполните:

```bash
cd /opt
sudo git clone https://github.com/ВАШ_ЛОГИН/РЕПОЗИТОРИЙ.git appointment-system
cd appointment-system
```

Или в свою домашнюю папку:

```bash
cd ~
git clone https://github.com/ВАШ_ЛОГИН/РЕПОЗИТОРИЙ.git appointment-system
cd appointment-system
```

Замените `ВАШ_ЛОГИН` и `РЕПОЗИТОРИЙ` на реальные данные репозитория.

---

### 3B. Создание и настройка `.env`

```bash
cp env.example .env
nano .env
```

Заполните переменные:

| Переменная      | Пример                    | Описание                          |
|-----------------|---------------------------|-----------------------------------|
| `DB_NAME`       | `appointment_db`          | Имя базы MySQL                    |
| `DB_USER`       | `appointment_user`        | Пользователь MySQL                |
| `DB_PASSWORD`   | `надёжный_пароль`         | Пароль MySQL                      |
| `DB_HOST`       | `db`                      | Для Docker оставляйте `db`        |
| `DB_PORT`       | `3306`                    | Порт MySQL                        |
| `SECRET_KEY`    | длинная случайная строка  | Секрет Django                     |
| `DEBUG`         | `False`                   | В продакшене всегда `False`       |
| `ALLOWED_HOSTS` | `ваш-домен.ru,127.0.0.1`  | Домен и IP через запятую          |

Сгенерировать `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Сохраните файл (`Ctrl+O`, Enter, `Ctrl+X` в nano).

---

### 4B. Запуск проекта

```bash
docker-compose build --no-cache
docker-compose up -d
```

Проверка:

```bash
docker-compose ps
```

Все сервисы должны быть в состоянии `Up`. Сайт доступен по `http://IP_СЕРВЕРА` или `http://ваш-домен.ru`.

---

### 5B. Обновление проекта из Git

После изменений в репозитории на хостинге:

```bash
cd /opt/appointment-system
git pull origin main
docker-compose up -d --build
```

(или `git pull origin develop`, если деплоите с ветки `develop`).

---

### 6B. Полезные команды

| Действие           | Команда                          |
|--------------------|----------------------------------|
| Остановить         | `docker-compose down`            |
| Перезапустить      | `docker-compose up -d --build`   |
| Логи веб-сервера   | `docker-compose logs -f web`     |
| Логи nginx         | `docker-compose logs -f nginx`   |
| Логи MySQL         | `docker-compose logs -f db`      |
| Статус контейнеров | `docker-compose ps`              |

---

> Если у вас MySQL именно от reg.ru и вы запускаете Docker-контейнеры, `DB_HOST=localhost` внутри контейнера **не сработает** (это будет localhost контейнера). В Docker-варианте используйте MySQL в контейнере (`DB_HOST=db`).

---

## Деплой через GitHub Actions (workflow `deploy.yml`)

При ошибке **"missing server host"** в логе Actions причина — не заданы секреты репозитория. Workflow подставляет их в `appleboy/ssh-action`; если секрет пустой, хост не передаётся.

**Что сделать:** зайти в репозиторий на GitHub → **Settings** → **Secrets and variables** → **Actions** и добавить:

| Секрет        | Описание |
|---------------|----------|
| `VPS_HOST`   | IP или домен сервера (например `123.45.67.89` или `vps.example.com`) |
| `VPS_USER`   | SSH-логин на сервере |
| `VPS_SSH_KEY`| Приватный SSH-ключ (содержимое файла, без пароля) |
| `APP_DIR`    | Путь на сервере до приложения (например `/home/user/appointment-system`) |
| `DB_NAME`    | Имя БД MySQL |
| `DB_USER`    | Пользователь MySQL |
| `DB_PASSWORD`| Пароль MySQL |
| `DB_HOST`    | Хост БД (часто `localhost`) |
| `DB_PORT`    | Порт БД (обычно `3306`) |
| `SECRET_KEY` | Django SECRET_KEY |
| `ALLOWED_HOSTS` | Домен(ы) через запятую |
| `PYTHON_BIN` | (опционально) Путь к Python на сервере, например `/opt/python/python-3.10.1/bin/python` |

После добавления секретов перезапустите failed workflow (Re-run jobs).
