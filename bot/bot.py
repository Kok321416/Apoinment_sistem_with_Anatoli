"""Telegram bot for appointment system (FastAPI backend)."""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

import requests

from bot.api_client import post_site_api
from bot.config import get_bot_settings

logger = logging.getLogger(__name__)
settings = get_bot_settings()
TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.telegram_bot_token}" if settings.telegram_bot_token else None
_tg_session = requests.Session()
_update_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-update")


def get_site_url() -> str:
    return settings.site_url


def _fetch_site_api(path: str, json_data: dict) -> tuple[bool, dict | None]:
    status, data = post_site_api(path, json_data)
    if status != 200 or not data:
        return False, None
    return data.get("success") is True, data


def send_telegram_message(chat_id, text, reply_markup=None) -> bool:
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        response = _tg_session.post(f"{TELEGRAM_API_URL}/sendMessage", json=data, timeout=(5, 10))
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error("Telegram send error: %s", e)
        return False


def answer_callback_query(callback_query_id, text=None) -> bool:
    if not settings.telegram_bot_token:
        return False
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text[:200]
    try:
        _tg_session.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json=payload, timeout=(3, 5))
        return True
    except Exception as e:
        logger.error("answerCallbackQuery error: %s", e)
        return False


def get_client_reply_keyboard():
    return {
        "keyboard": [
            [{"text": "📱 Записаться"}, {"text": "📋 Мои записи"}],
            [{"text": "📝 Регистрация"}, {"text": "📜 История"}, {"text": "📞 Связаться"}],
            [{"text": "❓ Помощь"}],
        ],
        "resize_keyboard": True,
        "persistent": True,
    }


def get_specialist_reply_keyboard():
    return {
        "keyboard": [
            [{"text": "📅 Ближайшие записи"}, {"text": "📊 Статистика"}],
            [{"text": "🔗 Управление аккаунтами"}],
            [{"text": "❓ Помощь"}],
        ],
        "resize_keyboard": True,
        "persistent": True,
    }


def _get_booking_url() -> str:
    return f"{get_site_url().rstrip('/')}/book/"


def _send_webapp_button(chat_id):
    keyboard = {"inline_keyboard": [[{"text": "📱 Открыть запись на консультацию", "url": _get_booking_url()}]]}
    send_telegram_message(chat_id, "Нажмите кнопку ниже, чтобы перейти на страницу записи:", keyboard)


