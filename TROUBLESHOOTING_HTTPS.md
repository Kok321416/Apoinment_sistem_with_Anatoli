# 🔍 Диагностика проблем с HTTPS

Выполните эти команды на сервере и пришлите результаты:

## 1. Проверка статуса контейнеров

```bash
cd /opt/appointment-system
docker-compose ps
```

**Ожидается:** Все контейнеры должны быть в статусе `Up`

## 2. Проверка логов nginx

```bash
docker-compose logs nginx | tail -50
```

Ищите ошибки, особенно связанные с SSL сертификатом.

## 3. Проверка логов web (Django)

```bash
docker-compose logs web | tail -50
```

## 4. Проверка портов

```bash
ss -tlnp | grep -E ':(80|443)'
```

Должны быть открыты порты 80 и 443.

## 5. Проверка сертификата

```bash
docker-compose exec nginx ls -la /etc/letsencrypt/live/selfsigned/
```

Должны быть файлы: `fullchain.pem` и `privkey.pem`

## 6. Проверка конфигурации nginx

```bash
docker-compose exec nginx nginx -t
```

Должно показать: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

## 7. Попытка подключения из контейнера

```bash
docker-compose exec nginx wget -O- http://web:8000 2>&1 | head -20
```

## 8. Проверка .env файла

```bash
cat .env | grep -E "(USE_HTTPS|ALLOWED_HOSTS)"
```

## 9. Проверка сети Docker

```bash
docker network ls
docker network inspect appointment-system_app_network 2>/dev/null || docker network inspect appoinment_sistem_with_anatoli_app_network
```

## 10. Полная перезагрузка (если ничего не помогает)

```bash
cd /opt/appointment-system
docker-compose down
docker-compose build --no-cache nginx
docker-compose up -d
sleep 10
docker-compose logs nginx | tail -30
```

---

**Пришлите результаты этих команд, и я помогу найти проблему!**
