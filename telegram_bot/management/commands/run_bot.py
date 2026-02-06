"""
Management команда для запуска Telegram бота
Использование: python manage.py run_bot
Логи пишутся в файл (TELEGRAM_BOT_LOG_FILE) и в stdout/journal при systemd.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import logging
import requests
import time
import threading
import os

logger = logging.getLogger(__name__)


def _setup_bot_file_logging():
    """Добавить вывод логов бота в файл (корень репозитория/logs/telegram_bot.log)."""
    log_path = getattr(settings, 'TELEGRAM_BOT_LOG_FILE', None)
    if not log_path:
        return
    try:
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.isdir(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        for name in ('telegram_bot', 'telegram_bot.bot'):
            log = logging.getLogger(name)
            log.addHandler(handler)
            log.setLevel(logging.DEBUG)
        logger.info("Логирование бота в файл: %s", log_path)
    except Exception as e:
        logger.warning("Не удалось настроить лог-файл бота: %s", e)


class Command(BaseCommand):
    help = 'Запускает Telegram бота для обработки обновлений'

    def handle(self, *args, **options):
        _setup_bot_file_logging()
        self.stdout.write(self.style.SUCCESS('Запуск Telegram бота...'))
        site_url = getattr(settings, 'SITE_URL', '') or 'не задан'
        logger.info("TG bot: запуск. SITE_URL=%s", site_url)

        TELEGRAM_BOT_TOKEN = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not TELEGRAM_BOT_TOKEN:
            logger.error("TG bot: TELEGRAM_BOT_TOKEN не установлен")
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN не установлен в settings.py'))
            return
        logger.info("TG bot: токен задан (первые 10 символов: %s...)", (TELEGRAM_BOT_TOKEN or '')[:10])

        use_webhook = getattr(settings, 'TELEGRAM_USE_WEBHOOK', False)
        if use_webhook:
            self.setup_webhook(TELEGRAM_BOT_TOKEN)
        else:
            self.run_long_polling(TELEGRAM_BOT_TOKEN)
    
    def setup_webhook(self, token):
        """Настройка webhook для получения обновлений"""
        webhook_url = getattr(settings, 'TELEGRAM_WEBHOOK_URL', None)
        if not webhook_url:
            self.stdout.write(self.style.ERROR('TELEGRAM_WEBHOOK_URL не установлен'))
            return
        
        url = f"https://api.telegram.org/bot{token}/setWebhook"
        data = {'url': webhook_url}
        
        try:
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result.get('ok'):
                self.stdout.write(self.style.SUCCESS(f'Webhook установлен: {webhook_url}'))
            else:
                self.stdout.write(self.style.ERROR(f'Ошибка установки webhook: {result.get("description")}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при установке webhook: {e}'))
    
    def run_long_polling(self, token):
        """Запуск long polling для получения обновлений"""
        from telegram_bot.bot import handle_telegram_update
        
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        offset = 0
        error_count = 0
        max_errors = 10
        
        self.stdout.write(self.style.SUCCESS('Бот запущен. Ожидание обновлений...'))
        self.stdout.write(self.style.SUCCESS(f'Токен: {token[:10]}...'))
        
        while True:
            try:
                params = {
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': ['message', 'callback_query']
                }
                
                response = requests.get(url, params=params, timeout=35)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('ok'):
                    error_msg = data.get('description', 'Unknown error')
                    logger.error("TG bot: getUpdates API ошибка: %s", error_msg)
                    self.stdout.write(self.style.ERROR(f'Ошибка API: {error_msg}'))
                    error_count += 1
                    if error_count >= max_errors:
                        logger.error("TG bot: превышено макс. число ошибок, остановка")
                        self.stdout.write(self.style.ERROR('Превышено максимальное количество ошибок. Остановка.'))
                        break
                    time.sleep(10)
                    continue
                error_count = 0
                if data.get('result'):
                    updates = data['result']
                    for update in updates:
                        update_id = update.get('update_id')
                        offset = update_id + 1
                        try:
                            thread = threading.Thread(
                                target=handle_telegram_update,
                                args=(update,),
                                daemon=True
                            )
                            thread.start()
                        except Exception as e:
                            logger.error("TG bot: ошибка при обработке обновления: %s", e)
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nОстановка бота...'))
                break
            except requests.exceptions.RequestException as e:
                error_count += 1
                logger.error("TG bot: ошибка сети getUpdates: %s", e)
                if error_count >= max_errors:
                    self.stdout.write(self.style.ERROR('Превышено максимальное количество ошибок сети. Остановка.'))
                    break
                time.sleep(10)
            except Exception as e:
                error_count += 1
                logger.error(f"Неожиданная ошибка: {e}")
                if error_count >= max_errors:
                    self.stdout.write(self.style.ERROR('Превышено максимальное количество ошибок. Остановка.'))
                    break
                time.sleep(5)

