# 🔄 Полная переустановка с HTTPS и доменом

## Шаг 1: Очистка всего Docker

```bash
cd /opt/appointment-system

# 1. Остановите и удалите ВСЕ контейнеры
docker-compose down -v

# 2. Удалите все контейнеры проекта вручную
docker ps -a | grep appointment-system
docker rm -f $(docker ps -aq --filter "name=appointment") 2>/dev/null || true

# 3. Остановите все процессы, занимающие порты 80 и 443
fuser -k 80/tcp 2>/dev/null || true
fuser -k 443/tcp 2>/dev/null || true
pkill -f "docker-proxy.*80" 2>/dev/null || true
pkill -f "docker-proxy.*443" 2>/dev/null || true

# 4. Проверьте, что порты свободны
ss -tlnp | grep -E ':(80|443)'

# 5. Перезапустите Docker (опционально, если проблемы)
systemctl restart docker
sleep 5

# 6. Проверьте статус Docker
docker ps
```

## Шаг 2: Обновление кода

```bash
cd /opt/appointment-system

# Обновите код из GitHub
git pull origin develop

# Проверьте наличие всех файлов
ls -la nginx/conf.d/app.conf
ls -la docker-compose.yml
```

## Шаг 3: Подготовка конфигурации для домена

```bash
# 1. Обновите .env
nano .env
```

Убедитесь, что там:
```env
ALLOWED_HOSTS=yourclients.duckdns.org
USE_HTTPS=True
```

## Шаг 4: Подготовка nginx для Let's Encrypt

Конфигурация nginx должна поддерживать получение сертификата.

## Шаг 5: Запуск с правильной конфигурацией

```bash
# Запустите все сервисы
docker-compose up -d

# Проверьте логи
docker-compose logs nginx | tail -20
docker-compose ps
```

## Шаг 6: Получение Let's Encrypt сертификата

После запуска получите сертификат.
