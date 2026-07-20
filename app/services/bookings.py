import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, ClientCard, Consultant, Service, TimeSlot
from app.services.telegram import on_booking_created, on_booking_updated


def parse_fio(fio_str: str) -> tuple[str, str, str]:
    parts = (fio_str or "").strip().split()
    last_name = parts[0] if parts else ""
    first_name = parts[1] if len(parts) > 1 else ""
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else ""
    return first_name, last_name, middle_name


def find_or_create_client_card(
    db: Session,
    consultant: Consultant,
    client_name: str,
    client_phone: str,
    client_email: str,
    client_telegram: str,
) -> ClientCard:
    card = None
    if client_phone or client_email or client_telegram:
        conditions = []
        if client_phone:
            conditions.append(ClientCard.phone == client_phone)
        if client_email:
            conditions.append(ClientCard.email == client_email)
        if client_telegram:
            tg_norm = client_telegram.lstrip("@").split("/")[-1].split("?")[0]
            if tg_norm:
                conditions.append(ClientCard.telegram.ilike(f"%{tg_norm}%"))
        if conditions:
            card = (
                db.query(ClientCard)
                .filter(ClientCard.consultant_id == consultant.id, or_(*conditions))
                .first()
            )
    if not card:
        card = ClientCard(
            consultant_id=consultant.id,
            name=client_name or None,
            phone=client_phone or None,
            email=client_email or None,
            telegram=client_telegram or None,
        )
        db.add(card)
        db.flush()
        return card

    updated = False
    if client_name and not card.name:
        card.name = client_name
        updated = True
    if client_phone and card.phone != client_phone:
        card.phone = client_phone
        updated = True
    if client_email and card.email != client_email:
        card.email = client_email
        updated = True
    if client_telegram and (not card.telegram or client_telegram not in (card.telegram or "")):
        card.telegram = client_telegram
        updated = True
    if updated:
        db.flush()
    return card


def create_public_booking(
    db: Session,
    calendar: Calendar,
    service_id: int,
    booking_date: date,
    booking_time_str: str,
    booking_end_time_str: str,
    client_name: str,
    client_phone: str,
    client_email: str,
    client_telegram: str,
) -> tuple[Booking | None, str | None]:
    consultant = calendar.consultant
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.consultant_id == consultant.id, Service.is_active.is_(True))
        .first()
    )
    if not service:
        return None, "Услуга не найдена"

    start_time_obj = datetime.strptime(booking_time_str, "%H:%M").time()
    end_time_obj = datetime.strptime(booking_end_time_str, "%H:%M").time()
    start_dt = datetime.combine(booking_date, start_time_obj)
    end_dt = datetime.combine(booking_date, end_time_obj)
    duration_minutes = (end_dt - start_dt).total_seconds() / 60
    if abs(duration_minutes - service.duration_minutes) > 1:
        return None, "Неверная длительность. Выберите время из списка доступных слотов."

    day_of_week = booking_date.weekday()
    time_slot = (
        db.query(TimeSlot)
        .filter(
            TimeSlot.calendar_id == calendar.id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.start_time <= start_time_obj,
            TimeSlot.end_time >= end_time_obj,
            TimeSlot.is_available.is_(True),
        )
        .first()
    )
    if not time_slot:
        return None, "Выбранное время не входит в доступные окна приёма."

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)

    existing_bookings = (
        db.query(Booking)
        .filter(
            Booking.calendar_id == calendar.id,
            Booking.booking_date == booking_date,
            Booking.status.in_(["pending", "confirmed"]),
        )
        .with_for_update()
        .all()
    )

    for booking in existing_bookings:
        if not booking.booking_end_time:
            continue
        booking_start = datetime.combine(booking_date, booking.booking_time)
        booking_end = datetime.combine(booking_date, booking.booking_end_time)
        if not (end_dt + break_delta <= booking_start or start_dt >= booking_end + break_delta):
            return None, "Это время уже занято или слишком близко к другой записи."

    card = find_or_create_client_card(
        db, consultant, client_name, client_phone, client_email, client_telegram
    )
    link_token = uuid.uuid4().hex[:24]
    booking = Booking(
        service_id=service.id,
        time_slot_id=time_slot.id,
        calendar_id=calendar.id,
        client_card_id=card.id,
        booking_date=booking_date,
        booking_time=start_time_obj,
        booking_end_time=end_time_obj,
        client_name=client_name,
        client_phone=client_phone or "",
        client_telegram=client_telegram or "",
        client_email=client_email or "",
        status="pending",
        link_token=link_token,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    on_booking_created(db, booking)
    return booking, None


def mark_past_bookings_completed(db: Session, calendars: list[Calendar]) -> None:
    now = datetime.now()
    calendar_ids = [c.id for c in calendars]
    bookings = (
        db.query(Booking)
        .filter(Booking.calendar_id.in_(calendar_ids), Booking.status == "confirmed")
        .all()
    )
    for b in bookings:
        end_time = b.booking_end_time or b.booking_time
        end_dt = datetime.combine(b.booking_date, end_time)
        if end_dt <= now:
            b.status = "completed"
    db.commit()


def reschedule_booking(
    db: Session,
    booking: Booking,
    new_date: date,
    new_time_str: str,
) -> str | None:
    """Reschedule booking to new date/time. Returns error message or None on success."""
    calendar = booking.calendar
    service = booking.service
    if not calendar or not service:
        return "Запись или услуга не найдена"

    try:
        start_time_obj = datetime.strptime(new_time_str, "%H:%M").time()
    except (TypeError, ValueError):
        return "Некорректное время"

    end_dt = datetime.combine(new_date, start_time_obj) + timedelta(minutes=service.duration_minutes)
    end_time_obj = end_dt.time()

    day_of_week = new_date.weekday()
    time_slot = (
        db.query(TimeSlot)
        .filter(
            TimeSlot.calendar_id == calendar.id,
            TimeSlot.day_of_week == day_of_week,
            TimeSlot.start_time <= start_time_obj,
            TimeSlot.end_time >= end_time_obj,
            TimeSlot.is_available.is_(True),
        )
        .first()
    )
    if not time_slot:
        return "Выбранное время не входит в доступные окна приёма."

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)
    start_dt = datetime.combine(new_date, start_time_obj)

    existing = (
        db.query(Booking)
        .filter(
            Booking.calendar_id == calendar.id,
            Booking.booking_date == new_date,
            Booking.status.in_(["pending", "confirmed"]),
            Booking.id != booking.id,
        )
        .all()
    )
    for other in existing:
        if not other.booking_end_time:
            continue
        other_start = datetime.combine(new_date, other.booking_time)
        other_end = datetime.combine(new_date, other.booking_end_time)
        if not (end_dt + break_delta <= other_start or start_dt >= other_end + break_delta):
            return "Это время уже занято."

    booking.booking_date = new_date
    booking.booking_time = start_time_obj
    booking.booking_end_time = end_time_obj
    booking.time_slot_id = time_slot.id
    db.commit()
    db.refresh(booking)
    on_booking_updated(db, booking, created=False)
    return None
