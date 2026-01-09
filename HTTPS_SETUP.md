# Настройка HTTPS для проекта

## Важно: Требования

Для получения SSL сертификата от Let's Encrypt **необходим домен**. Let's Encrypt не выдает сертификаты для IP-адресов.

1. У вас должен быть домен (например: `example.com`)
2. DNS записи должны указывать на ваш VPS IP:
   - A запись: `example.com` → `ваш_VPS_IP`
   - A запись: `www.example.com` → `ваш_VPS_IP` (опционально)

## Шаг 1: Обновление docker-compose.yml и конфигурации

Файлы уже подготовлены:
- ✅ `docker-compose.yml` - добавлен nginx и certbot
- ✅ `nginx/nginx.conf` - основная конфигурация nginx
- ✅ `nginx/conf.d/app.conf` - конфигурация для приложения

## Шаг 2: Настройка переменных окружения

Обновите `.env` файл на сервере:

```bash
cd /opt/appointment-system
nano .env
```

Добавьте или обновите:

```env
# Добавьте домен в ALLOWED_HOSTS
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Включите HTTPS (пока False, включите после получения сертификата)
USE_HTTPS=False
```

## Шаг 3: Создание директорий для сертификатов

```bash
cd /opt/appointment-system
mkdir -p certbot/conf certbot/www
chmod -R 755 certbot
```

## Шаг 4: Первый запуск (без SSL)

Перед получением сертификата нужно запустить nginx для проверки домена:

```bash
cd /opt/appointment-system

# Остановите старые контейнеры
docker-compose down

# Запустите все сервисы
docker-compose up -d

# Проверьте логи nginx
docker-compose logs nginx
```

## Шаг 5: Получение SSL сертификата через Let's Encrypt

### Вариант A: Использование готового скрипта (рекомендуется)

1. Убедитесь, что домен указывает на ваш VPS IP:
   ```bash
   # Проверьте с вашего компьютера
   nslookup your-domain.com
   # или
   dig your-domain.com
   ```

2. Скопируйте скрипт на сервер (если его еще нет):
   ```bash
   # Файл уже должен быть в репозитории: nginx/init-letsencrypt.sh
   ```

3. Сделайте скрипт исполняемым:
   ```bash
   cd /opt/appointment-system
   chmod +x nginx/init-letsencrypt.sh
   ```

