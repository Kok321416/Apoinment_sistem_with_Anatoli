"""Context processors для шаблонов consultant_menu."""
from django.conf import settings


def header_user(request):
    """Имя специалиста и учётная запись (почта/логин) для шапки справа."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {
            'header_consultant_name': '',
            'header_account_display': '',
        }
    user = request.user
    name = ''
    try:
        from consultant_menu.models import Consultant
        consultant = Consultant.objects.get(user=user)
        parts = [consultant.first_name or '', consultant.last_name or '']
        name = ' '.join(p for p in parts if p).strip() or consultant.email or user.get_full_name() or user.username
    except Exception:
        name = user.get_full_name() or user.username or ''

    account = ''
    try:
        from allauth.account.models import EmailAddress
        primary = EmailAddress.objects.filter(user=user, primary=True).first()
        if primary and primary.email:
            account = primary.email
    except Exception:
        pass
    if not account and getattr(user, 'email', None):
        account = user.email
    if not account and getattr(user, 'username', None) and '@' in user.username:
        account = user.username
    # Подключённые сервисы: показываем, через что вошли (если есть)
    try:
        from allauth.socialaccount.models import SocialAccount
        social = SocialAccount.objects.filter(user=user).first()
        if social:
            provider = social.provider
            extra = social.extra_data or {}
            if provider == 'google' and (extra.get('email') or user.email):
                account = account or extra.get('email') or user.email
            elif provider == 'telegram':
                uname = extra.get('username') or ''
                if uname and not uname.startswith('@'):
                    uname = '@' + uname
                account = account or uname or user.email or user.username
    except Exception:
        pass
    if not account:
        account = getattr(user, 'username', '') or ''

    return {
        'header_consultant_name': name,
        'header_account_display': account,
    }


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
