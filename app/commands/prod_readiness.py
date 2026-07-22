"""CLI: python -m app.commands.prod_readiness [--json]"""
from __future__ import annotations

import json
import sys

from app.database import SessionLocal
from app.services.prod_readiness import format_readiness_report, run_prod_readiness


def main() -> int:
    as_json = "--json" in sys.argv
    db = SessionLocal()
    try:
        data = run_prod_readiness(db)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(format_readiness_report(data))
        if not data["ok"]:
            return 1
        if data.get("warn_count"):
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
