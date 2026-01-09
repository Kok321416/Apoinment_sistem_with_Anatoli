# 🚀 Быстрая настройка домена для убирания предупреждения (5 минут)

## Вариант 1: DuckDNS (самый простой, бесплатно)

### Шаг 1: Регистрация
1. Откройте https://www.duckdns.org
2. Войдите через Google/GitHub (бесплатно)
3. Создайте поддомен (например: `myappointment`)
4. Получите ваш домен: `myappointment.duckdns.org`
5. Скопируйте токен

### Шаг 2: Настройка DNS на сервере

```bash
cd /opt/appointment-system

# Установите DuckDNS клиент (если нужно)
# Или просто обновите DNS вручную через их веб-интерфейс

# Узнайте ваш VPS IP
curl ifconfig.me

# Обновите DNS через API (замените YOUR_TOKEN и YOUR_DOMAIN)
curl "https://www.duckdns.org/update?domains=myappointment&token=YOUR_TOKEN&ip=$(curl -s ifconfig.me)"
```

### Шаг 3: Получение Let's Encrypt сертификата

```bash
cd /opt/appointment-system

# Подождите 2-3 минуты для распространения DNS

# Обновите .env
nano .env
# ALLOWED_HOSTS=myappointment.duckdns.org

# Получите сертификат
chmod +x nginx/init-letsencrypt.sh
./nginx/init-letsencrypt.sh myappointment.duckdns.org your-email@example.com

# Обновите nginx конфигурацию
nano nginx/conf.d/app.conf
```

Обновите `nginx/conf.d/app.conf` - замените самоподписанный блок на:

```nginx
# HTTP - редирект на HTTPS
server {
    listen 80;
    server_name myappointment.duckdns.org;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS конфигурация с Let's Encrypt
server {
    listen 443 ssl;
    http2 on;
    server_name myappointment.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/myappointment.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myappointment.duckdns.org/privkey.pem;
    
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
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

```bash
# Перезапустите
docker-compose restart nginx web

# Обновите Django settings
nano .env
# USE_HTTPS=True
docker-compose restart web
```

**Результат:** ✅ Зеленый замочек, никаких предупреждений!

---

## Вариант 2: Freenom (бесплатный домен .tk, .ml, .ga, .cf)

1. Зарегистрируйтесь на https://www.freenom.com
2. Найдите и зарегистрируйте бесплатный домен (например: `myapp.tk`)
3. Настройте A запись: `myapp.tk` → `YOUR_VPS_IP`
4. Подождите 15-30 минут для распространения DNS
5. Используйте `init-letsencrypt.sh` как выше

---

## Вариант 3: Установить сертификат только на ваш компьютер

Если домен не нужен, можно установить сертификат в доверенные корневые центры сертификации на вашем компьютере.

### Windows:

```bash
# На сервере
cd /opt/appointment-system
openssl x509 -in certbot/conf/live/selfsigned/fullchain.pem -out server.crt

# Скопируйте server.crt на Windows
# Двойной клик → Установить сертификат → 
# Локальный компьютер → 
# Доверенные корневые центры сертификации → 
# Готово!
```

**Результат:** ✅ Только ваш браузер не покажет предупреждение

---

## ⚡ Самый быстрый способ (DuckDNS)

1. Регистрация: 2 минуты
2. DNS обновление: 1 минута
3. Let's Encrypt: 2 минуты
4. **Итого: 5 минут** → Предупреждение исчезнет навсегда!

Нужна помощь с настройкой? Скажите, какой вариант выбрали!
