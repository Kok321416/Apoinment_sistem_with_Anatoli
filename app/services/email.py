import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """Отправить письмо через SMTP. Возвращает True при успехе."""
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.error("SMTP not configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)")
        return False

    to_email = (to_email or "").strip()
    if not to_email:
        return False

    from_addr = settings.smtp_from or settings.smtp_user
    from_name = settings.smtp_from_name or "allyourclients"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_email

    plain = text_body or _html_to_plain(html_body)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", to_email, e)
        return False


def _html_to_plain(html: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def send_verification_email(to_email: str, confirm_url: str) -> bool:
    subject = "Подтвердите регистрацию — allyourclients"
    html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #111;">
        <h2 style="font-size: 18px;">Подтверждение email</h2>
        <p>Здравствуйте!</p>
        <p>Вы зарегистрировались в системе записи <b>allyourclients</b>.</p>
        <p>Чтобы активировать аккаунт, нажмите кнопку:</p>
        <p style="margin: 24px 0;">
            <a href="{confirm_url}"
               style="background:#667eea;color:#fff;padding:12px 24px;text-decoration:none;border-radius:8px;display:inline-block;">
                Подтвердить email
            </a>
        </p>
        <p>Или скопируйте ссылку в браузер:</p>
        <p style="word-break:break-all;color:#555;">{confirm_url}</p>
        <p style="color:#666;font-size:12px;">Ссылка действует {settings.email_verify_hours} ч.
        Если вы не регистрировались, проигнорируйте это письмо.</p>
    </div>
    """
    plain = (
        f"Подтвердите регистрацию на allyourclients.\n\n"
        f"Перейдите по ссылке:\n{confirm_url}\n\n"
        f"Ссылка действует {settings.email_verify_hours} ч."
    )
    return send_email(to_email, subject, html, plain)
