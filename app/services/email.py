import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.branding import DEFAULT_SITE_BRAND_NAME
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    *,
    template_key: str | None = None,
) -> bool:
    """Отправить письмо через SMTP. Возвращает True при успехе."""
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.error("SMTP not configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)")
        _persist_email_log(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            template_key=template_key,
            status="failed",
            error="SMTP not configured",
        )
        return False

    to_email = (to_email or "").strip()
    if not to_email:
        return False

    from_addr = settings.smtp_from or settings.smtp_user
    from_name = settings.smtp_from_name or DEFAULT_SITE_BRAND_NAME

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
        _persist_email_log(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=plain,
            template_key=template_key,
            status="sent",
        )
        return True
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", to_email, e)
        _persist_email_log(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=plain,
            template_key=template_key,
            status="failed",
            error=str(e)[:500],
        )
        return False


def _persist_email_log(
    *,
    to_email: str,
    subject: str,
    html_body: str | None,
    text_body: str | None,
    template_key: str | None,
    status: str,
    error: str | None = None,
) -> None:
    try:
        from app.database import SessionLocal
        from app.services.platform_email_log import log_email_delivery

        db = SessionLocal()
        try:
            log_email_delivery(
                db,
                to_email=to_email,
                subject=subject,
                status=status,
                html_body=html_body,
                text_body=text_body,
                template_key=template_key,
                error=error,
            )
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to persist email delivery log")


