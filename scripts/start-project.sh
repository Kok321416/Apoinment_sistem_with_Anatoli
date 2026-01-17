#!/bin/bash
# Скрипт для запуска проекта

set -e

echo "=== Запуск проекта ==="

cd /opt/appointment-system || { echo "❌ Директория /opt/appointment-system не найдена!"; exit 1; }

# 1. Проверка .env
echo "1. Проверка .env файла..."
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "Скопируйте env.example в .env и настройте:"
    echo "  cp env.example .env"
    echo "  nano .env"
    exit 1
fi

# Проверяем наличие домена в ALLOWED_HOSTS
if ! grep -q "yourclients.duckdns.org" .env; then
    echo "⚠ ВНИМАНИЕ: Домен yourclients.duckdns.org не найден в ALLOWED_HOSTS"
    echo "Обновите .env файл:"
    echo "  ALLOWED_HOSTS=185.155.101.22,yourclients.duckdns.org"
    read -p "Продолжить? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. Создание сертификата (если не существует)
echo "2. Проверка SSL сертификата..."
if [ ! -f certbot/conf/live/selfsigned/fullchain.pem ]; then
    echo "Создание самоподписанного сертификата..."
    mkdir -p certbot/conf/live/selfsigned
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout certbot/conf/live/selfsigned/privkey.pem \
      -out certbot/conf/live/selfsigned/fullchain.pem \
      -subj "/C=RU/ST=Moscow/L=Moscow/O=Appointment System/CN=yourclients.duckdns.org" 2>/dev/null
    
    chmod 644 certbot/conf/live/selfsigned/fullchain.pem
    chmod 600 certbot/conf/live/selfsigned/privkey.pem
    echo "✓ Сертификат создан"
else
    echo "✓ Сертификат уже существует"
fi

# 3. Создание директорий
echo "3. Создание директорий..."
mkdir -p certbot/www/.well-known/acme-challenge
chmod -R 755 certbot/www 2>/dev/null || true
echo "✓ Директории готовы"

# 4. Проверка портов
echo "4. Проверка портов..."
if ss -tlnp 2>/dev/null | grep -q ":80 "; then
    echo "⚠ Порт 80 занят. Попытка освободить..."
    fuser -k 80/tcp 2>/dev/null || true
    sleep 2
fi

# 5. Обновление кода
echo "5. Обновление кода из Git..."
git pull origin develop || echo "⚠ Не удалось обновить код (возможно, нет изменений)"

# 6. Сборка и запуск
echo "6. Сборка и запуск контейнеров..."
docker-compose build web
docker-compose up -d

# 7. Ожидание готовности
echo "7. Ожидание готовности сервисов..."
sleep 10

# 8. Проверка статуса
echo ""
echo "=== Статус контейнеров ==="
docker-compose ps

echo ""
echo "=== Проверка работы ==="
echo "Проверка HTTP (локально):"
curl -I http://localhost -H "Host: yourclients.duckdns.org" 2>/dev/null | head -3 || echo "❌ HTTP не работает локально"

echo ""
echo "Проверка логов nginx:"
docker-compose logs nginx | tail -5

echo ""
echo "Проверка логов web:"
docker-compose logs web | tail -5

echo ""
echo "=== Готово ==="
echo ""
echo "Проверьте работу:"
echo "  - HTTP:  curl -I http://yourclients.duckdns.org"
echo "  - Логи:  docker-compose logs -f nginx"
echo ""
