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

- Django 4.2 (LTS) — совместимо с Python 3.10.x (reg.ru)
- Django REST Framework
- MySQL
- Docker & Docker Compose
- Gunicorn, Nginx
- WhiteNoise (для статических файлов)

## Деплой на хостинг (reg.ru и др.)

Инструкция по запуску через Git и консоль: [DEPLOY_REGRU.md](DEPLOY_REGRU.md)

## Быстрый старт

```bash
# Установка зависимостей
cd appoinment_sistem
pip install -r ../requirements.txt

# Миграции
python manage.py migrate

# Создание суперпользователя
python manage.py createsuperuser

# Запуск сервера
python manage.py runserver
```

Приложение будет доступно по адресу: http://127.0.0.1:8000

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
└── requirements.txt        # Python зависимости
```

## Связь HTML с бэкендом

Подробное описание того, как HTML шаблоны связаны с Django бэкендом, см. в файле [HTML_BACKEND_CONNECTION.md](HTML_BACKEND_CONNECTION.md)
