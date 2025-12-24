# План разработки системы онлайн записи (Django REST Framework)

## Архитектура проекта

```
project/
├── appointment_system/       # Django проект
│   ├── manage.py
│   ├── appointment_system/   # Главный модуль проекта
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── accounts/             # Приложение для авторизации
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── admin.py
│   ├── services/             # Приложение для услуг
│   ├── calendars/            # Приложение для календарей
│   ├── bookings/             # Приложение для записей
│   ├── integrations/         # Интеграции с календарями
│   ├── telegram_bot/         # Telegram бот
│   └── static/               # Статические файлы
├── frontend/                 # HTML/CSS/JS (Анатолий)
│   ├── specialist/           # Личный кабинет специалиста
│   ├── client/               # Публичная страница клиента
│   └── assets/
└── requirements.txt
```

## Этап 1: Подготовка инфраструктуры (Неделя 1)

### Артем - Бэкенд инфраструктура

- [ ] Установка Django и Django REST Framework
- [ ] Создание Django проекта: `django-admin startproject appointment_system`
- [ ] Подключение PostgreSQL в settings.py
- [ ] Настройка переменных окружения (.env)
- [ ] Создание приложений Django (apps)
- [ ] Настройка базовой структуры проекта

**Команды для создания проекта:**

```bash
pip install django djangorestframework python-dotenv psycopg2-binary
django-admin startproject appointment_system
cd appointment_system
python manage.py startapp accounts
python manage.py startapp services
python manage.py startapp calendars
python manage.py startapp bookings
python manage.py startapp integrations
```

**Файлы для настройки:**

- `appointment_system/settings.py` - настройки Django проекта
- `appointment_system/urls.py` - главный urls.py
- `.env` - переменные окружения (DATABASE_URL, SECRET_KEY)

**Технологии:**

- Django 4.2+ (веб-фреймворк)
- Django REST Framework (API)
- PostgreSQL (база данных)
- psycopg2-binary (драйвер PostgreSQL)
- djangorestframework-simplejwt (JWT токены)
- django-cors-headers (CORS)
- python-telegram-bot (Telegram бот)
- google-api-python-client (Google Calendar API)
- python-dotenv (конфигурация)
- phonenumbers (валидация телефонов)

### Анатолий - Фронтенд инфраструктура

- [ ] Структура папок фронтенда
- [ ] Настройка базовых HTML шаблонов
- [ ] CSS переменные и общие стили
- [ ] JS модули для работы с API
- [ ] Базовая система навигации

**Файлы для создания:**

- `frontend/index.html` - главная страница
- `frontend/assets/css/main.css` - основные стили
- `frontend/assets/js/api.js` - функции для API запросов
- `frontend/assets/js/utils.js` - утилиты

## Этап 2: Авторизация и аутентификация (Неделя 1-2)

### Артем - Бэкенд авторизация

- [ ] Модель CustomUser (специалист) - расширение Django User
- [ ] Эндпоинт регистрации по телефону и почте
- [ ] SMS верификация номера телефона (опционально)
- [ ] Валидация номера телефона и email
- [ ] JWT токены через djangorestframework-simplejwt
- [ ] OAuth интеграция с Google (как способ входа/регистрации)
- [ ] OAuth интеграция с Yandex (как способ входа/регистрации)
- [ ] Permissions для защиты эндпоинтов

**API эндпоинты:**

- `POST /api/auth/register/` - регистрация (телефон + email)
- `POST /api/auth/verify-phone/` - верификация телефона SMS кодом (опционально)
- `POST /api/auth/token/` - получение JWT токена
- `POST /api/auth/token/refresh/` - обновление токена
- `GET /api/auth/oauth/google/` - инициализация OAuth Google
- `GET /api/auth/oauth/google/callback/` - callback OAuth Google
- `GET /api/auth/oauth/yandex/` - инициализация OAuth Yandex
- `GET /api/auth/oauth/yandex/callback/` - callback OAuth Yandex
- `GET /api/auth/me/` - текущий пользователь

