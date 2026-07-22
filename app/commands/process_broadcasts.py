"""Process Telegram broadcast queue: python -m app.commands.process_broadcasts"""
import logging
import sys

from app.database import SessionLocal
from app.services.broadcast import process_broadcast_jobs

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


def main():
    db = SessionLocal()
    try:
        stats = process_broadcast_jobs(db, limit_jobs=5, chunk_size=25)
        print(f"Broadcast processed: {stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
