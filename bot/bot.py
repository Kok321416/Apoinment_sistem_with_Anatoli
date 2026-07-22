"""Telegram bot for appointment system (FastAPI backend)."""
import json
import logging
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

from bot.api_client import post_site_api
from bot.config import get_bot_settings
from bot.copy import (
    CONNECT_SITE,
    HELP_TEXT,
    LOGIN_OPEN_SITE,
    MODE_PICK_TEXT,
    SWITCH_ROLE_HINT,
    WELCOME_CLIENT,
    WELCOME_SPECIALIST,
)

logger = logging.getLogger(__name__)
settings = get_bot_settings()
TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.telegram_bot_token}" if settings.telegram_bot_token else None
_tg_session = requests.Session()
_update_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tg-update")
_chat_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
_chat_locks_guard = threading.Lock()


def get_site_url() -> str:
    return settings.site_url


def _mini_app_url(path: str = "/tg/") -> str:
    base = get_site_url().rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _fetch_site_api(path: str, json_data: dict) -> tuple[bool, dict | None]:
    # Routes are registered without trailing slash; normalize to avoid redirects.
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    status, data = post_site_api(path, json_data)
    if status != 200 or not data:
        return False, None
    return data.get("success") is True, data


def send_telegram_message(chat_id, text, reply_markup=None, *, retries: int = 2) -> bool:
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = _tg_session.post(f"{TELEGRAM_API_URL}/sendMessage", json=data, timeout=(5, 10))
            if response.status_code == 429:
                retry_after = 1
                try:
                    retry_after = int((response.json().get("parameters") or {}).get("retry_after") or 1)
                except Exception:
                    pass
                time.sleep(min(retry_after, 5))
                continue
            response.raise_for_status()
            return True
        except Exception as e:
            last_error = e
            time.sleep(0.4 * (attempt + 1))
    logger.error("Telegram send error: %s", last_error)
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


def get_client_reply_keyboard(*, can_switch: bool = False):
    rows = [
        [{"text": "📱 Записаться"}, {"text": "📋 Мои записи"}],
        [{"text": "📝 Регистрация"}, {"text": "📜 История"}, {"text": "📞 Связаться"}],
        [{"text": "❓ Помощь"}],
    ]
    if can_switch:
        rows.append([{"text": "🔄 Сменить роль"}])
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "persistent": True,
    }


def get_specialist_reply_keyboard(*, can_switch: bool = False):
    rows = [
        [{"text": "📅 Ближайшие записи"}, {"text": "📊 Статистика"}],
        [{"text": "🔗 Управление аккаунтами"}],
        [{"text": "❓ Помощь"}],
    ]
    if can_switch:
        rows.append([{"text": "🔄 Сменить роль"}])
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "persistent": True,
    }


def _mode_picker_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "👤 Я клиент", "callback_data": "mode_client"},
                {"text": "💼 Я специалист", "callback_data": "mode_specialist"},
            ]
        ]
    }


def _fetch_capabilities(chat_id, user_id) -> dict:
    ok, data = _fetch_site_api(
        "/api/telegram/capabilities",
        {"telegram_id": user_id, "telegram_chat_id": str(chat_id)},
    )
    if ok and data:
        return data
    return {
        "is_client": True,
        "is_specialist": False,
        "dual": False,
        "mode": "client",
        "needs_picker": False,
    }


def _set_ui_mode(chat_id, mode: str) -> bool:
    ok, data = _fetch_site_api(
        "/api/telegram/ui-mode",
        {"telegram_chat_id": str(chat_id), "mode": mode},
    )
    return bool(ok and data and data.get("success"))