**Модели БД:**

- CustomUser (id, phone, email, name, is_phone_verified, oauth_provider, oauth_id, created_at)

**Примечание:** При OAuth входе система проверяет наличие пользователя по email или создает нового.

### Анатолий - Фронтенд авторизация

- [ ] Страница регистрации (register.html)
  - Поле для номера телефона (с маской ввода)
  - Поле для email
  - Валидация телефона и email на клиенте
  - Кнопка регистрации

- [ ] Страница верификации телефона (verify-phone.html, опционально)
  - Поле для ввода SMS кода
  - Таймер повторной отправки кода

- [ ] Главная страница входа (login.html)
  - Кнопка "Войти через Google"
  - Кнопка "Войти через Yandex"
  - Ссылка на регистрацию

- [ ] Обработка OAuth callback'ов

- [ ] Хранение JWT токена (localStorage)

- [ ] Редирект на защищенные страницы

- [ ] Обработка ошибок авторизации

## Этап 3: Модели данных и услуги (Неделя 2)

### Артем - Бэкенд модели

- [ ] Модель Service (услуга)
  - Поля: id, specialist (ForeignKey), name, description, duration_minutes, price (опционально), is_active

- [ ] Модель Calendar (календарь специалиста)
  - Поля: id, specialist (ForeignKey), name, work_start_time, work_end_time, buffer_before_minutes, buffer_after_minutes, max_bookings_per_day

- [ ] Модель Booking (запись клиента)
  - Поля: id, calendar (ForeignKey), service (ForeignKey), client_name, client_phone, client_email, tg_username (обязательно), tg_chat_id (опционально), start_datetime, end_datetime, status, booking_token (UUID), created_at

- [ ] Связи между моделями (Foreign Keys)

- [ ] Миграции БД: `python manage.py makemigrations` и `python manage.py migrate`

**API эндпоинты для услуг:**

- `GET /api/services/` - список услуг специалиста
- `POST /api/services/` - создание услуги
- `GET /api/services/{id}/` - детали услуги
- `PUT /api/services/{id}/` - обновление услуги
- `DELETE /api/services/{id}/` - удаление услуги

**API эндпоинты для календарей:**

- `GET /api/calendars/` - список календарей специалиста
- `POST /api/calendars/` - создание календаря
- `GET /api/calendars/{id}/` - детали календаря
- `PUT /api/calendars/{id}/` - обновление календаря
- `DELETE /api/calendars/{id}/` - удаление календаря

### Анатолий - Фронтенд услуги и календари

- [ ] Страница управления услугами (services.html)

- [ ] Форма создания/редактирования услуги

- [ ] Страница управления календарями (calendars.html)

- [ ] Форма создания/редактирования календаря

- [ ] Валидация форм на клиенте

- [ ] Отображение списков услуг и календарей

## Этап 4: Логика календаря и записи (Неделя 3)

### Артем - Бэкенд логика записи

- [ ] Сервис для расчета доступных слотов (отдельный файл services.py)

- [ ] Проверка пересечений временных окон

- [ ] Учет буферного времени (до/после услуги)

- [ ] Ограничение на количество услуг в день

- [ ] Эндпоинт получения доступных слотов

- [ ] Эндпоинт создания записи (booking)

**Логика расчета слотов:**

- Получение рабочего времени календаря
- Вычитание уже существующих записей
- Применение буферного времени
- Проверка лимита на день

**API эндпоинты:**

- `GET /api/calendars/{id}/available-slots/` - доступные слоты (дата, время)
  - Параметры: calendar_id, service_id, date (YYYY-MM-DD)
  - Возвращает: массив доступных временных слотов

- `POST /api/bookings/` - создание записи
  - Тело запроса: calendar_id, service_id, client_name, client_phone, client_email (опционально), tg_username (обязательно), start_datetime
  - Валидация обязательности tg_username
  - Генерация booking_token (UUID)

- `GET /api/bookings/` - список записей специалиста

- `PUT /api/bookings/{id}/` - обновление записи (отмена)

