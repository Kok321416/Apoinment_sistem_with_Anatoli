"""Send booking reminders: python -m app.commands.send_reminders"""
import logging
import sys

from app.database import SessionLocal
from app.services.telegram import send_reminders

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


def main():
    db = SessionLocal()
    try:
        sent = send_reminders(db)
        print(f"Reminders sent: {sent}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
