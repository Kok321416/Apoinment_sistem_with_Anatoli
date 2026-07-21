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


def delete_time_slot(db: Session, slot: TimeSlot) -> tuple[bool, str]:
    db.query(Booking).filter(Booking.time_slot_id == slot.id).update(
        {Booking.time_slot_id: None}, synchronize_session=False
    )
    db.delete(slot)
    try:
        db.commit()
        return True, "Временное окно удалено"
    except IntegrityError:
        db.rollback()
        return False, "Не удалось удалить временное окно."
