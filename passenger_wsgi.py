"""
WSGI entrypoint for shared hosting environments (e.g., Passenger).

Many shared hosts run Python apps via Phusion Passenger and expect a file named
`passenger_wsgi.py` in the application root.

This file wires Passenger -> Django WSGI application.
"""

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DJANGO_DIR = BASE_DIR / "appoinment_sistem"

# Ensure project paths are importable
sys.path.insert(0, str(DJANGO_DIR))
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "appoinment_sistem.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

