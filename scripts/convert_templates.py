"""Convert Django templates to Jinja2-compatible templates for FastAPI."""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "appoinment_sistem" / "consultant_menu" / "templates" / "consultant_menu"
DST = ROOT / "app" / "templates"
STATIC_SRC = ROOT / "appoinment_sistem" / "consultant_menu" / "static" / "consultant_menu" / "css" / "style.css"
STATIC_DST = ROOT / "app" / "static" / "css" / "style.css"

URL_REPLACEMENTS = {
    r"\{% url 'home' %\}": "/",
    r"\{% url 'privacy' %\}": "/privacy/",
    r"\{% url 'terms' %\}": "/terms/",
    r"\{% url 'register' %\}": "/register/",
    r"\{% url 'login' %\}": "/login/",
    r"\{% url 'logout' %\}": "/logout/",
    r"\{% url 'calendars' %\}": "/calendars/",
    r"\{% url 'services' %\}": "/services/",
    r"\{% url 'booking' %\}": "/booking/",
    r"\{% url 'profile' %\}": "/profile/",
    r"\{% url 'integrations' %\}": "/integrations/",
    r"\{% url 'client_cards_list' %\}": "/clients/",
    r"\{% url 'booking_redirect' %\}": "/book/",
    r"\{% url 'account_login' %\}": "/accounts/login/",
    r"\{% url 'account_set_password' %\}": "/accounts/password/set/",
    r"\{% url 'connect_telegram_app' %\}": "/integrations/telegram/connect-app/",
    r"\{% url 'google_calendar_connect' %\}": "/integrations/google/connect/",
}


def convert_content(text: str) -> str:
    text = re.sub(r"\{% load static %\}\s*", "", text)
    text = re.sub(r"\{% static 'consultant_menu/css/style.css' %\}", "/static/css/style.css", text)
    text = re.sub(r"\{% csrf_token %\}", "", text)
    text = re.sub(r"\{% url 'calendar_detail' (\w+)\.id %\}", r"/calendars/{{ \1.id }}/", text)
    text = re.sub(r"\{% url 'calendar_detail' calendar\.id %\}", "/calendars/{{ calendar.id }}/", text)
    text = re.sub(r"\{% url 'calendar_settings_edit' calendar\.id %\}", "/calendars/{{ calendar.id }}/settings/", text)
    text = re.sub(r"\{% url 'public_booking' calendar\.id %\}", "/book/{{ calendar.id }}/", text)
    text = re.sub(r"\{% url 'client_card_detail' (\w+)\.id %\}", r"/clients/{{ \1.id }}/", text)
    text = re.sub(r"\{% url 'confirm_booking_telegram_browser' booking\.link_token %\}", "/book/confirm-telegram/{{ booking.link_token }}/", text)
    text = re.sub(r"\{% url 'confirm_booking_telegram_browser' link_token %\}", "/book/confirm-telegram/{{ link_token }}/", text)
    for pattern, replacement in URL_REPLACEMENTS.items():
        text = re.sub(pattern, replacement, text)
    return text


def main():
    DST.mkdir(parents=True, exist_ok=True)
    if SRC.exists():
        for src_file in SRC.glob("*.html"):
            content = src_file.read_text(encoding="utf-8")
            (DST / src_file.name).write_text(convert_content(content), encoding="utf-8")
    if STATIC_SRC.exists():
        STATIC_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(STATIC_SRC, STATIC_DST)

    # OAuth templates
    (DST / "telegram_login.html").write_text("""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Вход через Telegram</title>
<link rel="stylesheet" href="/static/css/style.css?v=2"></head><body>
<div class="container"><h1>Вход через Telegram</h1>
<script async src="https://telegram.org/js/telegram-widget.js?22"
  data-telegram-login="{{ telegram_bot_username }}"
  data-size="large" data-auth-url="/accounts/telegram/login/callback/?next={{ next_url }}"
  data-request-access="write"></script>
<p><a href="/login/">Назад</a></p></div></body></html>""", encoding="utf-8")

    (DST / "password_set.html").write_text("""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Установка пароля</title>
<link rel="stylesheet" href="/static/css/style.css?v=2"></head><body>
<div class="container"><h1>Установите пароль</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="POST"><label>Новый пароль</label><input type="password" name="password1" required>
<label>Повторите пароль</label><input type="password" name="password2" required>
<button type="submit">Сохранить</button></form></div></body></html>""", encoding="utf-8")

    (DST / "social_connections.html").write_text("""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Управление аккаунтами</title>
<link rel="stylesheet" href="/static/css/style.css?v=2"></head><body>
<div class="container"><h1>Способы входа</h1>
<ul>{% for acc in social_accounts %}<li>{{ acc.provider }} (uid: {{ acc.uid }})</li>{% endfor %}</ul>
<p><a href="/profile/">Назад в профиль</a></p></div></body></html>""", encoding="utf-8")

    print(f"Templates converted to {DST}")


if __name__ == "__main__":
    main()
