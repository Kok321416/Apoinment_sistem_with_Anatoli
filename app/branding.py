"""Visible site branding and Russian UI labels."""

DEFAULT_SITE_BRAND_NAME = "Все клиенты здесь"

BOOKING_STATUS_LABELS = {
    "pending": "Ожидает подтверждения",
    "confirmed": "Подтверждена",
    "completed": "Завершена",
    "cancelled": "Отменена",
}

AUTH_PROVIDER_LABELS = {
    "telegram": "Телеграм",
    "yandex": "Яндекс",
    "google": "Гугл",
    "email": "Почта",
}


def booking_status_label(status: str | None) -> str:
    if not status:
        return ""
    return BOOKING_STATUS_LABELS.get(status, status)


def auth_provider_label(provider: str | None) -> str:
    if not provider:
        return ""
    return AUTH_PROVIDER_LABELS.get(provider.lower(), provider)
