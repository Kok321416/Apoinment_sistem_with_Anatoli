"""Platform ops: health, dual inventory, backups (Admin A5)."""
from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db_schema import get_schema_health
from app.services.dual_role_inventory import collect_dual_role_inventory, format_inventory_report
from app.services.prod_readiness import run_prod_readiness
from app.services.deploy_checklist import deploy_checklist

logger = logging.getLogger(__name__)


def system_snapshot(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    schema = get_schema_health()
    inventory = collect_dual_role_inventory(db)
    db_kind = "sqlite" if s.database_url.startswith("sqlite") else "mysql"
    backups_dir = s.base_dir / "media" / "backups"
    backups = list_recent_backups(backups_dir, limit=10)
    readiness = run_prod_readiness(db, s)
    return {
        "schema": schema,
        "db_kind": db_kind,
        "site_url": s.site_url,
        "platform_admin_enabled": s.platform_admin_enabled,
        "notify_dedup": s.notify_dedup,
        "inventory": inventory,
        "inventory_report": format_inventory_report(inventory),
        "readiness": readiness,
        "deploy_checklist": deploy_checklist(db, s),
        "backups_dir": str(backups_dir.relative_to(s.base_dir)),
        "recent_backups": backups,
        "support_email": s.support_email,
    }


def list_recent_backups(backups_dir: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    if not backups_dir.is_dir():
        return []
    files = sorted(backups_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for path in files[:limit]:
        if not path.is_file():
            continue
        stat = path.stat()
        out.append(
            {
                "name": path.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds"),
            }
        )
    return out


def create_platform_backup(settings: Settings | None = None) -> tuple[str | None, str | None]:
    """Create DB backup. Returns (relative_path, error)."""
    s = settings or get_settings()
    backups_dir = s.base_dir / "media" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if s.database_url.startswith("sqlite"):
        src = s.base_dir / "data.db"
        if not src.is_file():
            return None, "Файл data.db не найден"
        dst = backups_dir / f"data_{ts}.db"
        shutil.copy2(src, dst)
        return str(dst.relative_to(s.base_dir)).replace("\\", "/"), None

    if not s.db_name:
        return None, "MySQL: DB_NAME не задан"
    dst = backups_dir / f"mysql_{s.db_name}_{ts}.sql"
    cmd = [
        "mysqldump",
        f"-h{s.db_host}",
        f"-P{s.db_port}",
        f"-u{s.db_user}",
        s.db_name,
    ]
    env = None
    if s.db_password:
        env = {"MYSQL_PWD": s.db_password}
    try:
        with dst.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                cmd,
                stdout=fh,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                timeout=120,
                check=False,
            )
        if proc.returncode != 0:
            dst.unlink(missing_ok=True)
            err = (proc.stderr or "mysqldump failed")[:500]
            return None, f"MySQL backup failed: {err}"
        return str(dst.relative_to(s.base_dir)).replace("\\", "/"), None
    except FileNotFoundError:
        return None, "mysqldump не найден на сервере. Сделайте дамп вручную через панель хостинга."
    except Exception as e:
        logger.exception("backup failed")
        dst.unlink(missing_ok=True)
        return None, str(e)[:500]
