#!/bin/bash
# Полная переустановка с HTTPS

set -e

echo "=== Полная переустановка системы ==="

cd /opt/appointment-system || { echo "Директория /opt/appointment-system не найдена!"; exit 1; }

# 1. Создаем самоподписанный сертификат
echo "1. Создание самоподписанного SSL сертификата..."
mkdir -p certbot/conf/live/selfsigned
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certbot/conf/live/selfsigned/privkey.pem \
  -out certbot/conf/live/selfsigned/fullchain.pem \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Appointment System/CN=yourclients.duckdns.org"

chmod 644 certbot/conf/live/selfsigned/fullchain.pem
chmod 600 certbot/conf/live/selfsigned/privkey.pem

echo "✓ Сертификат создан"

# 2. Создаем директорию для certbot www
echo "2. Создание директорий..."
mkdir -p certbot/www/.well-known/acme-challenge
chmod -R 755 certbot/www
echo "✓ Директории созданы"

# 3. Проверяем .env
echo "3. Проверка .env..."
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден! Скопируйте env.example в .env и настройте его."
    exit 1
fi

# Обновляем ALLOWED_HOSTS (добавляем домен если его нет)
if ! grep -q "yourclients.duckdns.org" .env; then
    echo "⚠ Добавьте домен в ALLOWED_HOSTS в файле .env:"
    echo "   ALLOWED_HOSTS=185.155.101.22,yourclients.duckdns.org"
fi

echo "✓ .env проверен"

# 4. Собираем и запускаем контейнеры
echo "4. Запуск Docker контейнеров..."
docker-compose build web
docker-compose up -d

echo "5. Ожидание готовности сервисов..."
sleep 10

# 6. Проверка статуса
echo "6. Проверка статуса контейнеров..."
docker-compose ps

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Проверьте работу:"
echo "  - HTTP:  curl -I http://yourclients.duckdns.org"
echo "  - HTTPS: curl -k -I https://yourclients.duckdns.org"
echo ""
echo "Логи nginx: docker-compose logs nginx"
echo "Логи web:   docker-compose logs web"
