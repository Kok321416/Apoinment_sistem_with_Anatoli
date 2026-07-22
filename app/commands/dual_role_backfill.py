"""Phase 2 backfill: python -m app.commands.dual_role_backfill [--dry-run] [--limit N]"""
from __future__ import annotations

import json
import sys

from app.database import SessionLocal
from app.services.dual_role_backfill import backfill_booking_client_user_ids, format_backfill_report


def _parse_limit(argv: list[str]) -> int | None:
    for i, arg in enumerate(argv):
        if arg == "--limit" and i + 1 < len(argv):
            try:
                return int(argv[i + 1])
            except ValueError:
                return None
        if arg.startswith("--limit="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                return None
    return None


def main() -> int:
    argv = sys.argv[1:]
    # Default dry-run unless --apply
    dry_run = "--apply" not in argv
    as_json = "--json" in argv
    limit = _parse_limit(argv)

    db = SessionLocal()
    try:
        data = backfill_booking_client_user_ids(db, dry_run=dry_run, limit=limit)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(format_backfill_report(data))
            if dry_run:
                print("Hint: re-run with --apply to write changes.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
