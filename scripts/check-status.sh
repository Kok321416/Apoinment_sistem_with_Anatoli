#!/bin/bash
# Скрипт для проверки работоспособности проекта

echo "=== Проверка работоспособности проекта ==="
echo ""

cd /opt/appointment-system || { echo "❌ Директория не найдена!"; exit 1; }

# 1. Проверка контейнеров
echo "1. Статус контейнеров:"
echo "-------------------"
docker-compose ps
echo ""

# 2. Проверка портов
echo "2. Проверка портов:"
echo "-------------------"
echo "Порт 80 (HTTP):"
ss -tlnp 2>/dev/null | grep ":80 " || echo "  ⚠ Порт 80 не слушается"
echo "Порт 443 (HTTPS):"
ss -tlnp 2>/dev/null | grep ":443 " || echo "  ⚠ Порт 443 не слушается"
echo "Порт 5432 (PostgreSQL):"
ss -tlnp 2>/dev/null | grep ":5432 " || echo "  ⚠ Порт 5432 не слушается"
echo ""

# 3. Проверка nginx
echo "3. Проверка Nginx:"
echo "-------------------"
if docker-compose ps | grep -q "nginx.*Up"; then
    echo "✓ Nginx контейнер запущен"
    
    # Проверка конфигурации
    if docker-compose exec -T nginx nginx -t 2>&1 | grep -q "successful"; then
        echo "✓ Конфигурация nginx валидна"
    else
        echo "❌ Ошибка в конфигурации nginx:"
        docker-compose exec -T nginx nginx -t 2>&1 | grep -i error
    fi
    
    # Проверка HTTP локально
    echo "Проверка HTTP (локально):"
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: yourclients.duckdns.org" http://localhost 2>/dev/null)
    if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "302" ]; then
        echo "  ✓ HTTP работает (код: $HTTP_STATUS)"
    else
        echo "  ❌ HTTP не работает (код: $HTTP_STATUS)"
    fi
else
    echo "❌ Nginx контейнер не запущен"
fi
echo ""

# 4. Проверка Django/Web
echo "4. Проверка Django приложения:"
echo "-------------------"
if docker-compose ps | grep -q "web.*Up"; then
    echo "✓ Web контейнер запущен"
    
    # Проверка переменных окружения
    echo "Проверка ALLOWED_HOSTS:"
    ALLOWED_HOSTS=$(docker-compose exec -T web env | grep ALLOWED_HOSTS | cut -d= -f2)
    echo "  ALLOWED_HOSTS=$ALLOWED_HOSTS"
    
    if echo "$ALLOWED_HOSTS" | grep -q "yourclients.duckdns.org"; then
        echo "  ✓ Домен добавлен в ALLOWED_HOSTS"
    else
        echo "  ⚠ Домен НЕ найден в ALLOWED_HOSTS"
    fi
    
    # Проверка доступности приложения
    echo "Проверка доступности приложения (внутри контейнера):"
    if docker-compose exec -T web curl -s -o /dev/null -w "%{http_code}" http://localhost:8000 2>/dev/null | grep -q "200\|301\|302"; then
        echo "  ✓ Приложение отвечает на порту 8000"
    else
        echo "  ❌ Приложение не отвечает"
    fi
else
    echo "❌ Web контейнер не запущен"
fi
echo ""

# 5. Проверка базы данных
echo "5. Проверка базы данных:"
echo "-------------------"
if docker-compose ps | grep -q "db.*healthy"; then
    echo "✓ База данных запущена и здорова"
    
    # Проверка подключения
    if docker-compose exec -T db pg_isready -U appointment_user 2>/dev/null | grep -q "accepting"; then
        echo "  ✓ PostgreSQL принимает подключения"
    else
        echo "  ❌ PostgreSQL не принимает подключения"
    fi
else
    echo "❌ База данных не запущена или нездорова"
fi
echo ""

# 6. Проверка внешней доступности
echo "6. Проверка внешней доступности:"
echo "-------------------"
echo "Проверка HTTP извне:"
EXTERNAL_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://yourclients.duckdns.org 2>/dev/null)
if [ "$EXTERNAL_HTTP" = "200" ] || [ "$EXTERNAL_HTTP" = "301" ] || [ "$EXTERNAL_HTTP" = "302" ]; then
    echo "  ✓ Сайт доступен извне по HTTP (код: $EXTERNAL_HTTP)"
elif [ "$EXTERNAL_HTTP" = "000" ]; then
    echo "  ❌ Сайт НЕ доступен извне (Connection refused)"
    echo "     Возможно, порт 80 заблокирован провайдером"
else
    echo "  ⚠ Сайт отвечает, но с ошибкой (код: $EXTERNAL_HTTP)"
fi

echo "Проверка по IP:"
IP_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://185.155.101.22 2>/dev/null)
if [ "$IP_HTTP" = "200" ] || [ "$IP_HTTP" = "301" ] || [ "$IP_HTTP" = "302" ]; then
    echo "  ✓ Сайт доступен по IP (код: $IP_HTTP)"
elif [ "$IP_HTTP" = "000" ]; then
    echo "  ❌ Сайт НЕ доступен по IP (Connection refused)"
else
    echo "  ⚠ Сайт отвечает по IP с ошибкой (код: $IP_HTTP)"
fi
echo ""

# 7. Последние логи
echo "7. Последние логи (последние 5 строк каждого сервиса):"
echo "-------------------"
echo "Nginx:"
docker-compose logs nginx --tail=5 2>/dev/null | tail -5
echo ""
echo "Web:"
docker-compose logs web --tail=5 2>/dev/null | tail -5
echo ""
echo "DB:"
docker-compose logs db --tail=5 2>/dev/null | tail -5
echo ""

# 8. Итоговая сводка
echo "=== Итоговая сводка ==="
echo "-------------------"
ALL_OK=true

if ! docker-compose ps | grep -q "nginx.*Up"; then
    echo "❌ Nginx не запущен"
    ALL_OK=false
fi

if ! docker-compose ps | grep -q "web.*Up"; then
    echo "❌ Web не запущен"
    ALL_OK=false
fi

if ! docker-compose ps | grep -q "db.*healthy"; then
    echo "❌ База данных не работает"
    ALL_OK=false
fi

if [ "$EXTERNAL_HTTP" = "000" ]; then
    echo "⚠ Сайт недоступен извне (проверьте файрвол/провайдера)"
fi

if [ "$ALL_OK" = true ] && [ "$EXTERNAL_HTTP" != "000" ]; then
    echo "✓ Все основные компоненты работают!"
    echo ""
    echo "Сайт доступен по адресу:"
    echo "  - http://yourclients.duckdns.org"
    echo "  - http://185.155.101.22"
else
    echo ""
    echo "Есть проблемы. Проверьте логи выше."
fi
