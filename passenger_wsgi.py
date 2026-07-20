"""
WSGI entrypoint for reg.ru / ispmanager shared hosting (Passenger).

reg.ru expects passenger_wsgi.py in the site root with sys.path for:
1) project directory (APP_DIR)
2) virtualenv site-packages
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PY_VER = f"python{sys.version_info.major}.{sys.version_info.minor}"
VENV_SITE_PACKAGES = BASE_DIR / "venv" / "lib" / PY_VER / "site-packages"

sys.path.insert(0, str(BASE_DIR))
if VENV_SITE_PACKAGES.exists():
    sys.path.insert(1, str(VENV_SITE_PACKAGES))

from a2wsgi import ASGIMiddleware  # noqa: E402
from app.main import app  # noqa: E402

application = ASGIMiddleware(app)
