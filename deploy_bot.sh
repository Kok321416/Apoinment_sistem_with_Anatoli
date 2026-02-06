#!/bin/bash
# Запуск Telegram-бота как systemd-сервиса: автозапуск при загрузке сервера и перезапуск при падении.
# Бот обязан работать из КОРНЯ репозитория с настройками appoiment_system.settings (корневой manage.py).

set -e
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Настройка Telegram бота (systemd) ===${NC}"

# Переходим в корень репозитория (каталог скрипта)
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Проверка: бот должен запускаться из корня (здесь manage.py, appoiment_system, telegram_bot)
if [ ! -f "manage.py" ] || [ ! -d "appoiment_system" ] || [ ! -d "telegram_bot" ]; then
    echo -e "${RED}✗ Запустите скрипт из корня репозитория (где лежат manage.py, appoiment_system, telegram_bot).${NC}"
    exit 1
fi

# .env обязателен: из него systemd подхватит TELEGRAM_BOT_TOKEN и SITE_URL
if [ ! -f ".env" ]; then
    echo -e "${RED}✗ Файл .env не найден. Создайте его из env.example и укажите TELEGRAM_BOT_TOKEN и SITE_URL.${NC}"
    exit 1
fi
if ! grep -q 'TELEGRAM_BOT_TOKEN=' .env 2>/dev/null || ! grep -qE '^TELEGRAM_BOT_TOKEN=.+$' .env 2>/dev/null; then
    echo -e "${YELLOW}⚠ В .env должен быть непустой TELEGRAM_BOT_TOKEN. Проверьте файл .env.${NC}"
fi

# Виртуальное окружение
if [ -d "venv" ]; then
    echo -e "${YELLOW}Активация venv...${NC}"
    source venv/bin/activate
fi

# Зависимости и миграции (для appoiment_system / bookings)
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install -q -r requirements.txt
echo -e "${YELLOW}Миграции (appoiment_system)...${NC}"
python manage.py migrate --noinput
echo -e "${YELLOW}Сбор статики (если настроена)...${NC}"
python manage.py collectstatic --noinput 2>/dev/null || true

# Пути для systemd
PROJECT_DIR="$ROOT_DIR"
USER=$(whoami)
SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

if [ -d "venv" ]; then
    PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
else
    PYTHON_PATH=$(which python3)
fi
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}✗ Python не найден: $PYTHON_PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}Создание systemd unit (переменные из .env)...${NC}"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Telegram Bot — запись на консультации (корень репозитория, appoiment_system.settings)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment=DJANGO_SETTINGS_MODULE=appoiment_system.settings
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PYTHON_PATH $PROJECT_DIR/manage.py run_bot
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegram-bot
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
echo -e "${YELLOW}Запуск сервиса...${NC}"
sudo systemctl start telegram-bot.service

sleep 3
if sudo systemctl is-active --quiet telegram-bot.service; then
    echo -e "${GREEN}✓ Бот запущен и будет автоматически стартовать при загрузке сервера и перезапускаться при сбоях.${NC}"
    echo ""
    echo -e "${GREEN}Команды:${NC}"
    echo -e "  Статус:   ${YELLOW}sudo systemctl status telegram-bot${NC}"
    echo -e "  Логи:     ${YELLOW}sudo journalctl -u telegram-bot -f${NC}"
    echo -e "  Рестарт:  ${YELLOW}sudo systemctl restart telegram-bot${NC}"
    echo -e "  Стоп:     ${YELLOW}sudo systemctl stop telegram-bot${NC}"
    echo ""
    sudo journalctl -u telegram-bot -n 8 --no-pager
else
    echo -e "${RED}✗ Сервис не запустился. Логи:${NC}"
    sudo journalctl -u telegram-bot -n 25 --no-pager
    exit 1
fi
echo -e "${GREEN}=== Готово ===${NC}"
