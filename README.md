# Система онлайн записи консультантов

Django приложение для управления записями на консультации.

## Возможности

- Регистрация и авторизация консультантов
- Управление календарями и временными окнами
- Создание и управление услугами
- Публичная страница для записи клиентов
- Управление записями (бронированиями)
- API для интеграций

## Технологии

- Django 6.0
- Django REST Framework
- PostgreSQL
- Docker & Docker Compose
- Gunicorn
- WhiteNoise (для статических файлов)

## Локальная разработка

### Требования

- Python 3.11+
- PostgreSQL (или SQLite для разработки)

### Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd Apoinment_sistem_with_Anatoli
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
cd appoinment_sistem
pip install -r ../requirements.txt
```

4. Примените миграции:
```bash
python manage.py migrate
```

5. Создайте суперпользователя:
```bash
python manage.py createsuperuser
```

6. Запустите сервер:
```bash
python manage.py runserver
```

Приложение будет доступно по адресу: http://127.0.0.1:8000

## Запуск тестов

```bash
cd appoinment_sistem
python manage.py test consultant_menu
```

## Деплой на VPS

### Подготовка

1. Настройте GitHub Secrets:
   - `VPS_HOST` - IP адрес вашего VPS
   - `VPS_USER` - пользователь SSH (обычно `root`)
   - `VPS_SSH_KEY` - приватный SSH ключ
   - `DB_PASSWORD` - пароль для PostgreSQL
   - `SECRET_KEY` - секретный ключ Django
   - `ALLOWED_HOSTS` - домен или IP адрес
   - `PGADMIN_PASSWORD` - пароль для pgAdmin

2. На VPS сервере установите Docker:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt install docker-compose -y
```

3. Создайте директорию проекта:
```bash
mkdir -p /opt/appointment-system
cd /opt/appointment-system
```

### Автоматический деплой

При каждом push в ветку `main` или `master` GitHub Actions автоматически:
1. Создаст `.env` файл из секретов
2. Обновит код на сервере
3. Пересоберет Docker контейнеры
4. Применит миграции
5. Соберет статические файлы

### Ручной деплой

1. Склонируйте репозиторий на сервер:
```bash
git clone <repository-url> /opt/appointment-system
cd /opt/appointment-system
```

2. Создайте `.env` файл (скопируйте из `env.example` и заполните):
```bash
cp env.example .env
nano .env
```

3. Запустите Docker Compose:
```bash
docker-compose up -d
```

4. Примените миграции:
```bash
docker-compose exec web python manage.py migrate
```

5. Создайте суперпользователя:
```bash
docker-compose exec web python manage.py createsuperuser
```

### Доступ к приложению

- Веб-приложение: http://YOUR_VPS_IP:8000
- pgAdmin (управление БД): http://YOUR_VPS_IP:5050
  - Email: `admin@admin.com`
  - Password: из `PGADMIN_PASSWORD`

### Полезные команды

```bash
# Просмотр логов
docker-compose logs -f web

# Перезапуск
docker-compose restart web

# Остановка
docker-compose down

# Обновление кода
git pull
docker-compose up -d --build
```

## Структура проекта

```
appoinment_sistem/
├── appoinment_sistem/      # Настройки проекта
│   ├── settings.py         # Конфигурация Django
│   ├── urls.py             # URL маршруты
│   └── wsgi.py             # WSGI конфигурация
├── consultant_menu/        # Основное приложение
│   ├── models.py           # Модели данных
│   ├── views.py            # Представления
│   ├── templates/          # HTML шаблоны
│   ├── static/             # Статические файлы (CSS, JS)
│   └── tests.py            # Тесты
├── Dockerfile              # Конфигурация Docker образа
├── docker-compose.yml      # Конфигурация Docker Compose
├── requirements.txt        # Python зависимости
└── .github/
    └── workflows/
        └── deploy.yml      # GitHub Actions workflow
```

## Бэкапы базы данных

Бэкапы создаются автоматически в директории `backups/` на сервере.

Для ручного бэкапа:
```bash
docker-compose exec db pg_dump -U appointment_user appointment_db > backup_$(date +%Y%m%d).sql
```

Для восстановления:
```bash
docker-compose exec -T db psql -U appointment_user appointment_db < backup_20250108.sql
```

## Лицензия

Проект создан для внутреннего использования.
