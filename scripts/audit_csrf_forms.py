"""Audit Jinja templates: POST forms missing csrf_token nearby."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "templates"
FORM_SPLIT = re.compile(r"(?i)(<form\b[^>]*>)")
METHOD_POST = re.compile(r"""method\s*=\s*['\"]post['\"]""", re.I)


def main() -> int:
    missing: list[str] = []
    for path in sorted(ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        parts = FORM_SPLIT.split(text)
        i = 1
        while i < len(parts):
            tag = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            if METHOD_POST.search(tag):
                chunk = (tag + body)[:2500]
                if "csrf_token" not in chunk and "csrfmiddlewaretoken" not in chunk:
                    rel = path.relative_to(ROOT).as_posix()
                    missing.append(f"{rel}: {tag[:140]}")
            i += 2
    print(f"POST forms missing csrf_token: {len(missing)}")
    for line in missing:
        print(line)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