def handle_telegram_update(update_data: dict) -> None:
    try:
        if "message" in update_data:
            message = update_data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            username = message.get("from", {}).get("username", "")
            user_id = message.get("from", {}).get("id")
            first_name = message.get("from", {}).get("first_name", "")
            logger.info("TG bot: message chat_id=%s user_id=%s text=%r", chat_id, user_id, (text or "")[:80])
            if text == "/start":
                handle_start_command(chat_id, user_id, username, first_name)
            elif text.startswith("/start link_"):
                token_str = text.replace("/start link_", "").strip()
                if token_str:
                    handle_booking_link_confirm(chat_id, user_id, token_str)
                else:
                    handle_start_command(chat_id, user_id, username, first_name)
            elif text.startswith("/start login_"):
                token_str = text.replace("/start login_", "", 1).strip()
                if token_str:
                    handle_login_token(chat_id, user_id, username, first_name, token_str)
                else:
                    handle_login_via_bot(chat_id)
            elif text.startswith("/start login"):
                handle_login_via_bot(chat_id)
            elif text.startswith("/start connect_spec_"):
                token_str = text.replace("/start connect_spec_", "").strip()
                if token_str:
                    handle_specialist_connect_telegram(chat_id, user_id, token_str)
                else:
                    handle_connect_via_bot(chat_id)
            elif text.startswith("/start connect"):
                handle_connect_via_bot(chat_id)
            elif text in ("/register", "📝 Регистрация"):
                handle_register_command(chat_id)
            elif text in ("/appointments", "📋 Мои записи"):
                handle_appointments_command(chat_id, user_id)
            elif text in ("/help", "❓ Помощь"):
                handle_help_command(chat_id)
            elif text in ("📜 История", "/history"):
                handle_history_command(chat_id, user_id)
            elif text in ("📞 Связаться", "/admin"):
                handle_contact_admin_command(chat_id)
            elif text == "📱 Записаться":
                _send_webapp_button(chat_id)
            elif text == "📅 Ближайшие записи":
                handle_specialist_next_appointments(chat_id, user_id)
            elif text == "📊 Статистика":
                _send_specialist_webapp(chat_id)
            elif text == "🔗 Управление аккаунтами":
                handle_manage_accounts_command(chat_id)
            else:
                send_telegram_message(chat_id, "Неизвестная команда. Нажмите /help.", get_client_reply_keyboard())

        elif "callback_query" in update_data:
            callback_query = update_data["callback_query"]
            callback_query_id = callback_query["id"]
            chat_id = callback_query["message"]["chat"]["id"]
            data = callback_query.get("data", "")
            user_id = callback_query.get("from", {}).get("id")
            if not data.startswith(("booklink_", "spec_confirm_", "login_confirm_")):
                answer_callback_query(callback_query_id)
            if data == "my_appointments":
                answer_callback_query(callback_query_id)
                handle_appointments_command(chat_id, user_id)
            elif data == "history":
                answer_callback_query(callback_query_id)
                handle_history_command(chat_id, user_id)
            elif data.startswith("login_confirm_"):
                handle_login_confirm_callback(
                    chat_id, user_id, callback_query_id,
                    data.replace("login_confirm_", "", 1),
                    callback_query.get("from", {}).get("username", ""),
                    callback_query.get("from", {}).get("first_name", ""),
                )
            elif data.startswith("booklink_"):
                handle_booking_link_callback(chat_id, user_id, callback_query_id, data.replace("booklink_", "", 1))
            elif data.startswith("spec_confirm_"):
                handle_specialist_connect_telegram_callback(chat_id, user_id, callback_query_id, data.replace("spec_confirm_", "", 1))
    except Exception as e:
        logger.exception("TG bot update error: %s", e)


def handle_login_via_bot(chat_id):
    site = get_site_url().rstrip("/")
    keyboard = {"inline_keyboard": [[{"text": "🔐 Войти на сайт", "url": f"{site}/login/"}]]}
    send_telegram_message(
        chat_id,
        "👋 <b>Вход на сайт через Telegram</b>\n\n"
        "Откройте страницу входа на сайте и нажмите «Telegram» — "
        "бот отправит ссылку для подтверждения.",
        keyboard,
    )


def handle_login_token(chat_id, user_id, username, first_name, token_str):
    keyboard = {
        "inline_keyboard": [[{
            "text": "✅ Подтвердить вход",
            "callback_data": f"login_confirm_{token_str}",
        }]]
    }
    send_telegram_message(
        chat_id,
        "🔐 <b>Вход на сайт</b>\n\n"
        "Нажмите кнопку ниже, чтобы подтвердить вход через Telegram.",
        keyboard,
    )


def handle_login_confirm_callback(chat_id, user_id, callback_query_id, token_str, username, first_name):
    answer_callback_query(callback_query_id, "Проверяем...")
    status, data = post_site_api(
        "/api/telegram/confirm-login",
        {
            "token": token_str,
            "telegram_id": user_id,
            "username": username or "",
            "first_name": first_name or "",
        },
        timeout=8,
    )
    try:
        if status == 200 and data and data.get("success"):
            complete_url = data.get("complete_url", "")
            keyboard = {"inline_keyboard": [[{"text": "🌐 Открыть сайт", "url": complete_url}]]} if complete_url else None
            send_telegram_message(
                chat_id,
                "✅ <b>Вход подтверждён.</b>\n\n"
                "Нажмите кнопку ниже, чтобы завершить вход в браузере.",
                keyboard,
            )
        else:
            msg = (data or {}).get("error", "Ссылка недействительна или истекла.")
            answer_callback_query(callback_query_id, msg[:200])
            send_telegram_message(chat_id, f"❌ {msg}")
    except Exception as e:
        logger.warning("Login confirm error: %s", e)
        answer_callback_query(callback_query_id, "Ошибка.")
        send_telegram_message(chat_id, "❌ Ошибка связи с сервером.")


