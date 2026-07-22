"""Phase 0 inventory: python -m app.commands.dual_role_inventory"""
from __future__ import annotations

import json
import sys

from app.database import SessionLocal
from app.services.dual_role_inventory import collect_dual_role_inventory, format_inventory_report


def main() -> int:
    as_json = "--json" in sys.argv
    db = SessionLocal()
    try:
        data = collect_dual_role_inventory(db)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(format_inventory_report(data))
        # Non-zero if dangerous collisions exist (CI can watch)
        if data.get("shared_integration_chats_count") or data.get("duplicate_telegram_social_uids_count"):
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
