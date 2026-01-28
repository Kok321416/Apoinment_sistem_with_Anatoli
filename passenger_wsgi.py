"""
WSGI entrypoint for reg.ru / ispmanager shared hosting (Passenger).

reg.ru documentation expects a `passenger_wsgi.py` in the site root and
explicit sys.path entries for:
1) project directory
2) virtualenv site-packages
"""

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent  # site root (APP_DIR)

# Django project directory (contains manage.py)
PROJECT_DIR = BASE_DIR / "appoinment_sistem"

# venv installed by deploy workflow (inside APP_DIR)
PY_VER = f"python{sys.version_info.major}.{sys.version_info.minor}"
VENV_SITE_PACKAGES = BASE_DIR / "venv" / "lib" / PY_VER / "site-packages"

# Match reg.ru guide order: project first, then venv site-packages
sys.path.insert(0, str(PROJECT_DIR))
if VENV_SITE_PACKAGES.exists():
    sys.path.insert(1, str(VENV_SITE_PACKAGES))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "appoinment_sistem.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

