import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, ClientCard, Consultant, Service, TimeSlot
from app.services.telegram import on_booking_created, on_booking_updated, notify_booking_rescheduled


def normalize_client_phone(raw: str, *, required: bool = False) -> tuple[str, str | None]:
    """Return (+7XXXXXXXXXX, None) or ("", error). Empty allowed unless required=True."""
    from app.deps import normalize_phone

    text = (raw or "").strip()
    if not text:
        if required:
            return "", "Укажите номер телефона"
        return "", None
    phone = normalize_phone(text)
    if not phone:
        return "", "Укажите телефон в формате +7 (XXX) XXX-XX-XX"
    return phone, None


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
    client_user_id: int | None = None,
) -> ClientCard:
    """
    Find or create a ClientCard for this consultant.

    Phase 9: when client_user_id is set, match by user first and never merge into
    another card that already belongs to a different client_user_id.
    """
    card = None
    if client_user_id is not None:
        card = (
            db.query(ClientCard)
            .filter(
                ClientCard.consultant_id == consultant.id,
                ClientCard.client_user_id == client_user_id,
            )
            .first()
        )

    if not card and (client_phone or client_email or client_telegram):
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
            candidates = (
                db.query(ClientCard)
                .filter(ClientCard.consultant_id == consultant.id, or_(*conditions))
                .all()
            )
            for cand in candidates:
                # Do not merge into a card owned by another auth user
                if (
                    client_user_id is not None
                    and cand.client_user_id is not None
                    and cand.client_user_id != client_user_id
                ):
                    continue
                card = cand
                break

    if not card:
        card = ClientCard(
            consultant_id=consultant.id,
            client_user_id=client_user_id,
            name=client_name or None,
            phone=client_phone or None,
            email=client_email or None,
            telegram=client_telegram or None,
        )
        db.add(card)
        db.flush()
        return card

    updated = False
    if client_user_id is not None and card.client_user_id is None:
        card.client_user_id = client_user_id
        updated = True
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