def handle_connect_via_bot(chat_id):
    connect_url = f"{get_site_url().rstrip('/')}/accounts/telegram/login/?process=connect&next=/profile/"
    keyboard = {"inline_keyboard": [[{"text": "🔗 Подключить аккаунт на сайте", "url": connect_url}]]}
    send_telegram_message(chat_id, "👋 <b>Подключение Telegram к аккаунту</b>", keyboard)


def handle_specialist_connect_telegram(chat_id, user_id, token_str):
    keyboard = {"inline_keyboard": [[{"text": "✅ Подтвердить подключение", "callback_data": f"spec_confirm_{token_str}"}]]}
    send_telegram_message(chat_id, "👋 <b>Подключение Telegram для уведомлений специалиста</b>", keyboard)


def handle_specialist_connect_telegram_callback(chat_id, user_id, callback_query_id, token_str):
    answer_callback_query(callback_query_id, "Подключаем...")
    status, data = post_site_api(
        "/api/specialist/connect-telegram",
        {"link_token": token_str, "telegram_id": user_id},
        timeout=8,
    )
    try:
        if status == 200 and data and data.get("success"):
            send_telegram_message(chat_id, "✅ <b>Telegram успешно подключён.</b>")
        else:
            msg = (data or {}).get("error", "Ссылка недействительна.")
            answer_callback_query(callback_query_id, msg[:200])
            send_telegram_message(chat_id, f"❌ Не удалось подключить: {msg}")
    except Exception as e:
        logger.warning("Specialist connect error: %s", e)
        answer_callback_query(callback_query_id, "Ошибка.")
        send_telegram_message(chat_id, "❌ Ошибка связи с сервером.")


def handle_booking_link_confirm(chat_id, user_id, token_str):
    keyboard = {"inline_keyboard": [[{"text": "✅ Подтвердить и получать уведомления", "callback_data": f"booklink_{token_str}"}]]}
    send_telegram_message(chat_id, "📌 <b>Подтвердите привязку Telegram к вашей записи</b>", keyboard)
    return True


def handle_booking_link_callback(chat_id, user_id, callback_query_id, token_str):
    answer_callback_query(callback_query_id, "Привязываем...")
    status, data = post_site_api(
        "/api/booking/confirm-telegram",
        {"link_token": token_str, "telegram_id": user_id},
        timeout=8,
    )
    try:
        if status == 200 and data and data.get("success"):
            send_telegram_message(chat_id, "✅ Ваш Telegram привязан к записи.")
        else:
            send_telegram_message(chat_id, "❌ Ссылка недействительна или истекла.")
    except Exception as e:
        logger.warning("Booking confirm error: %s", e)
        answer_callback_query(callback_query_id, "Ошибка.")


def handle_start_command(chat_id, user_id, username, first_name):
    admin_username = settings.admin_telegram_username.lstrip("@")
    booking_url = _get_booking_url()
    keyboard = {
        "inline_keyboard": [
            [{"text": "📱 Записаться на консультацию", "url": booking_url}],
            [{"text": "📋 Мои записи", "callback_data": "my_appointments"}, {"text": "📜 История", "callback_data": "history"}],
            [{"text": "📞 Связаться с администрацией", "url": f"https://t.me/{admin_username}"}, {"text": "❓ Помощь", "callback_data": "help"}],
        ]
    }
    send_telegram_message(chat_id, f"👋 Добро пожаловать, {first_name}!", keyboard)
    send_telegram_message(chat_id, "Используйте кнопки ниже.", get_client_reply_keyboard())

    def _maybe_specialist_menu() -> None:
        ok, data = _fetch_site_api("/api/telegram/specialist-bookings/", {"telegram_chat_id": str(chat_id)})
        if not (ok and data and data.get("is_specialist")):
            return
        spec_keyboard = {
            "inline_keyboard": [
                [{"text": "📅 Показать 5 ближайших (в чат)", "callback_data": "spec_next"}],
            ]
        }
        send_telegram_message(
            chat_id,
            f"👋 {first_name}, вы вошли как <b>специалист</b>.",
            spec_keyboard,
        )
        send_telegram_message(chat_id, "Кнопки специалиста внизу экрана.", get_specialist_reply_keyboard())

    threading.Thread(target=_maybe_specialist_menu, daemon=True).start()