def _html_to_plain(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def send_verification_email(to_email: str, code: str) -> bool:
    brand = settings.site_brand_name
    hours = settings.email_verify_hours
    site = settings.site_url.rstrip("/")
    subject = f"Код подтверждения — {brand}"
    spaced = f"{code[:3]} {code[3:]}" if len(code) == 6 else code
    html = f"""
    <div style="margin:0;padding:0;background:#0b1020;font-family:Inter,Segoe UI,Arial,sans-serif;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1020;padding:32px 16px;">
        <tr>
          <td align="center">
            <table role="presentation" width="100%" style="max-width:520px;background:#121826;border:1px solid #2a3348;border-radius:16px;overflow:hidden;">
              <tr>
                <td style="padding:28px 28px 8px;text-align:center;">
                  <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#49d1ff;margin-bottom:12px;">{brand}</div>
                  <h1 style="margin:0;font-size:24px;line-height:1.3;color:#f4f7ff;">Подтвердите почту</h1>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 28px 8px;color:#b7c0d9;font-size:15px;line-height:1.6;text-align:center;">
                  Вам на почту пришёл код подтверждения. Введите его на сайте, чтобы активировать аккаунт.
                </td>
              </tr>
              <tr>
                <td style="padding:20px 28px;text-align:center;">
                  <div style="display:inline-block;background:linear-gradient(135deg,#7d5cff,#49d1ff);padding:2px;border-radius:14px;">
                    <div style="background:#0b1020;border-radius:12px;padding:18px 28px;">
                      <div style="font-size:12px;color:#8b95b0;margin-bottom:8px;">Ваш код</div>
                      <div style="font-size:36px;letter-spacing:0.28em;font-weight:700;color:#ffffff;font-family:ui-monospace,Consolas,monospace;">{spaced}</div>
                    </div>
                  </div>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 28px 28px;color:#8b95b0;font-size:13px;line-height:1.5;text-align:center;">
                  Код действует {hours} ч. Если вы не регистрировались в {brand}, просто проигнорируйте письмо.<br>
                  <a href="{site}/accounts/verify-email/?email={to_email}" style="color:#49d1ff;text-decoration:none;">Открыть страницу ввода кода</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """
    plain = (
        f"Подтверждение регистрации в сервисе {brand}.\n\n"
        f"Ваш код: {code}\n\n"
        f"Введите его на странице подтверждения почты.\n"
        f"Код действует {hours} ч.\n"
        f"{site}/accounts/verify-email/?email={to_email}\n"
    )
    return send_email(to_email, subject, html, plain, template_key="verification")


def send_email_link_success_email(to_email: str, *, needs_password: bool = False) -> bool:
    brand = settings.site_brand_name
    site = settings.site_url.rstrip("/")
    subject = f"Почта привязана — {brand}"
    password_hint = (
        "<br><br>Если пароль ещё не задан, создайте его в кабинете: "
        f'<a href="{site}/accounts/password/set/" style="color:#49d1ff;text-decoration:none;">Задать пароль</a>.'
        if needs_password
        else ""
    )
    password_plain = (
        f"\n\nЕсли пароль ещё не задан, создайте его: {site}/accounts/password/set/\n"
        if needs_password
        else ""
    )
    html = f"""
    <div style="margin:0;padding:0;background:#0b1020;font-family:Inter,Segoe UI,Arial,sans-serif;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1020;padding:32px 16px;">
        <tr>
          <td align="center">
            <table role="presentation" width="100%" style="max-width:520px;background:#121826;border:1px solid #2a3348;border-radius:16px;overflow:hidden;">
              <tr>
                <td style="padding:28px 28px 8px;text-align:center;">
                  <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#49d1ff;margin-bottom:12px;">{brand}</div>
                  <h1 style="margin:0;font-size:24px;line-height:1.3;color:#f4f7ff;">Почта привязана</h1>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 28px 28px;color:#b7c0d9;font-size:15px;line-height:1.6;text-align:center;">
                  Спасибо, что привязали почту. Теперь вы можете авторизовываться через почту и пароль.
                  {password_hint}
                  <br><br>
                  <a href="{site}/login/" style="color:#49d1ff;text-decoration:none;">Перейти ко входу</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """
    plain = (
        f"Спасибо, что привязали почту в сервисе {brand}.\n\n"
        "Теперь вы можете авторизовываться через почту и пароль.\n"
        f"{site}/login/\n"
        f"{password_plain}"
    )
    return send_email(to_email, subject, html, plain, template_key="email_link_success")


def send_password_reset_link_email(to_email: str, reset_link: str) -> bool:
    brand = settings.site_brand_name
    subject = f"Сброс пароля - {brand}"
    html = f"""
    <div style="margin:0;padding:24px;background:#0b1020;font-family:Segoe UI,Arial,sans-serif;color:#f4f7ff;">
      <h1 style="font-size:22px;">Сброс пароля</h1>
      <p style="color:#b7c0d9;line-height:1.6;">
        Администратор или вы запросили сброс пароля для {brand}.
        Ссылка действует 24 ч.
      </p>
      <p><a href="{reset_link}" style="color:#49d1ff;">Задать новый пароль</a></p>
      <p style="color:#8b95b0;font-size:13px;">Если вы не запрашивали сброс, проигнорируйте письмо.</p>
    </div>
    """
    plain = f"Сброс пароля в {brand}.\n\nПерейдите по ссылке:\n{reset_link}\n\nСсылка действует 24 ч.\n"
    return send_email(to_email, subject, html, plain, template_key="password_reset")


def send_support_ticket_created_email(
    *,
    to_email: str,
    ticket_id: int,
    subject: str,
    contact_email: str,
) -> bool:
    brand = settings.site_brand_name
    site = settings.site_url.rstrip("/")
    subj = f"[Support #{ticket_id}] {subject}"
    admin_url = f"{site}/platform-admin/support/{ticket_id}/"
    html = f"""
    <div style="margin:0;padding:24px;background:#0b1020;font-family:Segoe UI,Arial,sans-serif;color:#f4f7ff;">
      <h1 style="font-size:20px;">Новый тикет #{ticket_id}</h1>
      <p style="color:#b7c0d9;">Тема: {subject}</p>
      <p style="color:#b7c0d9;">От: {contact_email}</p>
      <p><a href="{admin_url}" style="color:#49d1ff;">Открыть в админке</a></p>
    </div>
    """
    plain = f"Новый тикет #{ticket_id}\nТема: {subject}\nОт: {contact_email}\n{admin_url}\n"
    return send_email(to_email, subj, html, plain, template_key="support_ticket_created")


def send_support_ticket_reply_email(
    *,
    to_email: str,
    ticket_id: int,
    subject: str,
    reply_body: str,
) -> bool:
    brand = settings.site_brand_name
    subj = f"Re: [{brand}] {subject} (#{ticket_id})"
    html = f"""
    <div style="margin:0;padding:24px;background:#0b1020;font-family:Segoe UI,Arial,sans-serif;color:#f4f7ff;">
      <h1 style="font-size:20px;">Ответ поддержки</h1>
      <p style="color:#8b95b0;font-size:13px;">Тикет #{ticket_id}</p>
      <div style="color:#b7c0d9;white-space:pre-wrap;line-height:1.6;">{reply_body}</div>
      <p style="color:#8b95b0;font-size:13px;margin-top:16px;">Ответьте на это письмо или напишите на {settings.support_email}</p>
    </div>
    """
    plain = f"Ответ по тикету #{ticket_id}\n\n{reply_body}\n"
    return send_email(to_email, subj, html, plain, template_key="support_ticket_reply")
