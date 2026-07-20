"""Replace visible English UI strings in templates with Russian."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"

REPLACEMENTS = [
    ('aria-label="allyourclients — на главную"', 'aria-label="{{ site_brand_name }} — на главную"'),
    ('<span class="brand-name">allyourclients</span>', '<span class="brand-name">{{ site_brand_name }}</span>'),
    ("— allyourclients", "— {{ site_brand_name }}"),
    ("booking.get_status_display", "booking.status|booking_status"),
    ("b.get_status_display", "b.status|booking_status"),
    ("<strong>Email:</strong>", "<strong>Почта:</strong>"),
    ("<label for=\"email\">Email:</label>", "<label for=\"email\">Почта:</label>"),
    ("<label for=\"email\">Email</label>", "<label for=\"email\">Почта</label>"),
    ("<label>Email</label>", "<label>Почта</label>"),
    ("<label>Email *</label>", "<label>Почта *</label>"),
    ("<label for=\"client_email\">Email</label>", "<label for=\"client_email\">Почта</label>"),
    ("<label for=\"login_email\">Email (необязательно)</label>", "<label for=\"login_email\">Почта (необязательно)</label>"),
    ('<td class="summary-label">Email</td>', '<td class="summary-label">Почта</td>'),
    ("<h1>Email подтверждён</h1>", "<h1>Почта подтверждена</h1>"),
    ("<title>Подтвердите email</title>", "<title>Подтвердите почту</title>"),
    ("«Подтвердить email»", "«Подтвердить почту»"),
    ("<span class=\"auth-method-name\">Telegram</span>", "<span class=\"auth-method-name\">Телеграм</span>"),
    ('class="auth-method">Telegram</a>', 'class="auth-method">Телеграм</a>'),
    ('<span class="auth-method-label">Telegram</span>', '<span class="auth-method-label">Телеграм</span>'),
    ("<strong>Telegram:</strong>", "<strong>Телеграм:</strong>"),
    ("<label>Telegram</label>", "<label>Телеграм</label>"),
    ("<label for=\"telegram\">Telegram</label>", "<label for=\"telegram\">Телеграм</label>"),
    ("<label>Telegram (ник или ссылка)</label>", "<label>Телеграм (ник или ссылка)</label>"),
    ("<label for=\"client_telegram\">Telegram (ник)</label>", "<label for=\"client_telegram\">Телеграм (ник)</label>"),
    ("<label>Telegram username</label>", "<label>Ник в Телеграм</label>"),
    ("placeholder=\"@username\"", "placeholder=\"@ник\""),
    ("@username или t.me/username", "@ник или t.me/ник"),
    ("Chat ID:", "Идентификатор чата:"),
    ("Chat ID</label>", "Идентификатор чата</label>"),
    ("токен и Chat ID", "токен и идентификатор чата"),
    ("Telegram @andrievskypsy", "Телеграм @andrievskypsy"),
    ("Отключить Telegram", "Отключить Телеграм"),
    ("Подключить Telegram", "Подключить Телеграм"),
    ("через Telegram", "через Телеграм"),
    ("в Telegram", "в Телеграм"),
    ("Telegram-бота", "бота Телеграм"),
    ("Telegram-вход", "Вход через Телеграм"),
    ("Telegram успешно", "Телеграм успешно"),
    ("Telegram или Google", "Телеграм или Гугл"),
    ("Telegram и др.", "Телеграм и др."),
    ("Google, Telegram", "Гугл, Телеграм"),
    ("Google Calendar", "Календарь Google"),
    ("<label>Instagram</label>", "<label>Инстаграм</label>"),
    ("📷 Instagram", "📷 Инстаграм"),
    ("<label>Facebook</label>", "<label>Фейсбук</label>"),
    ("📘 Facebook", "📘 Фейсбук"),
    ("<label>VK</label>", "<label>ВКонтакте</label>"),
    ("🔵 VK", "🔵 ВКонтакте"),
    ("<label>YouTube</label>", "<label>Ютуб</label>"),
    ("📺 YouTube", "📺 Ютуб"),
    ("на YouTube", "на Ютуб"),
    ("✈️ Telegram", "✈️ Телеграм"),
    ("<h3>Вход через Telegram</h3>", "<h3>Вход через Телеграм</h3>"),
    ("<h1>Вход через Telegram</h1>", "<h1>Вход через Телеграм</h1>"),
    ("<title>Вход через Telegram</title>", "<title>Вход через Телеграм</title>"),
    ("Войти через Telegram", "Войти через Телеграм"),
    ("Открыть бота в Telegram", "Открыть бота в Телеграм"),
    ("<title>Подтверждение Telegram</title>", "<title>Подтверждение Телеграм</title>"),
    ("Telegram привязан", "Телеграм привязан"),
    ("Подтвердить в Telegram", "Подтвердить в Телеграм"),
    ("аккаунт Telegram", "аккаунт Телеграм"),
    ("Telegram —", "Телеграм —"),
    ("Telegram.", "Телеграм."),
    ("Telegram,", "Телеграм,"),
    ("                        Telegram", "                        Телеграм"),
    ("Бот Telegram", "Бот Телеграм"),
    ("бота Telegram", "бота Телеграм"),
    ("@BotFather в Telegram", "@BotFather в Телеграм"),
    ("email и Telegram", "почту и Телеграм"),
    ("телефону, email и Telegram", "телефону, почте и Телеграм"),
    ("<p>Email: ' + email + '</p>", "<p>Почта: ' + email + '</p>"),
    ("<p>Telegram: ' + telegram + '</p>", "<p>Телеграм: ' + telegram + '</p>"),
    ("Сайт allyourclients.ru (далее — «Сервис»)", "Сервис «{{ site_brand_name }}» (далее — «Сервис»)"),
    ("Используя сайт allyourclients.ru (далее — «Сервис»)", "Используя сервис «{{ site_brand_name }}» (далее — «Сервис»)"),
    ("{{ acc.provider }} (uid:", "{{ acc.provider|auth_provider }} (идентификатор:"),
    ("Перейти к входу через Telegram", "Перейти к входу через Телеграм"),
    ("Telegram для рассылки", "Телеграм для рассылки"),
    ("Подключить Telegram-бота", "Подключить бота Телеграм"),
    ("Подключите Telegram-бота", "Подключите бота Телеграм"),
    ("Подключите Telegram -", "Подключите Телеграм -"),
    ("Подключите Telegram —", "Подключите Телеграм —"),
    ("Подключить через бота Telegram", "Подключить через бота Телеграм"),
    ("Вход через Telegram доступен", "Вход через Телеграм доступен"),
    ("Открыть в Telegram", "Открыть в Телеграм"),
    ("уведомления в Telegram", "уведомления в Телеграм"),
    ("Получать уведомления в Telegram?", "Получать уведомления в Телеграм?"),
    ("Подтвердите Telegram —", "Подтвердите Телеграм —"),
    ("Проверьте Telegram —", "Проверьте Телеграм —"),
    ("в приложении Telegram", "в приложении Телеграм"),
    ("Telegram (например", "Телеграм (например"),
]


def main():
    changed = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        original = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed.append(path.name)
    print("Russified:", ", ".join(changed) if changed else "nothing")


if __name__ == "__main__":
    main()