def handle_register_command(chat_id):
    site = get_site_url().rstrip("/")
    keyboard = {
        "inline_keyboard": [
            [{"text": "📝 Перейти на страницу регистрации", "url": f"{site}/register/"}],
            [{"text": "📱 Записаться (без регистрации)", "url": _get_booking_url()}],
        ]
    }
    send_telegram_message(chat_id, "📝 <b>Регистрация</b>\n\nПерейдите на сайт по кнопке ниже.", keyboard)


def handle_history_command(chat_id, user_id):
    ok, data = _fetch_site_api("/api/telegram/client-bookings/", {"telegram_id": user_id})
    if ok and data and data.get("bookings"):
        bookings = data["bookings"]
        names = [b.get("consultant_name") or "Специалист" for b in bookings]
        by_name = Counter(names)
        lines = ["📜 <b>К кому вы уже записывались:</b>\n"]
        for name, cnt in by_name.most_common():
            _raz = "раз" if cnt == 1 else ("раза" if 2 <= cnt <= 4 else "раз")
            lines.append(f"• {name} — {cnt} {_raz}")
        send_telegram_message(chat_id, "\n".join(lines), get_client_reply_keyboard())
        return
    send_telegram_message(chat_id, "У вас пока нет записей.", get_client_reply_keyboard())


def handle_contact_admin_command(chat_id):
    admin = settings.admin_telegram_username.lstrip("@")
    keyboard = {"inline_keyboard": [[{"text": "📞 Написать администрации", "url": f"https://t.me/{admin}"}]]}
    send_telegram_message(chat_id, "По вопросам обращайтесь к администрации:", keyboard)


def _send_specialist_webapp(chat_id):
    url = f"{get_site_url().rstrip('/')}/calendars/"
    keyboard = {"inline_keyboard": [[{"text": "Открыть на сайте", "url": url}]]}
    send_telegram_message(chat_id, "📊 Откройте календари на сайте:", keyboard)


def handle_manage_accounts_command(chat_id):
    url = f"{get_site_url().rstrip('/')}/accounts/social/connections/"
    keyboard = {"inline_keyboard": [[{"text": "🔗 Управление аккаунтами", "url": url}]]}
    send_telegram_message(chat_id, "Управление способами входа на сайте:", keyboard)


def handle_appointments_command(chat_id, user_id):
    keyboard = {"inline_keyboard": [[{"text": "📱 Записаться", "url": _get_booking_url()}]]}
    ok, data = _fetch_site_api("/api/telegram/client-bookings/", {"telegram_id": user_id})
    if ok and data and data.get("bookings"):
        status_emoji = {"pending": "⏳", "confirmed": "✅", "completed": "✔️"}
        message = "📋 <b>Ваши записи:</b>\n\n"
        for b in data["bookings"][:15]:
            em = status_emoji.get(b.get("status"), "📅")
            message += f"{em} <b>{b.get('date', '')} {b.get('time', '')}</b>\n"
            message += f"👤 {b.get('consultant_name', '—')}\n"
            message += f"💼 {b.get('service_name', 'Консультация')}\n\n"
        send_telegram_message(chat_id, message, keyboard)
        return
    send_telegram_message(chat_id, "📋 У вас пока нет записей. Используйте кнопку ниже.", keyboard)


