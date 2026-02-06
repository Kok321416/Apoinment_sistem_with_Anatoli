#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# До загрузки Django: подменяем MySQLdb на PyMySQL (иначе MySQLdb.constants на сервере)
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    import sys
    print("PyMySQL is required for the bot (pip install PyMySQL). Check venv and requirements.txt.", file=sys.stderr)
    sys.exit(1)


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "appoiment_system.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
