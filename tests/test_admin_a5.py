"""Admin A5: audit, ops, export, rate limit."""
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import AdminAuditLog, Booking, Calendar, Category, Consultant, Service, User
from app.services.admin_audit import write_admin_audit
from app.services.platform_admin_audit import audit_action_choices, list_admin_audit
from app.services.platform_admin_export import export_bookings_csv, export_users_csv
from app.services.platform_admin_ops import create_platform_backup, list_recent_backups
from app.services.rate_limit import check_rate_limit, reset_rate_limit


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_rate_limit_blocks_after_max():
    reset_rate_limit("test-key")
    assert check_rate_limit("test-key", max_calls=2, window_sec=60)
    assert check_rate_limit("test-key", max_calls=2, window_sec=60)
    assert not check_rate_limit("test-key", max_calls=2, window_sec=60)
    reset_rate_limit("test-key")


def test_audit_list_and_actions():
    db = _session()
    write_admin_audit(db, actor_user_id=1, action="user_block", entity="user", entity_id="2")
    db.commit()
    rows = list_admin_audit(db, action="user_block")
    assert len(rows) == 1
    actions = audit_action_choices(db)
    assert "user_block" in actions
    db.close()


def test_csv_export():
    db = _session()
    u = User(username="e@t.c", password="x", email="e@t.c", date_joined=datetime.now())
    db.add(u)
    db.flush()
    cat = Category(name_category="X")
    db.add(cat)
    db.flush()
    c = Consultant(first_name="A", last_name="B", email="c@t.c", phone="1", category_of_specialist_id=cat.id)
    db.add(c)
    db.flush()
    cal = Calendar(consultant_id=c.id, name="Cal", color="#7d5cff")
    db.add(cal)
    db.flush()
    svc = Service(consultant_id=c.id, calendar_id=cal.id, name="S", duration_minutes=60)
    db.add(svc)
    db.flush()
    from datetime import date, time

    db.add(
        Booking(
            service_id=svc.id,
            calendar_id=cal.id,
            client_name="X",
            client_phone="1",
            booking_date=date.today(),
            booking_time=time(10, 0),
            status="pending",
        )
    )
    db.commit()
    users_csv = export_users_csv(db)
    assert "e@t.c" in users_csv
    bookings_csv = export_bookings_csv(db)
    assert "pending" in bookings_csv
    db.close()


def test_sqlite_backup():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        db_path = base / "data.db"
        db_path.write_bytes(b"sqlite-test")
        backups_dir = base / "media" / "backups"
        backups_dir.mkdir(parents=True)

        class FakeSettings:
            base_dir = base
            database_url = f"sqlite:///{db_path}"
            db_name = None
            db_host = ""
            db_port = ""
            db_user = ""
            db_password = ""

        path, err = create_platform_backup(FakeSettings())
        assert err is None
        assert path and path.startswith("media/backups/")
        recent = list_recent_backups(backups_dir)
        assert len(recent) == 1
