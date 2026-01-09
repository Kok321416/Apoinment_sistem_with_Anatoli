#!/bin/bash
# Улучшенный скрипт создания самоподписанного сертификата с поддержкой IP адресов

set -e

CERT_DIR="./certbot/conf/live/selfsigned"
CERT_PATH="$CERT_DIR/fullchain.pem"
KEY_PATH="$CERT_DIR/privkey.pem"

echo "🔐 Создание улучшенного самоподписанного SSL сертификата..."

# Создаем директорию
mkdir -p "$CERT_DIR"

# Проверяем, существует ли уже сертификат
if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ]; then
    echo "⚠️  Сертификат уже существует. Удаляю старый..."
    rm -f "$CERT_PATH" "$KEY_PATH"
fi

# Проверяем наличие openssl
if ! command -v openssl &> /dev/null; then
    echo "❌ openssl не найден. Устанавливаю..."
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y openssl
    elif command -v yum &> /dev/null; then
        yum install -y openssl
    else
        echo "❌ Не удалось установить openssl. Установите вручную."
        exit 1
    fi
fi

# Получаем IP адрес сервера (если доступен)
SERVER_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "127.0.0.1")

echo "Создание конфигурации для openssl..."

# Создаем временный конфиг для openssl с subjectAltName
CONF_FILE=$(mktemp)
cat > "$CONF_FILE" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C=RU
ST=Moscow
L=Moscow
O=Appointment System
CN=localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *
IP.1 = 127.0.0.1
IP.2 = ::1
IP.3 = $SERVER_IP
EOF

# Генерируем самоподписанный сертификат с расширенными настройками
echo "Генерация сертификата..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_PATH" \
    -out "$CERT_PATH" \
    -config "$CONF_FILE" \
    -extensions v3_req

# Удаляем временный файл
rm -f "$CONF_FILE"

# Устанавливаем правильные права доступа
chmod 644 "$CERT_PATH"
chmod 600 "$KEY_PATH"

echo ""
echo "✅ Улучшенный самоподписанный сертификат успешно создан!"
echo "   Сертификат: $CERT_PATH"
echo "   Приватный ключ: $KEY_PATH"
echo "   Поддерживает IP: $SERVER_IP"
echo ""
echo "⚠️  ВНИМАНИЕ: Браузер все равно покажет предупреждение о самоподписанном сертификате."
echo "   Это нормально и безопасно для самоподписанного сертификата."
echo "   Для продакшена рекомендуется использовать домен с Let's Encrypt."
echo ""
echo "📝 Чтобы принять сертификат в браузере:"
echo "   1. Нажмите 'Дополнительно' / 'Advanced'"
echo "   2. Нажмите 'Перейти на сайт' / 'Proceed to site'"
echo "   3. Сертификат будет принят для этого IP"
