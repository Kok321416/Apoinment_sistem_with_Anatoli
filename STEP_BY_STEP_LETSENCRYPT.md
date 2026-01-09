# Пошаговая настройка Let's Encrypt для yourclients.duckdns.org

## Шаг 1: Обновить .env
```bash
cd /opt/appointment-system
nano .env
```
Изменить:
- `ALLOWED_HOSTS=yourclients.duckdns.org`
- `USE_HTTPS=True`

## Шаг 2: Проверить DNS
```bash
nslookup yourclients.duckdns.org
# Должен показать IP: 38.99.23.92
```

## Шаг 3: Обновить nginx конфигурацию для Let's Encrypt
Временно изменить `nginx/conf.d/app.conf` - убрать HTTPS блок, оставить только HTTP для валидации.

## Шаг 4: Перезапустить nginx
```bash
docker-compose restart nginx
```

## Шаг 5: Получить сертификат Let's Encrypt
```bash
chmod +x nginx/init-letsencrypt.sh
./nginx/init-letsencrypt.sh yourclients.duckdns.org your-email@example.com
```

## Шаг 6: Обновить nginx конфигурацию с Let's Encrypt
Заменить самоподписанный сертификат на Let's Encrypt в `nginx/conf.d/app.conf`.

## Шаг 7: Перезапустить все
```bash
docker-compose restart nginx web
```

## Шаг 8: Проверить
```bash
curl -I https://yourclients.duckdns.org
```
