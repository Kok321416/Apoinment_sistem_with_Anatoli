# -*- coding: utf-8 -*-
"""Fix brand SVG sources with proper UTF-8 Cyrillic."""
from pathlib import Path

brand = Path(__file__).resolve().parents[1] / "app" / "static" / "svg" / "brand"

MARK = """  <rect x="6" y="6" width="52" height="52" rx="14" stroke="#0A0A0A" stroke-width="3"/>
  <rect x="16" y="18" width="32" height="28" rx="4" stroke="#0A0A0A" stroke-width="2.5"/>
  <path d="M16 28h32M24 14v8M40 14v8" stroke="#0A0A0A" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="24" cy="36" r="2.2" fill="#0A0A0A"/>
  <circle cx="32" cy="36" r="2.2" fill="#0A0A0A"/>
  <circle cx="40" cy="36" r="2.2" fill="#0A0A0A"/>
  <circle cx="24" cy="44" r="2.2" fill="#0A0A0A"/>
  <circle cx="32" cy="44" r="2.2" fill="#0A0A0A"/>
  <circle cx="40" cy="44" r="2.2" fill="#0A0A0A"/>"""

files = {
    "logo-wordmark.svg": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 48" fill="none" aria-hidden="true">
  <text x="0" y="34" fill="#0A0A0A" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="28" font-weight="600" letter-spacing="-0.02em">Все клиенты здесь</text>
</svg>
""",
    "logo-horizontal.svg": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 64" fill="none" aria-hidden="true">
  <g>
{MARK}
  </g>
  <text x="76" y="42" fill="#0A0A0A" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="28" font-weight="600" letter-spacing="-0.02em">Все клиенты здесь</text>
</svg>
""",
    "og-banner.svg": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" fill="none" aria-hidden="true">
  <rect width="1200" height="630" fill="#FAFAFA"/>
  <g stroke="#E5E5E5" stroke-width="1">
    <path d="M0 105h1200M0 210h1200M0 315h1200M0 420h1200M0 525h1200"/>
    <path d="M150 0v630M300 0v630M450 0v630M600 0v630M750 0v630M900 0v630M1050 0v630"/>
  </g>
  <rect x="80" y="80" width="1040" height="470" rx="24" fill="#FFFFFF" stroke="#E5E5E5" stroke-width="2"/>
  <g transform="translate(468,150) scale(2.6)">
{MARK}
  </g>
  <text x="600" y="400" text-anchor="middle" fill="#0A0A0A" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="44" font-weight="600">Все клиенты здесь</text>
  <text x="600" y="455" text-anchor="middle" fill="#737373" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="24">Онлайн-запись и кабинет специалиста</text>
</svg>
""",
    "cabinet-empty-light.svg": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 560" fill="none" aria-hidden="true">
  <rect width="720" height="560" fill="#FAFAFA"/>
  <g stroke="#E5E5E5" stroke-width="1" opacity="0.9">
    <path d="M0 80h720M0 160h720M0 240h720M0 320h720M0 400h720M0 480h720"/>
    <path d="M80 0v560M160 0v560M240 0v560M320 0v560M400 0v560M480 0v560M560 0v560M640 0v560"/>
  </g>
  <rect x="120" y="90" width="480" height="360" rx="20" fill="#FFFFFF" stroke="#DADADA" stroke-width="1.5"/>
  <g transform="translate(296,140)">
{MARK}
  </g>
  <text x="360" y="260" text-anchor="middle" fill="#0A0A0A" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="28" font-weight="600">Все клиенты здесь</text>
  <text x="360" y="300" text-anchor="middle" fill="#525252" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="16">Кабинет специалиста. Выберите раздел слева.</text>
  <text x="360" y="330" text-anchor="middle" fill="#737373" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="14">Подсказка: начните с «Календари».</text>
</svg>
""",
    "cabinet-empty-decor.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 560" fill="none" aria-hidden="true">
  <rect width="720" height="560" fill="#FAFAFA"/>
  <g stroke="#E5E5E5" stroke-width="1" opacity="0.95">
    <path d="M0 80h720M0 160h720M0 240h720M0 320h720M0 400h720M0 480h720"/>
    <path d="M80 0v560M160 0v560M240 0v560M320 0v560M400 0v560M480 0v560M560 0v560M640 0v560"/>
  </g>
  <rect x="72" y="64" width="72" height="72" rx="10" stroke="#DADADA" stroke-width="1.5" fill="none"/>
  <rect x="576" y="424" width="72" height="72" rx="10" stroke="#DADADA" stroke-width="1.5" fill="none"/>
  <rect x="140" y="110" width="440" height="340" rx="20" fill="none" stroke="#E5E5E5" stroke-width="1.5" stroke-dasharray="6 6"/>
</svg>
""",
}

for name, content in files.items():
    path = brand / name
    path.write_text(content, encoding="utf-8")
    print("wrote", path.name)
