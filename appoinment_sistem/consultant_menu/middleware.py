"""
Middleware: для пользователей без пароля (вошли через Telegram/Google)
перенаправляем на обязательную установку пароля.
"""
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


# Префиксы путей, куда разрешён доступ без установленного пароля
REQUIRE_PASSWORD_SET_EXEMPT_PREFIXES = (
    "/accounts/password/set",   # страница установки пароля и POST на неё
    "/accounts/logout/",
    "/accounts/google/",        # OAuth callback — должен завершиться, иначе Google не подключится к профилю
    "/accounts/telegram/",      # OAuth callback Telegram
    "/admin/",
    "/static/",
    "/media/",
)


class RequirePasswordSetMiddleware(MiddlewareMixin):
    """
    Если пользователь авторизован и у него нет установленного пароля
    (вошёл через Telegram или Google), перенаправляем на установку пароля.
    Исключения: страница установки пароля, выход, админка, статика.
    """
    def process_request(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        if request.user.has_usable_password():
            return None

        path = request.path
        if path.startswith(REQUIRE_PASSWORD_SET_EXEMPT_PREFIXES):
            return None

        set_password_url = reverse("account_set_password")
        if path == set_password_url.rstrip("/") or path == set_password_url:
            return None

        # Сохраняем next для редиректа после установки пароля
        next_url = request.get_full_path()
        redirect_url = set_password_url
        if next_url and next_url != set_password_url and not next_url.startswith("/accounts/"):
            from urllib.parse import urlencode
            redirect_url = f"{set_password_url}?{urlencode({'next': next_url})}"

        return redirect(redirect_url)
