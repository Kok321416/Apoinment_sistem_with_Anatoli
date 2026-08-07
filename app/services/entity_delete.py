"""Safe deletes with FK checks (Django on_delete=CASCADE was not migrated to SQLAlchemy)."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Booking, Calendar, ClientCard, Service, TimeSlot


def delete_calendar(db: Session, calendar: Calendar) -> tuple[bool, str]:
    booking_count = db.query(Booking).filter(Booking.calendar_id == calendar.id).count()
    if booking_count:
        return False, (
            f"Нельзя удалить календарь: в нём {booking_count} "
            f"запис(ей). Сначала отмените или удалите записи в разделе «Записи»."
        )
    service_count = db.query(Service).filter(Service.calendar_id == calendar.id).count()
    if service_count:
        return False, (
            f"Нельзя удалить календарь: к нему привязано {service_count} услуг(и). "
            f"Сначала удалите или перенесите услуги на другой календарь."
        )
    db.query(TimeSlot).filter(TimeSlot.calendar_id == calendar.id).delete(synchronize_session=False)
    db.delete(calendar)
    try:
        db.commit()
        return True, "Календарь удален"
    except IntegrityError:
        db.rollback()
        return False, "Не удалось удалить календарь: есть связанные данные."


async def delete_calendar_async(db, calendar: Calendar) -> tuple[bool, str]:
    from sqlalchemy import delete, func, select

    booking_count = (
        await db.execute(
            select(func.count()).select_from(Booking).where(Booking.calendar_id == calendar.id)
        )
    ).scalar_one()
    if booking_count:
        return False, (
            f"Нельзя удалить календарь: в нём {booking_count} "
            f"запис(ей). Сначала отмените или удалите записи в разделе «Записи»."
        )
    service_count = (
        await db.execute(
            select(func.count()).select_from(Service).where(Service.calendar_id == calendar.id)
        )
    ).scalar_one()
    if service_count:
        return False, (
            f"Нельзя удалить календарь: к нему привязано {service_count} услуг(и). "
            f"Сначала удалите или перенесите услуги на другой календарь."
        )
    await db.execute(delete(TimeSlot).where(TimeSlot.calendar_id == calendar.id))
    await db.delete(calendar)
    try:
        await db.commit()
        return True, "Календарь удален"
    except IntegrityError:
        await db.rollback()
        return False, "Не удалось удалить календарь: есть связанные данные."


def delete_service(db: Session, service: Service) -> tuple[bool, str]:
    if db.query(Booking).filter(Booking.service_id == service.id).count():
        return False, "Услуга используется в записях. Деактивируйте её вместо удаления."
    db.delete(service)
    try:
        db.commit()
        return True, "Услуга удалена"
    except IntegrityError:
        db.rollback()
        return False, "Не удалось удалить услугу: есть связанные записи."


async def delete_service_async(db, service: Service) -> tuple[bool, str]:
    from sqlalchemy import func, select

    booking_count = (
        await db.execute(
            select(func.count()).select_from(Booking).where(Booking.service_id == service.id)
        )
    ).scalar_one()
    if booking_count:
        return False, "Услуга используется в записях. Деактивируйте её вместо удаления."
    await db.delete(service)
    try:
        await db.commit()
        return True, "Услуга удалена"
    except IntegrityError:
        await db.rollback()
        return False, "Не удалось удалить услугу: есть связанные записи."


def delete_client_card(db: Session, card: ClientCard) -> tuple[bool, str]:
    db.query(Booking).filter(Booking.client_card_id == card.id).update(
        {Booking.client_card_id: None}, synchronize_session=False
    )
    db.delete(card)
    try:
        db.commit()
        return True, "Карточка удалена."
    except IntegrityError:
        db.rollback()
        return False, "Не удалось удалить карточку."


async def delete_client_card_async(db, card: ClientCard) -> tuple[bool, str]:
    from sqlalchemy import update

    await db.execute(
        update(Booking).where(Booking.client_card_id == card.id).values(client_card_id=None)
    )
    await db.delete(card)
    try:
        await db.commit()
        return True, "Карточка удалена."
    except IntegrityError:
        await db.rollback()
        return False, "Не удалось удалить карточку."


def detach_bookings_from_slots(db: Session, slot_ids: list[int]) -> None:
    if not slot_ids:
        return
    db.query(Booking).filter(Booking.time_slot_id.in_(slot_ids)).update(
        {Booking.time_slot_id: None}, synchronize_session=False
    )


async def detach_bookings_from_slots_async(db, slot_ids: list[int]) -> None:
    from sqlalchemy import update

    if not slot_ids:
        return
    await db.execute(
        update(Booking).where(Booking.time_slot_id.in_(slot_ids)).values(time_slot_id=None)
    )


def delete_time_slot(db: Session, slot: TimeSlot) -> tuple[bool, str]:
    detach_bookings_from_slots(db, [slot.id])
    db.delete(slot)
    try:
        db.commit()
        return True, "Временное окно удалено"
    except IntegrityError:
        db.rollback()
        return False, "Не удалось удалить временное окно."


async def delete_time_slot_async(db, slot: TimeSlot) -> tuple[bool, str]:
    await detach_bookings_from_slots_async(db, [slot.id])
    await db.delete(slot)
    try:
        await db.commit()
        return True, "Временное окно удалено"
    except IntegrityError:
        await db.rollback()
        return False, "Не удалось удалить временное окно."
