"""Email delivery log and resend (Admin A4)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import EmailDeliveryLog


def log_email_delivery(
    db: Session,
    *,
    to_email: str,
    subject: str,
    status: str,
    html_body: str | None = None,
    text_body: str | None = None,
    template_key: str | None = None,
    error: str | None = None,
) -> EmailDeliveryLog:
    row = EmailDeliveryLog(
        to_email=(to_email or "")[:254],
        subject=(subject or "")[:255],
        template_key=(template_key or None) and str(template_key)[:64],
        status=(status or "failed")[:20],
        error=error,
        html_body=html_body,
        text_body=text_body,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_email_deliveries(
    db: Session,
    *,
    status: str | None = None,
    q: str = "",
    limit: int = 50,
) -> list[EmailDeliveryLog]:
    query = db.query(EmailDeliveryLog).order_by(EmailDeliveryLog.id.desc())
    if status:
        query = query.filter(EmailDeliveryLog.status == status)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            EmailDeliveryLog.to_email.ilike(like) | EmailDeliveryLog.subject.ilike(like)
        )
    return query.limit(limit).all()


def resend_email_delivery(db: Session, log_id: int) -> tuple[EmailDeliveryLog | None, str | None]:
    row = db.get(EmailDeliveryLog, log_id)
    if not row:
        return None, "Запись не найдена"
    if not row.html_body:
        return None, "Нет тела письма для повторной отправки"
    from app.services.email import send_email

    ok = send_email(row.to_email, row.subject, row.html_body, row.text_body, template_key="resend")
    return (row, None) if ok else (row, "Не удалось отправить повторно")
