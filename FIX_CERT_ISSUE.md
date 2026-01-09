# 🔧 Решение проблемы "Read-only file system"

Проблема была в том, что `/etc/letsencrypt` был смонтирован как read-only (`:ro`).

## Решение: Создайте сертификат на хосте

Выполните на сервере:

```bash
cd /opt/appointment-system

# 1. Обновите код
git pull origin develop

# 2. Создайте сертификат на хосте (не в контейнере!)
mkdir -p certbot/conf/live/selfsigned

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certbot/conf/live/selfsigned/privkey.pem \
  -out certbot/conf/live/selfsigned/fullchain.pem \
  -subj '/C=RU/ST=Moscow/L=Moscow/O=Appointment System/CN=localhost'

# Установите правильные права
chmod 644 certbot/conf/live/selfsigned/fullchain.pem
chmod 600 certbot/conf/live/selfsigned/privkey.pem

# 3. Проверьте, что файлы созданы
ls -la certbot/conf/live/selfsigned/

# Должны быть: fullchain.pem и privkey.pem

# 4. Перезапустите контейнеры
docker-compose down
docker-compose up -d

# 5. Проверьте логи
docker-compose logs nginx | tail -20
```

## Альтернатива: Использовать скрипт

```bash
cd /opt/appointment-system
chmod +x scripts/create-cert-on-host.sh
./scripts/create-cert-on-host.sh
docker-compose restart nginx
```