def handle_help_command(chat_id):
    admin = settings.admin_telegram_username.lstrip("@")
    site = get_site_url().rstrip("/")
    keyboard = {
        "inline_keyboard": [
            [{"text": "📱 Записаться", "url": _get_booking_url()}, {"text": "📋 Мои записи", "callback_data": "my_appointments"}],
            [{"text": "📝 Регистрация", "url": f"{site}/register/"}, {"text": "📞 Связаться", "url": f"https://t.me/{admin}"}],
        ]
    }
    send_telegram_message(chat_id, "📖 <b>Справка:</b>\n/start, /register, /appointments, /history, /help", keyboard)


def handle_specialist_next_appointments(chat_id, user_id):
    ok, data = _fetch_site_api("/api/telegram/specialist-bookings/", {"telegram_chat_id": str(chat_id)})
    if ok and data and data.get("bookings"):
        upcoming = [b for b in data["bookings"] if b.get("is_upcoming")][:5]
        if upcoming:
            text = "📅 <b>5 ближайших записей:</b>\n\n"
            for b in upcoming:
                text += f"• <b>{b.get('date', '')} {b.get('time', '')}</b> — {b.get('client_name', '—')}\n"
                text += f"  Услуга: {b.get('service_name', 'Консультация')}\n\n"
            send_telegram_message(chat_id, text)
            return
    send_telegram_message(chat_id, "📭 Ближайших записей нет.")


def verify_bot_identity() -> None:
    """Warn if TELEGRAM_BOT_USERNAME does not match the token (common misconfiguration)."""
    if not TELEGRAM_API_URL:
        return
    expected = settings.telegram_bot_username.lstrip("@").lower()
    try:
        r = _tg_session.get(f"{TELEGRAM_API_URL}/getMe", timeout=(5, 10))
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            return
        actual = (payload.get("result") or {}).get("username", "").lower()
        if actual:
            logger.info("Telegram bot identity: @%s", actual)
        if expected and actual and expected != actual:
            logger.error(
                "TELEGRAM_BOT_USERNAME=%s but token belongs to @%s — update GitHub Secret TELEGRAM_BOT_USERNAME",
                settings.telegram_bot_username,
                actual,
            )
    except Exception as exc:
        logger.warning("Could not verify bot identity: %s", exc)


def _clear_webhook() -> None:
    if not TELEGRAM_API_URL:
        return
    try:
        r = _tg_session.post(f"{TELEGRAM_API_URL}/deleteWebhook", json={"drop_pending_updates": False}, timeout=(5, 10))
        if r.ok:
            logger.info("deleteWebhook OK (long polling mode)")
        else:
            logger.warning("deleteWebhook HTTP %s", r.status_code)
    except Exception as exc:
        logger.warning("deleteWebhook failed: %s", exc)


def run_long_polling() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    verify_bot_identity()
    _clear_webhook()
    url = f"{TELEGRAM_API_URL}/getUpdates"
    offset = 0
    error_count = 0
    conflict_count = 0
    logger.info("Bot started. SITE_URL=%s SITE_INTERNAL_URL=%s", settings.site_url, settings.site_internal_url)
    while True:
        try:
            response = _tg_session.get(
                url,
                params={"offset": offset, "timeout": 20, "allowed_updates": ["message", "callback_query"]},
                timeout=(5, 30),
            )
            if response.status_code == 409:
                conflict_count += 1
                logger.error(
                    "409 Conflict: another bot process is polling getUpdates (duplicate instance). "
                    "Run: ./scripts/stop_bot.sh && ./scripts/run_bot.sh"
                )
                if conflict_count >= 6:
                    logger.critical("Too many 409 errors — exiting so deploy can start a single instance")
                    raise SystemExit(1)
                time.sleep(15)
                continue
            conflict_count = 0
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                error_count += 1
                time.sleep(min(5 * error_count, 30))
                continue
            error_count = 0
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                _update_pool.submit(handle_telegram_update, update)
        except KeyboardInterrupt:
            break
        except SystemExit:
            raise
        except requests.exceptions.RequestException as e:
            error_count += 1
            logger.error("Network error: %s", e)
            time.sleep(min(10 * error_count, 60))
        except Exception as e:
            error_count += 1
            logger.error("Unexpected error: %s", e)
            time.sleep(min(10 * error_count, 60))
