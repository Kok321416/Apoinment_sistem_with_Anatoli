# 🚨 Быстрое решение проблемы "сайт не грузится"

## Вариант 1: Проверка основных проблем (выполните на сервере)

```bash
cd /opt/appointment-system

# 1. Проверьте статус всех контейнеров
docker-compose ps

# 2. Проверьте логи nginx
docker-compose logs nginx

# 3. Проверьте логи web
docker-compose logs web

# 4. Проверьте, что порты не заняты
ss -tlnp | grep -E ':(80|443)'

# 5. Проверьте, запущен ли старый nginx на хосте
systemctl status nginx 2>/dev/null || echo "nginx не установлен на хосте"

# 6. Проверьте сеть Docker
docker network ls
```

## Вариант 2: Временное отключение HTTPS (если нужно быстро запустить)

Если проблема критична и нужно срочно запустить сайт, временно отключите HTTPS:

### 1. Измените nginx конфигурацию

```bash
cd /opt/appointment-system
nano nginx/conf.d/app.conf
```

Закомментируйте HTTPS блок (строки 17-61) и раскомментируйте HTTP:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /static/ {
        alias /app/appoinment_sistem/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /app/appoinment_sistem/media/;
        expires 30d;
        add_header Cache-Control "public";
    }
}
```

### 2. Обновите .env

```bash
nano .env
```

Измените:
```env
USE_HTTPS=False
```

### 3. Перезапустите

```bash
docker-compose restart nginx web
```

## Вариант 3: Полная переустановка HTTPS

```bash
cd /opt/appointment-system

# Остановите все
docker-compose down

# Удалите старые сертификаты
rm -rf certbot/conf/live/selfsigned

# Проверьте конфигурацию docker-compose
docker-compose config

# Пересоберите nginx
docker-compose build --no-cache nginx

# Запустите
docker-compose up -d

# Подождите 10 секунд
sleep 10

# Проверьте логи
docker-compose logs nginx | tail -50
docker-compose logs web | tail -50
```

## Вариант 4: Проверка подключения web контейнера

```bash
# Проверьте, что web контейнер доступен
docker-compose exec nginx ping -c 3 web

# Проверьте, что web отвечает на порту 8000
docker-compose exec nginx wget -O- http://web:8000 2>&1 | head -20
```

## Вариант 5: Запуск без nginx (для проверки Django)

Временно откройте порт 8000 напрямую:

```bash
cd /opt/appointment-system

# Измените docker-compose.yml - в секции web замените expose на ports
# expose:
#   - "8000"
# на:
# ports:
#   - "8000:8000"

nano docker-compose.yml

# Перезапустите
docker-compose up -d web

# Проверьте http://YOUR_VPS_IP:8000
```

---

**Пришлите результаты команды `docker-compose ps` и `docker-compose logs nginx | tail -30`, и я точно скажу, в чем проблема!**
