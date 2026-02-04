"""Context processors для шаблонов consultant_menu."""
from django.conf import settings


def telegram_bot_username(request):
    """Добавляет telegram_bot_username в контекст (для ссылок «Открыть в Telegram»)."""
    return {
        'telegram_bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', '') or '',
    }


def telegram_welcome(request):
    """Показать приветствие после входа/подключения через Telegram (один раз)."""
    if not request.user.is_authenticated:
        return {'show_telegram_welcome': False}
    show = request.session.pop('show_telegram_welcome', False)
    return {'show_telegram_welcome': show}
