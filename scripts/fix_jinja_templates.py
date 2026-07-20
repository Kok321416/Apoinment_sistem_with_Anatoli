"""Fix leftover Django template syntax in app/templates for Jinja2."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"

REPLACEMENTS = [
    (r"\{% url 'account_email' %\}", "/profile/"),
    (r"\{% url 'socialaccount_connections' %\}", "/accounts/social/connections/"),
    (r"\{% url 'public_booking' calendar\.id %\}", "/book/{{ calendar.id }}/"),
    (r"request\.GET\.telegram_connected", "request.query_params.get('telegram_connected')"),
    (r"consultant\.profile_photo\.url", "consultant.profile_photo|media_url"),
    (r"\|cut:'@'", "|cut('@')"),
    (r"\|default:''", "|default('')"),
    (r'\|default:"([^"]*)"', r"|default('\1')"),
    (r"\|default:(\d+)", r"|default(\1)"),
    (r'\|time:"H:i"', "|time('H:i')"),
    (r'\|date:"d\.m\.Y"', "|date('d.m.Y')"),
    (r"\|truncatewords:(\d+)", r"|truncatewords(\1)"),
    (r"\{% empty %\}", "{% else %}"),
    (r"\{% csrf_token %\}", '<input type="hidden" name="csrf_token" value="{{ csrf_token }}">'),
    (r"time_slots_by_day\.(\d+)", r"time_slots_by_day[\1]"),
]


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, repl in REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main():
    changed = []
    for path in sorted(TEMPLATES.glob("*.html")):
        if fix_file(path):
            changed.append(path.name)
    print("Fixed:", ", ".join(changed) if changed else "nothing")


if __name__ == "__main__":
    main()
