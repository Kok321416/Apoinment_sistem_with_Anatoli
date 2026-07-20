from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "auth_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password: Mapped[str] = mapped_column(String(128))
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    date_joined: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    consultant = relationship("Consultant", back_populates="user", uselist=False)
    social_accounts = relationship("SocialAccount", back_populates="user")


class SocialAccount(Base):
    __tablename__ = "socialaccount_socialaccount"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    uid: Mapped[str] = mapped_column(String(191))
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_user.id"))
    extra_data: Mapped[str] = mapped_column(Text, default="{}")

    user = relationship("User", back_populates="social_accounts")


class EmailAddress(Base):
    __tablename__ = "account_emailaddress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    primary: Mapped[bool] = mapped_column("primary", Boolean, default=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_user.id"))


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_user.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", backref="verification_tokens")


class TelegramLoginRequest(Base):
    __tablename__ = "telegram_login_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    complete_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    next_url: Mapped[str] = mapped_column(String(500), default="/")
    process: Mapped[str] = mapped_column(String(20), default="login")
    register_fio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    register_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    connect_user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_user.id"), nullable=True)
    telegram_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
