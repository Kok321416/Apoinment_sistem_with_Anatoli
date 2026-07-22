from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    __tablename__ = "consultant_menu_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_category: Mapped[str] = mapped_column(String(255), default="")


class Consultant(Base):
    __tablename__ = "consultants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str] = mapped_column(String(255), default="")
    middle_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str] = mapped_column(String(15), default="")
    telegram_nickname: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category_of_specialist_id: Mapped[int] = mapped_column(ForeignKey("consultant_menu_category.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True)
    profile_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_photo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_instagram: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_facebook: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_vk: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_telegram: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_youtube: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user = relationship("User", back_populates="consultant")
    category = relationship("Category")
    calendars = relationship("Calendar", back_populates="consultant")
    services = relationship("Service", back_populates="consultant")
    client_cards = relationship("ClientCard", back_populates="consultant")
    integration = relationship("Integration", back_populates="consultant", uselist=False)


class Calendar(Base):
    __tablename__ = "calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"))
    name: Mapped[str] = mapped_column(String(255))
    color: Mapped[str] = mapped_column(String(7), default="#667eea")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    break_between_services_minutes: Mapped[int] = mapped_column(Integer, default=0)
    book_ahead_hours: Mapped[int] = mapped_column(Integer, default=24)
    max_services_per_day: Mapped[int] = mapped_column(Integer, default=0)
    reminder_hours_first: Mapped[int] = mapped_column(Integer, default=24)
    reminder_hours_second: Mapped[int] = mapped_column(Integer, default=1)
    disabled_weekdays: Mapped[str] = mapped_column(String(32), default="")

    consultant = relationship("Consultant", back_populates="calendars")
    time_slots = relationship("TimeSlot", back_populates="calendar")
    services = relationship("Service", back_populates="calendar")
    bookings = relationship("Booking", back_populates="calendar")


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    calendar = relationship("Calendar", back_populates="time_slots")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"))
    calendar_id: Mapped[int | None] = mapped_column(ForeignKey("calendars.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    color: Mapped[str] = mapped_column(String(7), default="#7d5cff")
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    consultant = relationship("Consultant", back_populates="services")
    calendar = relationship("Calendar", back_populates="services")
    bookings = relationship("Booking", back_populates="service")


class ClientCard(Base):
    __tablename__ = "consultant_client_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    consultant = relationship("Consultant", back_populates="client_cards")
    bookings = relationship("Booking", back_populates="client_card")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    time_slot_id: Mapped[int | None] = mapped_column(ForeignKey("time_slots.id"), nullable=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"))
    client_card_id: Mapped[int | None] = mapped_column(ForeignKey("consultant_client_cards.id"), nullable=True)
    # Dual-role Phase 1: link booking-as-client to auth User (nullable; backfill in Phase 2)
    client_user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True, index=True)
    client_name: Mapped[str] = mapped_column(String(255))
    client_phone: Mapped[str] = mapped_column(String(20))
    client_telegram: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    booking_date: Mapped[date] = mapped_column(Date)
    booking_time: Mapped[time] = mapped_column(Time)
    booking_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    link_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    specialist_reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    specialist_reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    google_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    service = relationship("Service", back_populates="bookings")
    calendar = relationship("Calendar", back_populates="bookings")
    client_card = relationship("ClientCard", back_populates="bookings")
    client_user = relationship("User", foreign_keys=[client_user_id], back_populates="client_bookings")
    time_slot = relationship("TimeSlot")


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultant_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"), unique=True)
    google_calendar_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    google_calendar_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    google_calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_refresh_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_bot_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_link_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    telegram_link_token_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    consultant = relationship("Consultant", back_populates="integration")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    number: Mapped[int] = mapped_column(Integer)
    telegram_nickname: Mapped[str] = mapped_column(String(255), default="")
    who_your_consultant_name_id: Mapped[int] = mapped_column(ForeignKey("consultants.id"))
