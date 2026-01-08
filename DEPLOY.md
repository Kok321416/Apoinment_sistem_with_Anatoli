# Инструкция по деплою на VPS

## Пошаговая инструкция

### Этап 1: Подготовка GitHub Secrets

1. Откройте репозиторий на GitHub
2. Перейдите: Settings → Secrets and variables → Actions
3. Добавьте следующие секреты:

#### VPS_HOST
- **Что это**: IP адрес вашего VPS сервера
- **Как получить**: Из панели управления хостингом или командой `curl ifconfig.me` на сервере
- **Пример**: `123.45.67.89`

#### VPS_USER
- **Что это**: Пользователь для SSH подключения
- **Обычно**: `root`
- **Пример**: `root`

#### VPS_SSH_KEY
- **Что это**: Приватный SSH ключ для доступа к серверу
- **Как создать**:
  ```bash
  ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
  # Сохраните в ~/.ssh/vps_deploy_key (без пароля!)
  ```
- **Как скопировать**: 
  ```bash
  # Windows
  Get-Content ~/.ssh/vps_deploy_key
  
  # Linux/Mac
  cat ~/.ssh/vps_deploy_key
  ```
- **Важно**: Скопируйте ВЕСЬ текст, включая `-----BEGIN RSA PRIVATE KEY-----` и `-----END RSA PRIVATE KEY-----`

#### DB_PASSWORD
- **Что это**: Пароль для базы данных PostgreSQL
- **Как создать**: Используйте генератор паролей или команду:
  ```bash
  # Windows PowerShell
  -join ((48..57) + (65..90) + (97..122) + (33..47) | Get-Random -Count 24 | ForEach-Object {[char]$_})
  
  # Linux/Mac
  openssl rand -base64 24
  ```
- **Пример**: `MySecurePass123!`

#### SECRET_KEY
- **Что это**: Секретный ключ Django
- **Как создать**:
  ```python
  python
  from django.core.management.utils import get_random_secret_key
  print(get_random_secret_key())
  ```
- **Или онлайн**: https://djecrety.ir/

#### ALLOWED_HOSTS
- **Что это**: Домен или IP адрес вашего сервера
- **Формат**: `yourdomain.com,123.45.67.89` (через запятую, без пробелов)
- **Если только IP**: `123.45.67.89`
- **Если домен**: `yourdomain.com,www.yourdomain.com`

#### PGADMIN_PASSWORD
- **Что это**: Пароль для входа в pgAdmin (веб-интерфейс БД)
- **Как создать**: Аналогично DB_PASSWORD
- **Пример**: `AdminPass123!`

### Этап 2: Настройка VPS сервера

#### Шаг 1: Подключитесь к серверу
```bash
ssh root@YOUR_VPS_IP
```

#### Шаг 2: Установите Docker
```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установка Docker Compose
apt install docker-compose -y

# Проверка
docker --version
docker-compose --version
```

#### Шаг 3: Настройте SSH ключ
На вашем компьютере:
```bash
# Скопируйте публичный ключ на сервер
ssh-copy-id -i ~/.ssh/vps_deploy_key.pub root@YOUR_VPS_IP
```

Или вручную на сервере:
```bash
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# Вставьте публичный ключ (из ~/.ssh/vps_deploy_key.pub)
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

#### Шаг 4: Создайте директорию проекта
```bash
mkdir -p /opt/appointment-system
cd /opt/appointment-system
```

### Этап 3: Первый деплой

#### Вариант A: Автоматический (через GitHub Actions)

1. Убедитесь, что все секреты добавлены в GitHub
2. Сделайте push в ветку `main`:
   ```bash
   git add .
   git commit -m "Initial deployment setup"
   git push origin main
   ```

3. GitHub Actions автоматически:
   - Создаст `.env` файл на сервере
   - Склонирует репозиторий
   - Запустит Docker Compose
   - Применит миграции

4. Проверьте статус деплоя:
   - GitHub → Actions → выберите последний workflow

#### Вариант B: Ручной деплой

1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git /opt/appointment-system
   cd /opt/appointment-system
   ```