4. Запустите скрипт:
   ```bash
   ./nginx/init-letsencrypt.sh your-domain.com your-email@example.com
   ```

   Замените:
   - `your-domain.com` на ваш домен
   - `your-email@example.com` на ваш email (для уведомлений Let's Encrypt)

### Вариант B: Ручная настройка через certbot

1. Временно измените `nginx/conf.d/app.conf` - раскомментируйте HTTP редирект и закомментируйте HTTP доступ (пока не получите сертификат)

2. Запустите certbot:
   ```bash
   docker-compose run --rm certbot certonly --webroot \
     --webroot-path=/var/www/certbot \
     --email your-email@example.com \
     --agree-tos \
     --no-eff-email \
     -d your-domain.com \
     -d www.your-domain.com
   ```

3. Если получили ошибку, проверьте:
   - Домен указывает на ваш IP: `nslookup your-domain.com`
   - Порты 80 и 443 открыты: `ufw allow 80/tcp && ufw allow 443/tcp`
   - nginx запущен: `docker-compose ps`

## Шаг 6: Активация HTTPS в nginx

После успешного получения сертификата:

1. Обновите `nginx/conf.d/app.conf`:
   ```bash
   cd /opt/appointment-system
   nano nginx/conf.d/app.conf
   ```

2. Раскомментируйте HTTPS блок и закомментируйте/измените HTTP блок:
   ```nginx
   # HTTP - редирект на HTTPS
   server {
       listen 80;
       server_name your-domain.com www.your-domain.com;

       location /.well-known/acme-challenge/ {
           root /var/www/certbot;
       }

       # Редирект на HTTPS
       location / {
           return 301 https://$host$request_uri;
       }
   }

   # HTTPS конфигурация
   server {
       listen 443 ssl http2;
       server_name your-domain.com www.your-domain.com;

       ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
       
       include /etc/letsencrypt/options-ssl-nginx.conf;
       ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

       # Остальная конфигурация...
   }
   ```

   Замените `your-domain.com` на ваш домен!

3. Перезапустите nginx:
   ```bash
   docker-compose restart nginx
   # или
   docker-compose exec nginx nginx -s reload
   ```

## Шаг 7: Включение HTTPS в Django

1. Обновите `.env` файл:
   ```bash
   cd /opt/appointment-system
   nano .env
   ```

   Измените:
   ```env
   USE_HTTPS=True
   ```

2. Перезапустите веб-сервис:
   ```bash
   docker-compose restart web
   ```

## Шаг 8: Автоматическое обновление сертификатов

Certbot контейнер автоматически обновляет сертификаты каждые 12 часов. После обновления нужно перезагрузить nginx:

```bash
# Добавьте в cron или используйте готовый скрипт
docker-compose exec nginx nginx -s reload
```

Или создайте скрипт обновления:

```bash
cat > /opt/appointment-system/renew-cert.sh << 'EOF'
#!/bin/bash
cd /opt/appointment-system
docker-compose run --rm certbot renew
docker-compose exec nginx nginx -s reload
EOF

chmod +x /opt/appointment-system/renew-cert.sh

# Добавьте в cron (запуск каждые 12 часов)
(crontab -l 2>/dev/null; echo "0 */12 * * * /opt/appointment-system/renew-cert.sh >> /var/log/certbot-renew.log 2>&1") | crontab -
```

## Проверка работы HTTPS

1. Проверьте в браузере: `https://your-domain.com`
2. Проверьте редирект с HTTP: `http://your-domain.com` (должен редиректить на HTTPS)
3. Проверьте SSL сертификат: [SSL Labs](https://www.ssllabs.com/ssltest/)

## Решение проблем

### Ошибка: "Failed to obtain certificate"

**Причины:**
1. Домен не указывает на ваш IP
2. Порты 80/443 закрыты
3. nginx не запущен

**Решение:**
```bash
# Проверьте DNS
nslookup your-domain.com

# Проверьте порты
ufw status
ufw allow 80/tcp
ufw allow 443/tcp

# Проверьте nginx
docker-compose ps nginx
docker-compose logs nginx
```

### Ошибка: "Connection refused"

**Решение:**
```bash
# Проверьте, что nginx слушает на портах 80 и 443
docker-compose exec nginx netstat -tlnp

# Перезапустите nginx
docker-compose restart nginx
```

### Ошибка: "SSL certificate problem"

**Решение:**
```bash
# Проверьте наличие сертификата
docker-compose exec certbot ls -la /etc/letsencrypt/live/your-domain.com/

# Пересоздайте сертификат
docker-compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  --force-renewal \
  -d your-domain.com
```

### Сертификат истекает

**Решение:**
Сертификаты автоматически обновляются через certbot контейнер. Для ручного обновления:

```bash
docker-compose run --rm certbot renew
docker-compose exec nginx nginx -s reload
```

## Альтернатива: Самоподписанный сертификат (только для тестирования)

⚠️ **ВНИМАНИЕ**: Самоподписанные сертификаты показывают предупреждение в браузере и **НЕ ПОДХОДЯТ для продакшена**.

Если вам нужен самоподписанный сертификат для тестирования:

```bash
cd /opt/appointment-system
mkdir -p certbot/conf/live/your-domain.com

# Создайте самоподписанный сертификат
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certbot/conf/live/your-domain.com/privkey.pem \
  -out certbot/conf/live/your-domain.com/fullchain.pem \
  -subj "/CN=your-domain.com"
```

Затем обновите `nginx/conf.d/app.conf` для использования этого сертификата.

## Обновление GitHub Actions для HTTPS

Если используете GitHub Actions для деплоя, обновите `.github/workflows/deploy.yml` чтобы после деплоя перезапускать nginx:

```yaml
- name: Restart nginx
  run: |
    cd /opt/appointment-system
    docker-compose restart nginx
```

## Дополнительные настройки безопасности

После настройки HTTPS рекомендуется:

1. Настроить файрвол:
   ```bash
   ufw allow 22/tcp   # SSH
   ufw allow 80/tcp   # HTTP (для редиректа)
   ufw allow 443/tcp  # HTTPS
   ufw enable
   ```

2. Отключить прямой доступ к порту 8000 (gunicorn):
   - Убедитесь, что в `docker-compose.yml` используется `expose: 8000` вместо `ports: "8000:8000"` (уже сделано)
   - Доступ к приложению должен быть только через nginx (порты 80/443)

3. Настроить rate limiting в nginx (добавьте в `nginx/conf.d/app.conf`):
   ```nginx
   limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
   
   location / {
       limit_req zone=api_limit burst=20 nodelay;
       # ...
   }
   ```
