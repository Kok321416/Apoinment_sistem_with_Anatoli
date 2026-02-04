"""Context processors для шаблонов consultant_menu."""
from django.conf import settings


def telegram_bot_username(request):
    """Добавляет telegram_bot_username в контекст (для ссылок «Открыть в Telegram»)."""
    return {
        'telegram_bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', '') or '',
    }
