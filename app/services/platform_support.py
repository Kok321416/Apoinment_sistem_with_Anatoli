"""Support inbox for Admin A5+."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import SupportTicket, SupportTicketMessage, User

TICKET_OPEN = "open"
TICKET_IN_PROGRESS = "in_progress"
TICKET_RESOLVED = "resolved"
TICKET_CLOSED = "closed"

TICKET_STATUSES = (TICKET_OPEN, TICKET_IN_PROGRESS, TICKET_RESOLVED, TICKET_CLOSED)

TICKET_STATUS_LABELS = {
    TICKET_OPEN: "Открыт",
    TICKET_IN_PROGRESS: "В работе",
    TICKET_RESOLVED: "Решён",
    TICKET_CLOSED: "Закрыт",
}


def list_support_tickets(
    db: Session,
    *,
    status: str | None = None,
    q: str = "",
    limit: int = 50,
) -> list[SupportTicket]:
    query = db.query(SupportTicket).order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
    if status and status in TICKET_STATUSES:
        query = query.filter(SupportTicket.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (SupportTicket.subject.ilike(like))
            | (SupportTicket.contact_email.ilike(like))
            | (SupportTicket.contact_name.ilike(like))
        )
    return query.limit(limit).all()


def ticket_detail(db: Session, ticket_id: int) -> dict | None:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        return None
    messages = (
        db.query(SupportTicketMessage)
        .filter(SupportTicketMessage.ticket_id == ticket.id)
        .order_by(SupportTicketMessage.created_at.asc(), SupportTicketMessage.id.asc())
        .all()
    )
    user = db.get(User, ticket.user_id) if ticket.user_id else None
    assignee = db.get(User, ticket.assigned_to_user_id) if ticket.assigned_to_user_id else None
    return {"ticket": ticket, "messages": messages, "user": user, "assignee": assignee}


def create_support_ticket(
    db: Session,
    *,
    subject: str,
    body: str,
    contact_email: str,
    contact_name: str = "",
    user_id: int | None = None,
) -> tuple[SupportTicket | None, str | None]:
    subject = (subject or "").strip()
    body = (body or "").strip()
    contact_email = (contact_email or "").strip().lower()
    contact_name = (contact_name or "").strip()
    if not subject:
        return None, "Укажите тему"
    if not body:
        return None, "Опишите проблему"
    if not contact_email or "@" not in contact_email:
        return None, "Укажите корректный email"
    if len(subject) > 255:
        return None, "Тема слишком длинная"
    now = datetime.utcnow()
    ticket = SupportTicket(
        user_id=user_id,
        contact_name=contact_name,
        contact_email=contact_email,
        subject=subject,
        body=body,
        status=TICKET_OPEN,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    db.add(
        SupportTicketMessage(
            ticket_id=ticket.id,
            author_user_id=user_id,
            is_staff_reply=False,
            body=body,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(ticket)
    try:
        from app.config import get_settings
        from app.services.email import send_support_ticket_created_email

        s = get_settings()
        send_support_ticket_created_email(
            to_email=s.support_email,
            ticket_id=ticket.id,
            subject=ticket.subject,
            contact_email=ticket.contact_email,
        )
    except Exception:
        pass
    return ticket, None


def reply_support_ticket(
    db: Session,
    ticket_id: int,
    *,
    author_user_id: int,
    body: str,
    is_staff: bool,
) -> tuple[SupportTicketMessage | None, str | None]:
    body = (body or "").strip()
    if not body:
        return None, "Пустое сообщение"
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        return None, "Тикет не найден"
    if ticket.status == TICKET_CLOSED:
        return None, "Тикет закрыт"
    now = datetime.utcnow()
    msg = SupportTicketMessage(
        ticket_id=ticket.id,
        author_user_id=author_user_id,
        is_staff_reply=is_staff,
        body=body,
        created_at=now,
    )
    db.add(msg)
    ticket.updated_at = now
    if is_staff and ticket.status == TICKET_OPEN:
        ticket.status = TICKET_IN_PROGRESS
        ticket.assigned_to_user_id = author_user_id
    db.commit()
    db.refresh(msg)
    if is_staff:
        ticket = db.get(SupportTicket, ticket_id)
        if ticket:
            try:
                from app.services.email import send_support_ticket_reply_email

                send_support_ticket_reply_email(
                    to_email=ticket.contact_email,
                    ticket_id=ticket.id,
                    subject=ticket.subject,
                    reply_body=body,
                )
            except Exception:
                pass
    return msg, None


def set_ticket_status(db: Session, ticket_id: int, status: str) -> tuple[SupportTicket | None, str | None]:
    status = (status or "").strip()
    if status not in TICKET_STATUSES:
        return None, "Некорректный статус"
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        return None, "Тикет не найден"
    ticket.status = status
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return ticket, None
