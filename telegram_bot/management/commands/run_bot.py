"""
Management команда для запуска Telegram бота
Использование: python manage.py run_bot
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import logging
import requests
import time
import threading

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Запускает Telegram бота для обработки обновлений'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Запуск Telegram бота...'))
        
        TELEGRAM_BOT_TOKEN = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not TELEGRAM_BOT_TOKEN:
            self.stdout.write(self.style.ERROR('TELEGRAM_BOT_TOKEN не установлен в settings.py'))
            return
        
        # Устанавливаем webhook или используем long polling
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
                    self.stdout.write(self.style.ERROR(f'Ошибка API: {error_msg}'))
                    error_count += 1
                    if error_count >= max_errors:
                        self.stdout.write(self.style.ERROR('Превышено максимальное количество ошибок. Остановка.'))
                        break
                    time.sleep(10)
                    continue
                
                error_count = 0  # Сбрасываем счетчик при успехе
                
                if data.get('result'):
                    updates = data['result']
                    
                    for update in updates:
                        update_id = update.get('update_id')
                        offset = update_id + 1
                        
                        # Обрабатываем обновление в отдельном потоке
                        try:
                            thread = threading.Thread(
                                target=handle_telegram_update,
                                args=(update,),
                                daemon=True
                            )
                            thread.start()
                        except Exception as e:
                            logger.error(f"Ошибка при обработке обновления: {e}")
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nОстановка бота...'))
                break
            except requests.exceptions.RequestException as e:
                error_count += 1
                logger.error(f"Ошибка сети при получении обновлений: {e}")
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

