# 🔄 Полная переустановка с HTTPS и доменом - Пошаговая инструкция

## Шаг 1: Полная очистка Docker

```bash
cd /opt/appointment-system

# 1. Остановите и удалите ВСЕ контейнеры и volumes
docker-compose down -v

# 2. Удалите все контейнеры проекта вручную
docker ps -a | grep appointment
docker rm -f $(docker ps -aq) 2>/dev/null || true

# 3. Остановите все процессы на портах 80 и 443
fuser -k 80/tcp 2>/dev/null || true
fuser -k 443/tcp 2>/dev/null || true
pkill -f "docker-proxy" 2>/dev/null || true

# 4. Удалите все сети проекта
docker network prune -f

# 5. Перезапустите Docker
systemctl restart docker
sleep 5

# 6. Проверьте, что порты свободны
ss -tlnp | grep -E ':(80|443)'
# Должно быть пусто
```

## Шаг 2: Обновление кода

```bash
cd /opt/appointment-system
git pull origin develop

# Проверьте наличие файлов
ls -la docker-compose.yml
ls -la nginx/conf.d/app.conf
```

## Шаг 3: Подготовка .env

```bash
nano .env
```

Убедитесь, что там:
```env
ALLOWED_HOSTS=yourclients.duckdns.org
USE_HTTPS=False  # Пока False, включим после получения сертификата
```

## Шаг 4: Подготовка директорий

```bash
# Создайте директории для certbot
mkdir -p certbot/www/.well-known/acme-challenge
mkdir -p certbot/conf
chmod -R 755 certbot/www
```

## Шаг 5: Первый запуск (только HTTP, для получения сертификата)

```bash
# Запустите все сервисы
docker-compose up -d

# Проверьте статус
docker-compose ps

# Проверьте логи nginx
docker-compose logs nginx | tail -20

# Проверьте доступность HTTP
curl -I http://yourclients.duckdns.org
```

## Шаг 6: Получение Let's Encrypt сертификата

```bash
# Остановите nginx временно
docker-compose stop nginx

# Получите сертификат в standalone режиме
docker-compose run --rm --service-ports certbot certonly --standalone \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d yourclients.duckdns.org

# Если успешно - продолжаем. Если ошибка - скажите.
```

## Шаг 7: Обновление конфигурации nginx для HTTPS

После получения сертификата обновим nginx конфигурацию.

## Шаг 8: Включение HTTPS

Обновим .env и перезапустим.