def _apply_mode_ui(chat_id, user_id, first_name, mode: str, *, dual: bool):
    name = first_name or "друг"
    can_switch = dual
    if mode == "specialist":
        spec_keyboard = {
            "inline_keyboard": [
                [_web_app_button("📊 Кабинет специалиста", _mini_app_url("/dashboard/"))],
                [{"text": "📅 Показать 5 ближайших (в чат)", "callback_data": "spec_next"}],
            ]
        }
        send_telegram_message(chat_id, WELCOME_SPECIALIST.format(name=name), spec_keyboard)
        send_telegram_message(
            chat_id,
            "Кнопки специалиста внизу экрана." + (f"\n{SWITCH_ROLE_HINT}" if can_switch else ""),
            get_specialist_reply_keyboard(can_switch=can_switch),
        )
    else:
        keyboard = {
            "inline_keyboard": [
                [_web_app_button("📱 Открыть сервис в Telegram", _mini_app_url("/tg/"))],
                [_web_app_button("📅 Записаться", _mini_app_url("/book/"))],
                [
                    {"text": "📋 Мои записи", "callback_data": "my_appointments"},
                    {"text": "📜 История", "callback_data": "history"},
                ],
            ]
        }
        send_telegram_message(chat_id, WELCOME_CLIENT.format(name=name), keyboard)
        send_telegram_message(
            chat_id,
            "Используйте кнопки ниже." + (f"\n{SWITCH_ROLE_HINT}" if can_switch else ""),
            get_client_reply_keyboard(can_switch=can_switch),
        )


def _keyboard_for_user(chat_id, user_id):
    caps = _fetch_capabilities(chat_id, user_id)
    dual = bool(caps.get("dual"))
    mode = caps.get("mode") or "client"
    if mode == "specialist" and caps.get("is_specialist"):
        return get_specialist_reply_keyboard(can_switch=dual)
    return get_client_reply_keyboard(can_switch=dual)


def _get_booking_url() -> str:
    return f"{get_site_url().rstrip('/')}/book/"


def _web_app_button(text: str, url: str) -> dict:
    """Inline button that opens URL as Telegram Mini App."""
    return {"text": text, "web_app": {"url": url}}


def _url_button(text: str, url: str) -> dict:
    return {"text": text, "url": url}


def _send_webapp_button(chat_id):
    keyboard = {
        "inline_keyboard": [[
            _web_app_button("📱 Открыть запись", _mini_app_url("/book/")),
        ]]
    }
    send_telegram_message(
        chat_id,
        "Нажмите кнопку ниже — сайт откроется <b>внутри Telegram</b>:",
        keyboard,
    )


def _lock_for_chat(chat_id: int) -> threading.Lock:
    with _chat_locks_guard:
        return _chat_locks[chat_id]


def _process_update_ordered(update_data: dict) -> None:
    chat_id = None
    try:
        if "message" in update_data:
            chat_id = update_data["message"]["chat"]["id"]
        elif "callback_query" in update_data:
            chat_id = update_data["callback_query"]["message"]["chat"]["id"]
    except Exception:
        chat_id = None
    if chat_id is None:
        handle_telegram_update(update_data)
        return
    with _lock_for_chat(int(chat_id)):
        handle_telegram_update(update_data)


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
            elif text in ("🔄 Сменить роль", "/mode"):
                handle_switch_role(chat_id, user_id, first_name)
            else:
                send_telegram_message(
                    chat_id,
                    "Неизвестная команда. Нажмите /help.",
                    _keyboard_for_user(chat_id, user_id),
                )

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
            elif data == "help":
                answer_callback_query(callback_query_id)
                handle_help_command(chat_id)
            elif data == "spec_next":
                answer_callback_query(callback_query_id)
                handle_specialist_next_appointments(chat_id, user_id)
            elif data in ("mode_client", "mode_specialist"):
                answer_callback_query(callback_query_id)
                mode = "client" if data == "mode_client" else "specialist"
                handle_mode_chosen(
                    chat_id,
                    user_id,
                    callback_query.get("from", {}).get("first_name", ""),
                    mode,
                )
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
                handle_specialist_connect_telegram_callback(
                    chat_id, user_id, callback_query_id, data.replace("spec_confirm_", "", 1)
                )
            else:
                answer_callback_query(callback_query_id, "Неизвестная кнопка")
    except Exception as e:
        logger.exception("TG bot update error: %s", e)