2. Создайте `.env` файл:
   ```bash
   nano .env
   ```
   
   Вставьте (замените значения на реальные):
   ```env
   DB_NAME=appointment_db
   DB_USER=appointment_user
   DB_PASSWORD=ваш_пароль_из_github_secrets
   DB_HOST=db
   DB_PORT=5432
   SECRET_KEY=ваш_secret_key_из_github_secrets
   DEBUG=False
   ALLOWED_HOSTS=ваш_ip_или_домен
   PGADMIN_DEFAULT_EMAIL=admin@admin.com
   PGADMIN_PASSWORD=ваш_пароль_для_pgadmin
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

### Этап 4: Проверка работы

1. **Проверьте веб-приложение**:
   ```
   http://YOUR_VPS_IP:8000
   ```

2. **Проверьте pgAdmin**:
   ```
   http://YOUR_VPS_IP:5050
   ```
   - Email: `admin@admin.com`
   - Password: из `PGADMIN_PASSWORD`
   
   Затем добавьте сервер PostgreSQL:
   - Host: `db`
   - Port: `5432`
   - Database: `appointment_db`
   - Username: `appointment_user`
   - Password: из `DB_PASSWORD`

3. **Проверьте статус контейнеров**:
   ```bash
   docker-compose ps
   ```
   
   Должны быть запущены: `db`, `web`, `pgadmin`

### Этап 5: Настройка Nginx (опционально)

1. Установите Nginx:
   ```bash
   apt install nginx -y
   ```

2. Создайте конфиг:
   ```bash
   nano /etc/nginx/sites-available/appointment
   ```
   
   Вставьте:
   ```nginx
   server {
       listen 80;
       server_name YOUR_DOMAIN_OR_IP;

       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static/ {
           alias /opt/appointment-system/staticfiles/;
       }
   }
   ```

3. Активируйте:
   ```bash
   ln -s /etc/nginx/sites-available/appointment /etc/nginx/sites-enabled/
   nginx -t
   systemctl reload nginx
   ```

## Полезные команды

### Просмотр логов
```bash
docker-compose logs -f web
docker-compose logs -f db
```

### Перезапуск
```bash
docker-compose restart web
```

### Обновление кода
```bash
cd /opt/appointment-system
git pull
docker-compose down
docker-compose build
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py collectstatic --noinput
```

### Бэкап базы данных
```bash
docker-compose exec db pg_dump -U appointment_user appointment_db > backup_$(date +%Y%m%d).sql
```

### Восстановление из бэкапа
```bash
docker-compose exec -T db psql -U appointment_user appointment_db < backup_20250108.sql
```

## Решение проблем

### Контейнеры не запускаются
```bash
docker-compose logs
docker-compose ps
```

### Ошибка подключения к БД
- Проверьте `.env` файл
- Убедитесь, что контейнер `db` запущен: `docker-compose ps`
- Проверьте логи: `docker-compose logs db`

### Статические файлы не загружаются
```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### Миграции не применяются
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py makemigrations
```

## Безопасность

- ✅ Не коммитьте `.env` файл в Git
- ✅ Используйте сильные пароли
- ✅ Настройте SSL (Let's Encrypt) для HTTPS
- ✅ Регулярно обновляйте систему: `apt update && apt upgrade`
- ✅ Настройте файрвол (UFW):
  ```bash
  ufw allow 22/tcp   # SSH
  ufw allow 80/tcp   # HTTP
  ufw allow 443/tcp  # HTTPS
  ufw enable
  ```

## Поддержка

При возникновении проблем проверьте:
1. Логи Docker: `docker-compose logs`
2. Логи Django: `docker-compose exec web python manage.py check`
3. Статус контейнеров: `docker-compose ps`
4. GitHub Actions: GitHub → Actions