### Анатолий - Фронтенд календарь записи

- [ ] Календарный вид (выбор даты)

- [ ] Отображение доступных слотов

- [ ] Форма записи клиента:
  - Имя (обязательно)
  - Телефон (обязательно)
  - Email (опционально)
  - Telegram username/номер (обязательно, с валидацией формата @username)

- [ ] Валидация данных клиента (особенно Telegram)

- [ ] Подтверждение записи

- [ ] Отображение успешной записи с ссылкой/данными и инструкцией по подключению к Telegram боту

## Этап 5: Личный кабинет специалиста (Неделя 3-4)

### Артем - Бэкенд личный кабинет

- [ ] Эндпоинт статистики специалиста

- [ ] Эндпоинт ближайших записей

- [ ] Эндпоинт отмены записи

- [ ] Фильтры для записей (по дате, статусу, услуге) через Django Filter

**API эндпоинты:**

- `GET /api/dashboard/stats/` - статистика (количество записей, доход, загруженность)

- `GET /api/bookings/upcoming/` - ближайшие записи

- `GET /api/bookings/?status=active&date_from=...` - фильтрованные записи

**Статистика включает:**

- Общее количество записей
- Количество предстоящих записей
- Доход (если есть цена услуг)
- Загруженность календарей (процент занятого времени)

### Анатолий - Фронтенд личный кабинет

- [ ] Главная страница специалиста (dashboard.html)

- [ ] Блоки статистики (карточки с цифрами)

- [ ] Список ближайших записей

- [ ] График загруженности (если нужен)

- [ ] Навигация между разделами (услуги, календари, записи)

- [ ] Адаптивный дизайн

## Этап 6: Публичная страница клиента (Неделя 4)

### Артем - Бэкенд публичная часть

- [ ] Эндпоинт публичной информации о записи

- [ ] Генерация уникальной ссылки для записи (booking_token)

- [ ] Публичный эндпоинт без авторизации (permissions.AllowAny)

- [ ] Валидация доступа к записи

**API эндпоинты:**

- `GET /api/public/bookings/{booking_token}/` - информация о записи (публичный доступ)
- Токен генерируется при создании записи (UUID)

### Анатолий - Фронтенд клиентская страница

- [ ] Публичная страница записи (booking-info.html)

- [ ] Отображение информации: дата, время, услуга, специалист

- [ ] Отображение места проведения (если указано)

- [ ] Информация для связи

- [ ] Кнопка отмены записи (опционально)

## Этап 7: Telegram бот (Неделя 5)

### Артем - Telegram бот

- [ ] Настройка бота (python-telegram-bot)

- [ ] Обработка команд бота

- [ ] Отправка напоминаний о записях

- [ ] Интеграция с Django БД (использование Django ORM)

- [ ] Планировщик для напоминаний (Celery или django-crontab)

- [ ] Логика поиска клиента по Telegram username при первом сообщении

- [ ] Сохранение tg_chat_id при первом контакте клиента с ботом

- [ ] Связывание tg_chat_id с записью (booking) по username

**Функционал бота:**

- Команда `/start` - приветствие и инструкция
- При первом сообщении: поиск записей по username, сохранение chat_id
- Отправка напоминания за N часов до записи (настраивается)
- Информация о предстоящей записи (дата, время, услуга, специалист)
- Возможность отменить запись через бота
- Уведомление клиента сразу после записи с подтверждением данных

**Структура:**

- `telegram_bot/bot.py` - запуск бота
- `telegram_bot/handlers.py` - обработчики команд
- `telegram_bot/tasks.py` - Celery задачи для напоминаний

### Анатолий - Интеграция с фронтендом

- [ ] Информация в форме записи о необходимости указать Telegram для получения уведомлений

- [ ] Инструкция для клиента после записи:
  - Как найти бота в Telegram
  - Как подключиться к боту
  - Что делать при проблемах с получением уведомлений

## Этап 8: Интеграции с календарями (Неделя 6)

### Артем - Бэкенд интеграции

