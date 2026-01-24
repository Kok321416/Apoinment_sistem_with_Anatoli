# Запуск проекта на хостинге reg.ru (через Git и консоль)

Проект: Django + MySQL + Nginx в Docker. Деплой через Git (clone/pull) и консоль SSH.

---

## 1. Требования на хостинге

- **VPS** или сервер с SSH (обычный shared-хостинг с одним MySQL не подойдёт — нужен Docker).
- Установлены **Docker** и **Docker Compose**.
- Открыты порты **80** (HTTP) и **22** (SSH).

---

## 2. Клонирование репозитория

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

## 3. Создание и настройка `.env`

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

## 4. Запуск проекта

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

## 5. Обновление проекта из Git

После изменений в репозитории на хостинге:

```bash
cd /opt/appointment-system
git pull origin main
docker-compose up -d --build
```

(или `git pull origin develop`, если деплоите с ветки `develop`).

---

## 6. Полезные команды

| Действие           | Команда                          |
|--------------------|----------------------------------|
| Остановить         | `docker-compose down`            |
| Перезапустить      | `docker-compose up -d --build`   |
| Логи веб-сервера   | `docker-compose logs -f web`     |
| Логи nginx         | `docker-compose logs -f nginx`   |
| Логи MySQL         | `docker-compose logs -f db`      |
| Статус контейнеров | `docker-compose ps`              |

---

## 7. Использование MySQL с reg.ru (без Docker)

Если у вас **отдельный MySQL** от reg.ru (логин, пароль, хост), а приложение запускается **без Docker** (только Python/gunicorn на сервере):

1. В `.env` укажите:
   - `DB_HOST` — хост MySQL (например, `localhost` или выданный reg.ru).
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD` — данные из панели reg.ru.

2. Запускайте Django как обычно (gunicorn, systemd и т.п.), без контейнера `db`.

Текущая конфигурация в репозитории рассчитана на **Docker**: MySQL работает в контейнере `db`, поэтому `DB_HOST=db`.
