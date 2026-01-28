#!/bin/bash
# Скрипт для автоматического запуска Telegram бота при деплое на сервер

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Настройка Telegram бота ===${NC}"

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Активируем виртуальное окружение (если используется)
if [ -d "venv" ]; then
    echo -e "${YELLOW}Активация виртуального окружения...${NC}"
    source venv/bin/activate
fi

# Устанавливаем зависимости
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install -r requirements.txt

# Применяем миграции
echo -e "${YELLOW}Применение миграций...${NC}"
python manage.py migrate

# Собираем статические файлы
echo -e "${YELLOW}Сбор статических файлов...${NC}"
python manage.py collectstatic --noinput

# Создаем systemd service файл для автозапуска бота
echo -e "${YELLOW}Создание systemd service...${NC}"

PROJECT_DIR=$(pwd)
USER=$(whoami)
SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

# Определяем путь к Python
if [ -d "venv" ]; then
    PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
else
    PYTHON_PATH=$(which python3)
fi

# Проверяем наличие Python
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}✗ Python не найден по пути: $PYTHON_PATH${NC}"
    exit 1
fi

# Проверяем наличие обязательных переменных окружения
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo -e "${YELLOW}Предупреждение: TELEGRAM_BOT_TOKEN не установлен в переменных окружения${NC}"
    echo -e "${YELLOW}Установите его через: export TELEGRAM_BOT_TOKEN='ваш_токен'${NC}"
    echo -e "${YELLOW}Или добавьте в systemd service после создания${NC}"
fi

# SITE_URL опционально, используем значение по умолчанию если не указано
if [ -z "$SITE_URL" ]; then
    SITE_URL="http://127.0.0.1:8000"
    echo -e "${YELLOW}Используется SITE_URL по умолчанию: $SITE_URL${NC}"
    echo -e "${YELLOW}Для production установите: export SITE_URL='https://yourdomain.com'${NC}"
fi

sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Telegram Bot for Appointment System
After=network.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="DJANGO_SETTINGS_MODULE=appoiment_system.settings"
Environment="TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}"
Environment="SITE_URL=${SITE_URL:-http://127.0.0.1:8000}"
ExecStart=$PYTHON_PATH $PROJECT_DIR/manage.py run_bot
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegram-bot

# Ограничения ресурсов
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# Если переменные окружения установлены, добавляем их в service
if [ ! -z "$TELEGRAM_BOT_TOKEN" ]; then
    sudo systemctl set-environment TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
fi

if [ ! -z "$SITE_URL" ]; then
    sudo systemctl set-environment SITE_URL="$SITE_URL"
fi

# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable telegram-bot.service

# Запускаем сервис
echo -e "${YELLOW}Запуск Telegram бота...${NC}"
sudo systemctl start telegram-bot.service

# Проверяем статус
sleep 3
if sudo systemctl is-active --quiet telegram-bot.service; then
    echo -e "${GREEN}✓ Telegram бот успешно запущен!${NC}"
    echo ""
    echo -e "${GREEN}Полезные команды:${NC}"
    echo -e "  Проверить статус: ${YELLOW}sudo systemctl status telegram-bot${NC}"
    echo -e "  Просмотр логов: ${YELLOW}sudo journalctl -u telegram-bot -f${NC}"
    echo -e "  Перезапустить: ${YELLOW}sudo systemctl restart telegram-bot${NC}"
    echo -e "  Остановить: ${YELLOW}sudo systemctl stop telegram-bot${NC}"
    echo ""
    # Показываем последние логи
    echo -e "${YELLOW}Последние логи:${NC}"
    sudo journalctl -u telegram-bot -n 10 --no-pager
else
    echo -e "${RED}✗ Ошибка запуска бота.${NC}"
    echo -e "${YELLOW}Проверьте логи:${NC}"
    sudo journalctl -u telegram-bot -n 20 --no-pager
    exit 1
fi

echo ""
echo -e "${GREEN}=== Готово! ===${NC}"