- [ ] Google Calendar API интеграция
  - Аутентификация через OAuth
  - Создание событий в календаре при записи
  - Обновление событий при изменении
  - Синхронизация существующих событий

- [ ] Yandex Calendar API интеграция
  - Аутентификация через OAuth
  - Создание/обновление событий

- [ ] Настройки интеграций в профиле специалиста

**Модели:**

- CalendarIntegration (id, specialist (ForeignKey), provider, access_token, refresh_token, calendar_id)

**API эндпоинты:**

- `POST /api/integrations/google/connect/` - подключение Google Calendar
- `POST /api/integrations/yandex/connect/` - подключение Yandex Calendar
- `POST /api/integrations/{id}/sync/` - синхронизация событий
- `DELETE /api/integrations/{id}/` - отключение интеграции

### Анатолий - Фронтенд интеграции

- [ ] Страница настроек интеграций (integrations.html)

- [ ] Кнопки подключения Google/Yandex

- [ ] Статус подключенных интеграций

- [ ] Кнопка отключения интеграции

- [ ] Настройки синхронизации

## Этап 9: Финальная доработка и тестирование (Неделя 7)

### Артем - Бэкенд доработки

- [ ] Обработка ошибок и валидация (DRF exceptions)

- [ ] Логирование (Django logging)

- [ ] Тесты API (Django TestCase)

- [ ] Оптимизация запросов к БД (select_related, prefetch_related)

- [ ] Документация API (DRF автоматическая документация или drf-yasg)

- [ ] Настройка CORS для фронтенда (django-cors-headers)

### Анатолий - Фронтенд доработки

- [ ] Обработка всех ошибок API

- [ ] Загрузочные индикаторы

- [ ] Улучшение UX (анимации, переходы)

- [ ] Адаптивность под мобильные устройства

- [ ] Оптимизация производительности

- [ ] Финальная полировка дизайна

## Технические детали

### Бэкенд стек (Артем)

- Django 4.2+ (веб-фреймворк)
- Django REST Framework (API)
- Django ORM (работа с БД)
- PostgreSQL (база данных)
- psycopg2-binary (драйвер PostgreSQL)
- djangorestframework-simplejwt (JWT токены)
- django-cors-headers (CORS)
- python-telegram-bot (Telegram бот)
- Celery (планировщик задач, опционально)
- django-crontab (альтернатива Celery для простых задач)
- google-api-python-client (Google Calendar API)
- python-dotenv (конфигурация)
- phonenumbers (валидация телефонов)
- django-filter (фильтрация)

### Фронтенд стек (Анатолий)

- Vanilla JavaScript (ES6+)
- CSS3 (Flexbox/Grid)
- Fetch API для запросов
- Возможно: небольшая библиотека для календаря (опционально)

### База данных (PostgreSQL)

**Таблицы:**

- accounts_customuser (специалисты)
- services_service (услуги)
- calendars_calendar (календари)
- bookings_booking (записи)
- integrations_calendarintegration (интеграции с календарями)

## Взаимодействие разработчиков

1. **API контракт**: Артем предоставляет API документацию (DRF автоматически генерирует /api/)
2. **Моковые данные**: Анатолий может начать верстку с моковыми данными
3. **Интеграция**: После готовности бэкенда - подключение реального API
4. **Тестирование**: Совместное тестирование интеграции фронт-бэк

## Рекомендации для Артема (джуниор)

1. Начни с изучения Django документации (официальный туториал)
2. Освой Django ORM и работу с моделями
3. Изучи Django REST Framework
4. Постепенно добавляй функционал, тестируя каждый шаг
5. Используй автоматическую документацию DRF (/api/)

## Приоритеты разработки

**Критичный путь:**

1. Инфраструктура → Авторизация → Модели → Логика записи → Личный кабинет

**Параллельно можно разрабатывать:**

- Фронтенд верстка (на моковых данных)
- Telegram бот (после готовности модели Booking)

**После базового функционала:**

- Интеграции с календарями
- Дополнительная статистика