def handle_login_via_bot(chat_id):
    site = get_site_url().rstrip("/")
    keyboard = {"inline_keyboard": [[_url_button("🔐 Войти на сайт", f"{site}/login/")]]}
    send_telegram_message(
        chat_id,
        "👋 <b>Вход на сайт через Телеграм</b>\n\n"
        "Откройте страницу входа на сайте и нажмите «Телеграм» — "
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
        "Нажмите кнопку ниже, чтобы подтвердить вход через Телеграм.",
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
            keyboard = {"inline_keyboard": [[_url_button(LOGIN_OPEN_SITE, complete_url)]]} if complete_url else None
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
    keyboard = {"inline_keyboard": [[_url_button(CONNECT_SITE, connect_url)]]}
    send_telegram_message(chat_id, "👋 <b>Подключение Телеграм к аккаунту</b>", keyboard)


def handle_specialist_connect_telegram(chat_id, user_id, token_str):
    keyboard = {
        "inline_keyboard": [[{"text": "✅ Подтвердить подключение", "callback_data": f"spec_confirm_{token_str}"}]]
    }
    send_telegram_message(chat_id, "👋 <b>Подключение Телеграм для уведомлений специалиста</b>", keyboard)


def handle_specialist_connect_telegram_callback(chat_id, user_id, callback_query_id, token_str):
    answer_callback_query(callback_query_id, "Подключаем...")
    status, data = post_site_api(
        "/api/specialist/connect-telegram",
        {"link_token": token_str, "telegram_id": user_id},
        timeout=8,
    )
    try:
        if status == 200 and data and data.get("success"):
            send_telegram_message(
                chat_id,
                "✅ <b>Телеграм успешно подключён.</b>\n\n"
                "Нажмите /start или /mode, чтобы выбрать интерфейс специалиста.",
            )
        else:
            msg = (data or {}).get("error", "Ссылка недействительна.")
            answer_callback_query(callback_query_id, msg[:200])
            send_telegram_message(chat_id, f"❌ Не удалось подключить: {msg}")
    except Exception as e:
        logger.warning("Specialist connect error: %s", e)
        answer_callback_query(callback_query_id, "Ошибка.")
        send_telegram_message(chat_id, "❌ Ошибка связи с сервером.")


def handle_booking_link_confirm(chat_id, user_id, token_str):
    keyboard = {
        "inline_keyboard": [[{
            "text": "✅ Подтвердить и получать уведомления",
            "callback_data": f"booklink_{token_str}",
        }]]
    }
    send_telegram_message(chat_id, "📌 <b>Подтвердите привязку Телеграм к вашей записи</b>", keyboard)
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
            send_telegram_message(chat_id, "✅ Ваш Телеграм привязан к записи.")
        else:
            send_telegram_message(chat_id, "❌ Ссылка недействительна или истекла.")
    except Exception as e:
        logger.warning("Booking confirm error: %s", e)
        answer_callback_query(callback_query_id, "Ошибка.")


def handle_start_command(chat_id, user_id, username, first_name):
    caps = _fetch_capabilities(chat_id, user_id)
    dual = bool(caps.get("dual"))
    needs_picker = bool(caps.get("needs_picker"))
    mode = caps.get("mode")

    if needs_picker or (dual and not mode):
        send_telegram_message(chat_id, MODE_PICK_TEXT, _mode_picker_keyboard())
        return

    if dual and mode in ("client", "specialist"):
        _apply_mode_ui(chat_id, user_id, first_name, mode, dual=True)
        return

    if caps.get("is_specialist") and not caps.get("is_client"):
        _apply_mode_ui(chat_id, user_id, first_name, "specialist", dual=False)
        return

    _apply_mode_ui(chat_id, user_id, first_name, "client", dual=False)


def handle_switch_role(chat_id, user_id, first_name):
    caps = _fetch_capabilities(chat_id, user_id)
    if not caps.get("dual"):
        send_telegram_message(
            chat_id,
            "Сейчас доступен только один режим. Подключите уведомления специалиста в кабинете → Интеграции "
            "или запишитесь как клиент, чтобы появился второй режим.",
            _keyboard_for_user(chat_id, user_id),
        )
        return
    send_telegram_message(chat_id, MODE_PICK_TEXT, _mode_picker_keyboard())


def handle_mode_chosen(chat_id, user_id, first_name, mode: str):
    if not _set_ui_mode(chat_id, mode):
        send_telegram_message(chat_id, "Не удалось сохранить режим. Попробуйте /start ещё раз.")
        return
    caps = _fetch_capabilities(chat_id, user_id)
    _apply_mode_ui(chat_id, user_id, first_name, mode, dual=bool(caps.get("dual")))


def handle_register_command(chat_id):
    site = get_site_url().rstrip("/")
    keyboard = {
        "inline_keyboard": [
            [_web_app_button("📝 Регистрация", f"{site}/register/")],
            [_web_app_button("📱 Записаться без регистрации", _mini_app_url("/book/"))],
        ]
    }
    send_telegram_message(chat_id, "📝 <b>Регистрация</b>\n\nОткроется внутри Telegram.", keyboard)


def handle_history_command(chat_id, user_id):
    caps = _fetch_capabilities(chat_id, user_id)
    if not caps.get("is_client"):
        send_telegram_message(
            chat_id,
            "История доступна в режиме клиента.",
            _keyboard_for_user(chat_id, user_id),
        )
        return
    ok, data = _fetch_site_api("/api/telegram/client-bookings", {"telegram_id": user_id})
    kb = _keyboard_for_user(chat_id, user_id)
    if ok and data and data.get("bookings"):
        bookings = data["bookings"]
        names = [b.get("consultant_name") or "Специалист" for b in bookings]
        by_name = Counter(names)
        lines = ["📜 <b>К кому вы уже записывались:</b>\n"]
        for name, cnt in by_name.most_common():
            _raz = "раз" if cnt == 1 else ("раза" if 2 <= cnt <= 4 else "раз")
            lines.append(f"• {name} - {cnt} {_raz}")
        send_telegram_message(chat_id, "\n".join(lines), kb)
        return
    send_telegram_message(chat_id, "У вас пока нет записей.", kb)


def handle_contact_admin_command(chat_id):
    admin = settings.admin_telegram_username.lstrip("@")
    keyboard = {"inline_keyboard": [[_url_button("📞 Написать администрации", f"https://t.me/{admin}")]]}
    send_telegram_message(chat_id, "По вопросам обращайтесь к администрации:", keyboard)


def _send_specialist_webapp(chat_id):
    keyboard = {
        "inline_keyboard": [[
            _web_app_button("Открыть календари", _mini_app_url("/calendars/")),
        ]]
    }
    send_telegram_message(chat_id, "📊 Календари откроются внутри Telegram:", keyboard)


def handle_manage_accounts_command(chat_id):
    url = f"{get_site_url().rstrip('/')}/accounts/social/connections/"
    keyboard = {"inline_keyboard": [[_web_app_button("🔗 Управление аккаунтами", url)]]}
    send_telegram_message(chat_id, "Управление способами входа:", keyboard)


def handle_appointments_command(chat_id, user_id):
    caps = _fetch_capabilities(chat_id, user_id)
    if not caps.get("is_client"):
        send_telegram_message(
            chat_id,
            "Раздел «Мои записи» доступен в режиме клиента. Нажмите «Сменить роль» или /mode.",
            _keyboard_for_user(chat_id, user_id),
        )
        return
    keyboard = {"inline_keyboard": [[_web_app_button("📱 Записаться", _mini_app_url("/book/"))]]}
    ok, data = _fetch_site_api("/api/telegram/client-bookings", {"telegram_id": user_id})
    if ok and data and data.get("bookings"):
        status_emoji = {"pending": "⏳", "confirmed": "✅", "completed": "✔️"}
        message = "📋 <b>Ваши записи:</b>\n\n"
        for b in data["bookings"][:15]:
            em = status_emoji.get(b.get("status"), "📅")
            message += f"{em} <b>{b.get('date', '')} {b.get('time', '')}</b>\n"
            message += f"👤 {b.get('consultant_name', '-')}\n"
            message += f"💼 {b.get('service_name', 'Консультация')}\n\n"
        send_telegram_message(chat_id, message, keyboard)
        return
    send_telegram_message(chat_id, "📋 У вас пока нет записей. Используйте кнопку ниже.", keyboard)


def handle_help_command(chat_id):
    admin = settings.admin_telegram_username.lstrip("@")
    site = get_site_url().rstrip("/")
    keyboard = {
        "inline_keyboard": [
            [
                _web_app_button("📱 Записаться", _mini_app_url("/book/")),
                {"text": "📋 Мои записи", "callback_data": "my_appointments"},
            ],
            [
                _web_app_button("📝 Регистрация", f"{site}/register/"),
                _url_button("📞 Связаться", f"https://t.me/{admin}"),
            ],
            [_web_app_button("🏠 Открыть сервис", _mini_app_url("/tg/"))],
        ]
    }
    send_telegram_message(chat_id, HELP_TEXT.format(site_url=site), keyboard)


def handle_specialist_next_appointments(chat_id, user_id):
    caps = _fetch_capabilities(chat_id, user_id)
    if not caps.get("is_specialist"):
        send_telegram_message(
            chat_id,
            "Ближайшие записи специалиста доступны после подключения Телеграм в кабинете → Интеграции.",
            _keyboard_for_user(chat_id, user_id),
        )
        return
    ok, data = _fetch_site_api("/api/telegram/specialist-bookings", {"telegram_chat_id": str(chat_id)})
    kb = _keyboard_for_user(chat_id, user_id)
    if ok and data and data.get("bookings"):
        upcoming = [b for b in data["bookings"] if b.get("is_upcoming")][:5]
        if upcoming:
            text = "📅 <b>5 ближайших записей:</b>\n\n"
            for b in upcoming:
                text += f"• <b>{b.get('date', '')} {b.get('time', '')}</b> - {b.get('client_name', '-')}\n"
                text += f"  Услуга: {b.get('service_name', 'Консультация')}\n\n"
            send_telegram_message(chat_id, text, kb)
            return
    send_telegram_message(chat_id, "📭 Ближайших записей нет.", kb)


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
        r = _tg_session.post(
            f"{TELEGRAM_API_URL}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=(5, 10),
        )
        if r.ok:
            logger.info("deleteWebhook OK (long polling mode)")
        else:
            logger.warning("deleteWebhook HTTP %s", r.status_code)
    except Exception as exc:
        logger.warning("deleteWebhook failed: %s", exc)


def _setup_menu_button() -> None:
    """Set chat Menu Button to open Mini App (appears next to message input)."""
    if not TELEGRAM_API_URL:
        return
    menu_url = _mini_app_url("/tg/")
    try:
        r = _tg_session.post(
            f"{TELEGRAM_API_URL}/setChatMenuButton",
            json={
                "menu_button": {
                    "type": "web_app",
                    "text": "Открыть",
                    "web_app": {"url": menu_url},
                }
            },
            timeout=(5, 10),
        )
        if r.ok and (r.json() or {}).get("ok"):
            logger.info("setChatMenuButton OK -> %s", menu_url)
        else:
            logger.warning("setChatMenuButton failed: %s", r.text[:300])
    except Exception as exc:
        logger.warning("setChatMenuButton error: %s", exc)


def _warn_security_config() -> None:
    if not settings.bot_api_secret:
        logger.warning(
            "BOT_API_SECRET is empty — bot falls back to X-Bot-Token. "
            "Set BOT_API_SECRET on server and in GitHub secrets for production."
        )


def run_long_polling() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    _warn_security_config()
    verify_bot_identity()
    _clear_webhook()
    _setup_menu_button()
    url = f"{TELEGRAM_API_URL}/getUpdates"
    offset = 0
    error_count = 0
    conflict_count = 0
    logger.info(
        "Bot started. SITE_URL=%s SITE_INTERNAL_URL=%s",
        settings.site_url,
        settings.site_internal_url,
    )
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
                _update_pool.submit(_process_update_ordered, update)
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