async def find_or_create_client_card_async(
    db,
    consultant: Consultant,
    client_name: str,
    client_phone: str,
    client_email: str,
    client_telegram: str,
    client_user_id: int | None = None,
) -> ClientCard:
    """AsyncSession twin of find_or_create_client_card."""
    from sqlalchemy import select

    card = None
    if client_user_id is not None:
        card = (
            await db.execute(
                select(ClientCard).where(
                    ClientCard.consultant_id == consultant.id,
                    ClientCard.client_user_id == client_user_id,
                )
            )
        ).scalar_one_or_none()

    if not card and (client_phone or client_email or client_telegram):
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
            candidates = list(
                (
                    await db.execute(
                        select(ClientCard).where(
                            ClientCard.consultant_id == consultant.id,
                            or_(*conditions),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for cand in candidates:
                if (
                    client_user_id is not None
                    and cand.client_user_id is not None
                    and cand.client_user_id != client_user_id
                ):
                    continue
                card = cand
                break

    if not card:
        card = ClientCard(
            consultant_id=consultant.id,
            client_user_id=client_user_id,
            name=client_name or None,
            phone=client_phone or None,
            email=client_email or None,
            telegram=client_telegram or None,
        )
        db.add(card)
        await db.flush()
        return card

    updated = False
    if client_user_id is not None and card.client_user_id is None:
        card.client_user_id = client_user_id
        updated = True
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
        await db.flush()
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
    client_user_id: int | None = None,
) -> tuple[Booking | None, str | None]:
    consultant = calendar.consultant

    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.consultant_id == consultant.id, Service.is_active.is_(True))
        .first()
    )
    if not service:
        return None, "Услуга не найдена"
    if service.calendar_id and service.calendar_id != calendar.id:
        return None, "Услуга не относится к этому календарю."

    client_phone, phone_err = normalize_client_phone(client_phone, required=True)
    if phone_err:
        return None, phone_err

    db.query(Calendar).filter(Calendar.id == calendar.id).with_for_update().one()

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

    slot_taken = (
        db.query(Booking)
        .filter(
            Booking.calendar_id == calendar.id,
            Booking.booking_date == booking_date,
            Booking.booking_time == start_time_obj,
            Booking.status.in_(["pending", "confirmed"]),
        )
        .with_for_update()
        .first()
    )
    if slot_taken:
        return None, "Это время уже занято. Выберите другой слот."

    max_per_day = calendar.max_services_per_day or 0
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
    if max_per_day > 0 and len(existing_bookings) >= max_per_day:
        return None, "Достигнут лимит записей на этот день."

    from zoneinfo import ZoneInfo

    from app.config import get_settings

    tz = ZoneInfo(get_settings().timezone)
    book_ahead_hours = calendar.book_ahead_hours or 24
    min_start = datetime.now(tz) + timedelta(hours=book_ahead_hours)
    start_aware = datetime.combine(booking_date, start_time_obj, tzinfo=tz)
    if start_aware < min_start:
        return None, f"Запись доступна минимум за {book_ahead_hours} ч. до начала."

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)

    for booking in existing_bookings:
        if not booking.booking_end_time:
            continue
        booking_start = datetime.combine(booking_date, booking.booking_time)
        booking_end = datetime.combine(booking_date, booking.booking_end_time)
        if not (end_dt + break_delta <= booking_start or start_dt >= booking_end + break_delta):
            return None, "Это время уже занято или слишком близко к другой записи."

    card = find_or_create_client_card(
        db,
        consultant,
        client_name,
        client_phone,
        client_email,
        client_telegram,
        client_user_id=client_user_id,
    )
    link_token = uuid.uuid4().hex[:24]
    from app.services.vk_auth import resolve_vk_user_id_for_user

    vk_user_id = resolve_vk_user_id_for_user(db, client_user_id)
    booking = Booking(
        service_id=service.id,
        time_slot_id=time_slot.id,
        calendar_id=calendar.id,
        client_card_id=card.id,
        client_user_id=client_user_id,
        booking_date=booking_date,
        booking_time=start_time_obj,
        booking_end_time=end_time_obj,
        client_name=client_name,
        client_phone=client_phone or "",
        client_telegram=client_telegram or None,
        client_email=client_email or None,
        status="pending",
        link_token=link_token,
        vk_user_id=vk_user_id,
        source="client",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    on_booking_created(db, booking)
    return booking, None


async def create_public_booking_async(
    db,
    calendar: Calendar,
    service_id: int,
    booking_date: date,
    booking_time_str: str,
    booking_end_time_str: str,
    client_name: str,
    client_phone: str,
    client_email: str,
    client_telegram: str,
    client_user_id: int | None = None,
    *,
    consultant: Consultant | None = None,
) -> tuple[Booking | None, str | None]:
    """AsyncSession twin of create_public_booking. Notify/Google still via sync bridge."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    if consultant is None:
        consultant = (
            await db.execute(select(Consultant).where(Consultant.id == calendar.consultant_id))
        ).scalar_one_or_none()
    if not consultant:
        return None, "Календарь не найден"

    service = (
        await db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.consultant_id == consultant.id,
                Service.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not service:
        return None, "Услуга не найдена"
    if service.calendar_id and service.calendar_id != calendar.id:
        return None, "Услуга не относится к этому календарю."

    client_phone, phone_err = normalize_client_phone(client_phone, required=True)
    if phone_err:
        return None, phone_err

    (
        await db.execute(select(Calendar).where(Calendar.id == calendar.id).with_for_update())
    ).scalar_one()

    start_time_obj = datetime.strptime(booking_time_str, "%H:%M").time()
    end_time_obj = datetime.strptime(booking_end_time_str, "%H:%M").time()
    start_dt = datetime.combine(booking_date, start_time_obj)
    end_dt = datetime.combine(booking_date, end_time_obj)
    duration_minutes = (end_dt - start_dt).total_seconds() / 60
    if abs(duration_minutes - service.duration_minutes) > 1:
        return None, "Неверная длительность. Выберите время из списка доступных слотов."

    day_of_week = booking_date.weekday()
    time_slot = (
        await db.execute(
            select(TimeSlot).where(
                TimeSlot.calendar_id == calendar.id,
                TimeSlot.day_of_week == day_of_week,
                TimeSlot.start_time <= start_time_obj,
                TimeSlot.end_time >= end_time_obj,
                TimeSlot.is_available.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not time_slot:
        return None, "Выбранное время не входит в доступные окна приёма."

    slot_taken = (
        await db.execute(
            select(Booking)
            .where(
                Booking.calendar_id == calendar.id,
                Booking.booking_date == booking_date,
                Booking.booking_time == start_time_obj,
                Booking.status.in_(["pending", "confirmed"]),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if slot_taken:
        return None, "Это время уже занято. Выберите другой слот."

    max_per_day = calendar.max_services_per_day or 0
    existing_bookings = list(
        (
            await db.execute(
                select(Booking)
                .where(
                    Booking.calendar_id == calendar.id,
                    Booking.booking_date == booking_date,
                    Booking.status.in_(["pending", "confirmed"]),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if max_per_day > 0 and len(existing_bookings) >= max_per_day:
        return None, "Достигнут лимит записей на этот день."

    from zoneinfo import ZoneInfo

    from app.config import get_settings

    tz = ZoneInfo(get_settings().timezone)
    book_ahead_hours = calendar.book_ahead_hours or 24
    min_start = datetime.now(tz) + timedelta(hours=book_ahead_hours)
    start_aware = datetime.combine(booking_date, start_time_obj, tzinfo=tz)
    if start_aware < min_start:
        return None, f"Запись доступна минимум за {book_ahead_hours} ч. до начала."

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)

    for booking in existing_bookings:
        if not booking.booking_end_time:
            continue
        booking_start = datetime.combine(booking_date, booking.booking_time)
        booking_end = datetime.combine(booking_date, booking.booking_end_time)
        if not (end_dt + break_delta <= booking_start or start_dt >= booking_end + break_delta):
            return None, "Это время уже занято или слишком близко к другой записи."

    card = await find_or_create_client_card_async(
        db,
        consultant,
        client_name,
        client_phone,
        client_email,
        client_telegram,
        client_user_id=client_user_id,
    )
    link_token = uuid.uuid4().hex[:24]
    from app.services.vk_auth import resolve_vk_user_id_for_user_async

    vk_user_id = await resolve_vk_user_id_for_user_async(db, client_user_id)
    booking = Booking(
        service_id=service.id,
        time_slot_id=time_slot.id,
        calendar_id=calendar.id,
        client_card_id=card.id,
        client_user_id=client_user_id,
        booking_date=booking_date,
        booking_time=start_time_obj,
        booking_end_time=end_time_obj,
        client_name=client_name,
        client_phone=client_phone or "",
        client_telegram=client_telegram or None,
        client_email=client_email or None,
        status="pending",
        link_token=link_token,
        vk_user_id=vk_user_id,
        source="client",
    )
    db.add(booking)
    await db.commit()

    booking = (
        await db.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.calendar))
            .where(Booking.id == booking.id)
        )
    ).scalar_one()

    from app.services.notify_bridge import schedule_on_booking_created

    schedule_on_booking_created(booking.id)
    return booking, None


def normalize_optional_email(raw: str | None) -> tuple[str | None, str | None]:
    value = (raw or "").strip()
    if not value:
        return None, None
    if "@" not in value or "." not in value.split("@")[-1]:
        return None, "Некорректный email"
    if len(value) > 254:
        return None, "Email слишком длинный"
    return value.lower(), None


def normalize_optional_telegram(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    value = value.lstrip("@")
    if "t.me/" in value.lower():
        value = value.split("/")[-1].split("?")[0]
    return value or None


async def find_matching_client_cards_async(
    db,
    consultant_id: int,
    *,
    phone: str = "",
    email: str | None = None,
    telegram: str | None = None,
    limit: int = 8,
) -> list[ClientCard]:
    from sqlalchemy import select

    conditions = []
    if phone:
        conditions.append(ClientCard.phone == phone)
    if email:
        conditions.append(ClientCard.email == email)
    if telegram:
        conditions.append(ClientCard.telegram.ilike(f"%{telegram}%"))
    if not conditions:
        return []
    rows = (
        await db.execute(
            select(ClientCard)
            .where(ClientCard.consultant_id == consultant_id, or_(*conditions))
            .order_by(ClientCard.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def search_client_cards_async(
    db,
    consultant_id: int,
    query: str,
    *,
    limit: int = 12,
) -> list[ClientCard]:
    """Live search for specialist booking: name, telegram nick, phone, email."""
    from sqlalchemy import select

    q = (query or "").strip()
    if len(q) < 1:
        return []
    like = f"%{q}%"
    tg = q.lstrip("@")
    conditions = [
        ClientCard.name.ilike(like),
        ClientCard.telegram.ilike(like),
        ClientCard.phone.ilike(like),
        ClientCard.email.ilike(like),
    ]
    if tg and tg != q:
        conditions.append(ClientCard.telegram.ilike(f"%{tg}%"))
    rows = (
        await db.execute(
            select(ClientCard)
            .where(ClientCard.consultant_id == consultant_id, or_(*conditions))
            .order_by(ClientCard.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


def serialize_client_card_match(card: ClientCard) -> dict:
    return {
        "id": card.id,
        "name": card.name or f"Клиент #{card.id}",
        "phone": card.phone or "",
        "email": card.email or "",
        "telegram": card.telegram or "",
    }


async def create_specialist_booking_async(
    db,
    consultant: Consultant,
    *,
    calendar_id: int,
    service_id: int,
    booking_date: date,
    booking_time_str: str,
    booking_end_time_str: str,
    client_name: str,
    client_phone: str = "",
    client_email: str = "",
    client_telegram: str = "",
    client_card_id: int | None = None,
    force_new_client: bool = False,
) -> tuple[Booking | None, str | None, list[dict] | None]:
    """Create booking as specialist. Returns (booking, error, matches_if_conflict)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    name = (client_name or "").strip()
    if not name:
        return None, "Укажите ФИО клиента", None

    phone, phone_err = normalize_client_phone(client_phone, required=False)
    if phone_err:
        return None, phone_err, None
    email, email_err = normalize_optional_email(client_email)
    if email_err:
        return None, email_err, None
    telegram = normalize_optional_telegram(client_telegram)

    calendar = (
        await db.execute(
            select(Calendar).where(
                Calendar.id == calendar_id,
                Calendar.consultant_id == consultant.id,
            )
        )
    ).scalar_one_or_none()
    if not calendar:
        return None, "Календарь не найден", None
    if not calendar.is_active:
        return None, "Календарь отключён", None

    service = (
        await db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.consultant_id == consultant.id,
                Service.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not service:
        return None, "Услуга не найдена", None
    if service.calendar_id and service.calendar_id != calendar.id:
        return None, "Услуга не относится к этому календарю.", None

    try:
        start_time_obj = datetime.strptime(booking_time_str, "%H:%M").time()
        end_time_obj = datetime.strptime(booking_end_time_str, "%H:%M").time()
    except ValueError:
        return None, "Некорректный формат времени", None

    start_dt = datetime.combine(booking_date, start_time_obj)
    end_dt = datetime.combine(booking_date, end_time_obj)
    duration_minutes = (end_dt - start_dt).total_seconds() / 60
    if abs(duration_minutes - service.duration_minutes) > 1:
        return None, "Неверная длительность. Выберите время из списка доступных слотов.", None

    (
        await db.execute(select(Calendar).where(Calendar.id == calendar.id).with_for_update())
    ).scalar_one()

    day_of_week = booking_date.weekday()
    time_slot = (
        await db.execute(
            select(TimeSlot).where(
                TimeSlot.calendar_id == calendar.id,
                TimeSlot.day_of_week == day_of_week,
                TimeSlot.start_time <= start_time_obj,
                TimeSlot.end_time >= end_time_obj,
                TimeSlot.is_available.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not time_slot:
        return None, "Выбранное время не входит в доступные окна приёма.", None

    slot_taken = (
        await db.execute(
            select(Booking)
            .where(
                Booking.calendar_id == calendar.id,
                Booking.booking_date == booking_date,
                Booking.booking_time == start_time_obj,
                Booking.status.in_(["pending", "confirmed"]),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if slot_taken:
        return None, "Это время уже занято. Выберите другой слот.", None

    existing_bookings = list(
        (
            await db.execute(
                select(Booking)
                .where(
                    Booking.calendar_id == calendar.id,
                    Booking.booking_date == booking_date,
                    Booking.status.in_(["pending", "confirmed"]),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    max_per_day = calendar.max_services_per_day or 0
    if max_per_day > 0 and len(existing_bookings) >= max_per_day:
        return None, "Достигнут лимит записей на этот день.", None

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)
    for booking in existing_bookings:
        if not booking.booking_end_time:
            continue
        booking_start = datetime.combine(booking_date, booking.booking_time)
        booking_end = datetime.combine(booking_date, booking.booking_end_time)
        if not (end_dt + break_delta <= booking_start or start_dt >= booking_end + break_delta):
            return None, "Это время уже занято или слишком близко к другой записи.", None

    card = None
    if client_card_id is not None:
        card = (
            await db.execute(
                select(ClientCard).where(
                    ClientCard.id == client_card_id,
                    ClientCard.consultant_id == consultant.id,
                )
            )
        ).scalar_one_or_none()
        if not card:
            return None, "Карточка клиента не найдена", None
        if not phone and card.phone:
            phone, phone_err = normalize_client_phone(card.phone, required=False)
            if phone_err:
                return None, phone_err, None
    elif not force_new_client and (phone or email or telegram):
        matches = await find_matching_client_cards_async(
            db,
            consultant.id,
            phone=phone,
            email=email,
            telegram=telegram,
        )
        if matches:
            return None, "found_matches", [serialize_client_card_match(c) for c in matches]

    if not phone:
        return None, "Укажите номер телефона", None

    from app.services.client_auth import resolve_client_user_id_by_phone_async

    client_user_id = await resolve_client_user_id_by_phone_async(db, phone)

    if card is None:
        if force_new_client:
            card = ClientCard(
                consultant_id=consultant.id,
                name=name,
                phone=phone or None,
                email=email,
                telegram=telegram,
                client_user_id=client_user_id,
            )
            db.add(card)
            await db.flush()
        else:
            card = await find_or_create_client_card_async(
                db,
                consultant,
                name,
                phone,
                email or "",
                telegram or "",
                client_user_id=client_user_id,
            )
    elif phone and card.phone != phone:
        card.phone = phone

    link_token = uuid.uuid4().hex[:24]
    booking = Booking(
        service_id=service.id,
        time_slot_id=time_slot.id,
        calendar_id=calendar.id,
        client_card_id=card.id,
        client_user_id=card.client_user_id,
        booking_date=booking_date,
        booking_time=start_time_obj,
        booking_end_time=end_time_obj,
        client_name=name,
        client_phone=phone or "",
        client_telegram=telegram,
        client_email=email,
        status="confirmed",
        link_token=link_token,
        source="specialist",
    )
    db.add(booking)
    await db.commit()

    booking = (
        await db.execute(
            select(Booking)
            .options(selectinload(Booking.service), selectinload(Booking.calendar))
            .where(Booking.id == booking.id)
        )
    ).scalar_one()

    from app.services.notify_bridge import schedule_on_booking_created

    schedule_on_booking_created(booking.id)
    return booking, None, None


def mark_past_bookings_completed(db: Session, calendars: list[Calendar]) -> None:
    from zoneinfo import ZoneInfo

    from app.config import get_settings

    tz = ZoneInfo(get_settings().timezone or "Europe/Moscow")
    now = datetime.now(tz).replace(tzinfo=None)
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


async def mark_past_bookings_completed_async(db, calendars: list[Calendar]) -> None:
    from zoneinfo import ZoneInfo

    from sqlalchemy import select

    from app.config import get_settings

    tz = ZoneInfo(get_settings().timezone or "Europe/Moscow")
    now = datetime.now(tz).replace(tzinfo=None)
    calendar_ids = [c.id for c in calendars]
    if not calendar_ids:
        return
    bookings = list(
        (
            await db.execute(
                select(Booking).where(
                    Booking.calendar_id.in_(calendar_ids),
                    Booking.status == "confirmed",
                )
            )
        ).scalars().all()
    )
    changed = False
    for b in bookings:
        end_time = b.booking_end_time or b.booking_time
        end_dt = datetime.combine(b.booking_date, end_time)
        if end_dt <= now:
            b.status = "completed"
            changed = True
    if changed:
        await db.commit()


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

    old_date = booking.booking_date
    old_time = booking.booking_time
    old_end = booking.booking_end_time

    booking.booking_date = new_date
    booking.booking_time = start_time_obj
    booking.booking_end_time = end_time_obj
    booking.time_slot_id = time_slot.id
    # Reset reminder flags so new time gets reminders again
    booking.reminder_24h_sent = False
    booking.reminder_1h_sent = False
    booking.specialist_reminder_24h_sent = False
    booking.specialist_reminder_1h_sent = False
    db.commit()
    db.refresh(booking)
    on_booking_updated(db, booking, created=False)
    try:
        notify_booking_rescheduled(
            db,
            booking,
            old_date=old_date,
            old_time=old_time,
            old_end_time=old_end,
        )
    except Exception:
        pass
    return None


async def reschedule_booking_async(
    db,
    booking: Booking,
    new_date: date,
    new_time_str: str,
) -> str | None:
    """AsyncSession twin of reschedule_booking. Notify via background bridge after commit."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    calendar = booking.calendar
    service = booking.service
    if calendar is None or service is None:
        row = (
            await db.execute(
                select(Booking)
                .options(selectinload(Booking.service), selectinload(Booking.calendar))
                .where(Booking.id == booking.id)
            )
        ).scalar_one_or_none()
        if not row:
            return "Запись или услуга не найдена"
        booking = row
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
        await db.execute(
            select(TimeSlot).where(
                TimeSlot.calendar_id == calendar.id,
                TimeSlot.day_of_week == day_of_week,
                TimeSlot.start_time <= start_time_obj,
                TimeSlot.end_time >= end_time_obj,
                TimeSlot.is_available.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not time_slot:
        return "Выбранное время не входит в доступные окна приёма."

    break_minutes = calendar.break_between_services_minutes or 0
    break_delta = timedelta(minutes=break_minutes)
    start_dt = datetime.combine(new_date, start_time_obj)

    existing = list(
        (
            await db.execute(
                select(Booking).where(
                    Booking.calendar_id == calendar.id,
                    Booking.booking_date == new_date,
                    Booking.status.in_(["pending", "confirmed"]),
                    Booking.id != booking.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for other in existing:
        if not other.booking_end_time:
            continue
        other_start = datetime.combine(new_date, other.booking_time)
        other_end = datetime.combine(new_date, other.booking_end_time)
        if not (end_dt + break_delta <= other_start or start_dt >= other_end + break_delta):
            return "Это время уже занято."

    old_date = booking.booking_date
    old_time = booking.booking_time
    old_end = booking.booking_end_time

    booking.booking_date = new_date
    booking.booking_time = start_time_obj
    booking.booking_end_time = end_time_obj
    booking.time_slot_id = time_slot.id
    booking.reminder_24h_sent = False
    booking.reminder_1h_sent = False
    booking.specialist_reminder_24h_sent = False
    booking.specialist_reminder_1h_sent = False
    await db.commit()

    from app.services.notify_bridge import schedule_rescheduled

    schedule_rescheduled(
        booking.id,
        old_date=old_date,
        old_time=old_time,
        old_end_time=old_end,
    )
    return None
