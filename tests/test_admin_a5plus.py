"""Admin A5+ backlog: support, RBAC, 2FA, broadcast stop."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models import SupportTicket, TelegramBroadcastJob, User
from app.services.admin_rbac import ROLE_SUPPORT, assign_role, effective_roles, has_permission, revoke_role
from app.services.admin_totp import enable_admin_2fa, generate_totp_secret, totp_at, verify_totp
from app.services.broadcast import JOB_CANCELLED, JOB_QUEUED, cancel_broadcast_job, create_broadcast_job
from app.services.platform_billing import billing_snapshot
from app.services.platform_support import create_support_ticket, reply_support_ticket


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_support_ticket_create_and_reply():
    db = _session()
    ticket, err = create_support_ticket(
        db,
        subject="Help",
        body="Cannot login",
        contact_email="u@t.c",
        contact_name="U",
    )
    assert err is None and ticket
    msg, err = reply_support_ticket(db, ticket.id, author_user_id=1, body="We are checking", is_staff=True)
    assert err is None and msg and msg.is_staff_reply
    db.close()


def test_rbac_assign_and_permission():
    db = _session()
    staff = User(
        username="staff",
        password="x",
        email="s@t.c",
        date_joined=datetime.now(),
        is_staff=True,
    )
    db.add(staff)
    db.commit()
    ok, _ = assign_role(db, user_id=staff.id, role=ROLE_SUPPORT, granted_by=1)
    assert ok
    assert ROLE_SUPPORT in effective_roles(db, staff)
    assert has_permission(db, staff, "support")
    assert not has_permission(db, staff, "impersonate")
    ok, _ = revoke_role(db, user_id=staff.id, role=ROLE_SUPPORT)
    assert ok
    db.close()


def test_totp_verify():
    secret = generate_totp_secret()
    code = totp_at(secret, int(__import__("time").time()) // 30)
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000")


def test_admin_2fa_enable():
    db = _session()
    u = User(username="a@t.c", password="x", email="a@t.c", date_joined=datetime.now(), is_staff=True)
    db.add(u)
    db.commit()
    from app.services.admin_totp import ensure_admin_2fa_setup

    row = ensure_admin_2fa_setup(db, u)
    code = totp_at(row.secret, int(__import__("time").time()) // 30)
    ok, msg = enable_admin_2fa(db, u, code)
    assert ok, msg
    db.close()


def test_cancel_broadcast_job():
    db = _session()
    admin = User(username="admin", password="x", email="a@t.c", date_joined=datetime.now(), is_staff=True)
    db.add(admin)
    db.flush()
    from app.models import SocialAccount

    db.add(SocialAccount(provider="telegram", uid="12345", user_id=admin.id))
    db.commit()
    job, err = create_broadcast_job(db, created_by=admin.id, audience="test_self", text="hi")
    assert job and not err, err
    stopped, err2 = cancel_broadcast_job(db, job.id)
    assert not err2 and stopped.status == JOB_CANCELLED
    db.close()


def test_billing_snapshot_stub():
    db = _session()
    from app.services.platform_billing import billing_snapshot, create_billing_plan

    snap = billing_snapshot(db)
    assert snap["enabled"] is False
    plan, err = create_billing_plan(db, code="basic", name="Basic", price_rub=990)
    assert plan and not err
    snap2 = billing_snapshot(db)
    assert snap2["plans_total"] == 1
    assert snap2["active_plans"] == 1
    db.close()
