"""
Telegram бот для системы записи на консультации
"""
import json
import logging
import uuid
from django.conf import settings
from django.utils import timezone
from bookings.models import UserProfile, Appointment, Specialist, Service, TimeSlot, TelegramLinkToken
from django.contrib.auth.models import User
import requests

from telegram_bot.models import TelegramClient, TelegramClientSpecialist

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

def get_site_url():
    """Получить URL сайта для мини-приложения"""
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')


def _fetch_site_api(path, json_data):
    """
    Вызов API основного сайта (consultant_menu). Заголовок X-Bot-Token для доступа.
    Возвращает (success: bool, data: dict или None). При ошибке data может содержать error из ответа.
    """
    site_url = get_site_url().rstrip('/')
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or ''
    if not token or not site_url.startswith('http'):
        return False, None
    url = f"{site_url}{path}"
    try:
        r = requests.post(url, json=json_data, timeout=10, headers={'X-Bot-Token': token})
        try:
            data = r.json() if r.text else {}
        except Exception:
            data = {}
        if r.status_code != 200:
            return False, data
        return data.get('success') is True, data
    except Exception as e:
        logger.debug("Site API %s: %s", path, e)
        return False, None


def send_telegram_message(chat_id, text, reply_markup=None):
    """Отправить сообщение в Telegram. reply_markup — dict (inline_keyboard или keyboard)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен")
        return False
    
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        # Telegram API принимает reply_markup как JSON-строку
        data['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
        return False


def answer_callback_query(callback_query_id, text=None):
    """Убрать «загрузку» после нажатия inline-кнопки."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {'callback_query_id': callback_query_id}
    if text:
        payload['text'] = text[:200]
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Ошибка answerCallbackQuery: {e}")
        return False


def edit_telegram_message(chat_id, message_id, text, remove_keyboard=True):
    """Изменить текст сообщения. Если remove_keyboard=True — убрать inline-кнопки (передаём пустой inline_keyboard)."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
    }
    if remove_keyboard:
        payload['reply_markup'] = json.dumps({'inline_keyboard': []})
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception as e:
        logger.error("Ошибка editMessageText: %s", e)
        return False


def get_main_reply_keyboard():
    """Постоянное меню внизу экрана для клиентов (кнопки всегда видны)."""
    return get_client_reply_keyboard()


def get_client_reply_keyboard():
    """Меню клиента: запись, мои записи, регистрация, история, связь, помощь."""
    return {
        'keyboard': [
            [{'text': '📱 Записаться'}, {'text': '📋 Мои записи'}],
            [{'text': '📝 Регистрация'}, {'text': '📜 История'}, {'text': '📞 Связаться'}],
            [{'text': '❓ Помощь'}],
        ],
        'resize_keyboard': True,
        'persistent': True,
    }


def get_specialist_reply_keyboard():
    """Меню специалиста: записи, клиенты, ближайшие записи, статистика, управление, помощь."""
    return {
        'keyboard': [
            [{'text': '📋 Записи'}, {'text': '👥 Клиенты'}],
            [{'text': '📅 Ближайшие записи'}, {'text': '📊 Статистика'}],
            [{'text': '🔗 Управление аккаунтами'}, {'text': '❓ Помощь'}],
        ],
        'resize_keyboard': True,
        'persistent': True,
    }


def send_appointment_notification(appointment):
    """Отправить уведомление о записи на консультацию"""
    if not appointment.client_telegram:
        return False
    
    telegram_id = None
    
    if appointment.client:
        try:
            profile = appointment.client.profile
            if profile.telegram_id:
                telegram_id = profile.telegram_id
        except UserProfile.DoesNotExist:
            pass
    
    if not telegram_id:
        logger.warning(f"Не найден telegram_id для клиента {appointment.client_name}")
        return False
    
    specialist_name = appointment.specialist.user.get_full_name() or appointment.specialist.user.username
    service_name = appointment.service.name if appointment.service else "Консультация"
    date_str = appointment.appointment_date.strftime("%d.%m.%Y %H:%M")
    
    message = f"""
🎉 <b>Запись подтверждена!</b>

📅 <b>Дата и время:</b> {date_str}
👤 <b>Специалист:</b> {specialist_name}
💼 <b>Услуга:</b> {service_name}
⏱ <b>Длительность:</b> {appointment.duration} минут

📍 <b>Место проведения:</b> Уточняется

Если у вас возникли вопросы, свяжитесь с нами.
"""
    
    # Кнопки для управления записью
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📋 Мои записи', 'callback_data': 'my_appointments'},
                {'text': '📱 Записаться', 'url': _get_booking_url()}
            ],
            [
                {'text': '❌ Отменить', 'callback_data': f'cancel_{appointment.id}'}
            ]
        ]
    }
    
    return send_telegram_message(telegram_id, message, keyboard)


def send_admin_message(telegram_id, message):
    """Отправить информационное сообщение от администрации"""
    return send_telegram_message(telegram_id, f"📢 <b>Сообщение от администрации:</b>\n\n{message}")


def _get_booking_url():
    """Ссылка на страницу записи (сайт appoinment_sistem: /book/ → редирект на первый календарь)."""
    return f"{get_site_url().rstrip('/')}/book/"


def _send_webapp_button(chat_id):
    """Отправить сообщение с кнопкой перехода на страницу записи (открывается в браузере)."""
    booking_url = _get_booking_url()
    keyboard = {
        'inline_keyboard': [[{'text': '📱 Открыть запись на консультацию', 'url': booking_url}]]
    }
    send_telegram_message(chat_id, "Нажмите кнопку ниже, чтобы перейти на страницу записи:", keyboard)


def handle_telegram_update(update_data):
    """Обработка обновлений от Telegram"""
    try:
        if 'message' in update_data:
            message = update_data['message']
            chat_id = message['chat']['id']
            text = message.get('text', '')
            username = message.get('from', {}).get('username', '')
            user_id = message.get('from', {}).get('id')
            first_name = message.get('from', {}).get('first_name', '')
            logger.info("TG bot: сообщение chat_id=%s user_id=%s text=%r", chat_id, user_id, (text or '')[:80])
            if text == '/start':
                handle_start_command(chat_id, user_id, username, first_name)
            elif text.startswith('/start link_'):
                token_str = text.replace('/start link_', '').strip()
                if token_str and handle_link_token(chat_id, user_id, username, first_name, token_str):
                    pass
                elif token_str and handle_booking_link_confirm(chat_id, user_id, token_str):
                    pass
                else:
                    handle_start_command(chat_id, user_id, username, first_name)
            elif text.startswith('/start login') or text == '/start login':
                handle_login_via_bot(chat_id)
            elif text.startswith('/start connect_spec_'):
                token_str = text.replace('/start connect_spec_', '').strip()
                if token_str:
                    handle_specialist_connect_telegram(chat_id, user_id, token_str)
                else:
                    handle_connect_via_bot(chat_id)
            elif text.startswith('/start connect') or text == '/start connect':
                handle_connect_via_bot(chat_id)
            elif text == '/register' or text == '📝 Регистрация':
                handle_register_command(chat_id, user_id, username, first_name)
            elif text == '/appointments' or text == '📋 Мои записи':
                handle_appointments_command(chat_id, user_id)
            elif text == '/help' or text == '❓ Помощь':
                handle_help_command(chat_id)
            elif text == '📜 История' or text == '/history':
                handle_history_command(chat_id, user_id)
            elif text == '📞 Связаться' or text == '/admin':
                handle_contact_admin_command(chat_id)
            elif text == '📱 Записаться':
                _send_webapp_button(chat_id)
            elif text == '📋 Записи':
                handle_specialist_bookings_list(chat_id, user_id)
            elif text == '👥 Клиенты':
                handle_specialist_clients_list(chat_id, user_id)
            elif text == '📅 Ближайшие записи':
                handle_specialist_next_appointments(chat_id, user_id)
            elif text == '📊 Статистика':
                _send_specialist_webapp(chat_id, 'stats')
            elif text == '🔗 Управление аккаунтами':
                handle_manage_accounts_command(chat_id)
            else:
                send_telegram_message(chat_id, "Неизвестная команда. Нажмите кнопку внизу или /help.", get_main_reply_keyboard())
        
        elif 'callback_query' in update_data:
            callback_query = update_data['callback_query']
            callback_query_id = callback_query['id']
            chat_id = callback_query['message']['chat']['id']
            data = callback_query.get('data', '')
            user_id = callback_query.get('from', {}).get('id')
            logger.info("TG bot: callback chat_id=%s user_id=%s data=%r", chat_id, user_id, (data or '')[:60])
            # Не отвечаем сразу для кнопок, которые показывают свой текст (иначе второй answer не сработает)
            if not data.startswith('booklink_') and not data.startswith('spec_confirm_') and not data.startswith('spec_bok_ok_') and not data.startswith('spec_bok_no_'):
                answer_callback_query(callback_query_id)

            if data == 'my_appointments':
                user_id = callback_query['from']['id']
                handle_appointments_command(chat_id, user_id)
            elif data == 'spec_next':
                user_id = callback_query['from']['id']
                handle_specialist_next_appointments(chat_id, user_id)
            elif data == 'help':
                handle_help_command(chat_id)
            elif data == 'history':
                user_id = callback_query['from']['id']
                handle_history_command(chat_id, user_id)
            elif data.startswith('cancel_'):
                appointment_id = int(data.split('_')[1])
                handle_cancel_appointment(chat_id, appointment_id)
            elif data.startswith('book_'):
                service_id = int(data.split('_')[1])
                handle_book_appointment(chat_id, service_id)
            elif data.startswith('booklink_'):
                token_str = data.replace('booklink_', '', 1)
                user_id = callback_query['from']['id']
                handle_booking_link_callback(chat_id, user_id, callback_query_id, token_str)
            elif data.startswith('spec_confirm_'):
                token_str = data.replace('spec_confirm_', '', 1)
                user_id = callback_query['from']['id']
                handle_specialist_connect_telegram_callback(chat_id, user_id, callback_query_id, token_str)
            elif data.startswith('spec_bok_ok_'):
                try:
                    bid = int(data.replace('spec_bok_ok_', '', 1))
                    message_id = callback_query['message']['message_id']
                    handle_specialist_booking_confirm_decline(chat_id, callback_query_id, message_id, bid, 'confirm')
                except (ValueError, KeyError) as e:
                    logger.warning("spec_bok_ok_ parse: %s", e)
                    answer_callback_query(callback_query_id, 'Ошибка. Попробуйте позже.')
            elif data.startswith('spec_bok_no_'):
                try:
                    bid = int(data.replace('spec_bok_no_', '', 1))
                    message_id = callback_query['message']['message_id']
                    handle_specialist_booking_confirm_decline(chat_id, callback_query_id, message_id, bid, 'decline')
                except (ValueError, KeyError) as e:
                    logger.warning("spec_bok_no_ parse: %s", e)
                    answer_callback_query(callback_query_id, 'Ошибка. Попробуйте позже.')
            else:
                send_telegram_message(chat_id, "Выберите действие по кнопкам ниже.", get_main_reply_keyboard())
    
    except Exception as e:
        logger.exception("TG bot: ошибка обработки обновления: %s", e)


def handle_login_via_bot(chat_id):
    """
    Пользователь нажал «Войти через Telegram (открыть в приложении)» на сайте и попал в бота (start=login).
    Показываем кнопку для перехода на сайт и завершения входа через Telegram OAuth.
    """
    site_url = get_site_url().rstrip('/')
    login_url = f"{site_url}/accounts/telegram/login/"
    keyboard = {
        'inline_keyboard': [[
            {'text': '🔐 Войти на сайт', 'url': login_url}
        ]]
    }
    send_telegram_message(
        chat_id,
        "👋 <b>Вход на сайт через Telegram</b>\n\n"
        "Нажмите кнопку ниже — откроется страница входа на сайте. Подтвердите вход там, и вы будете авторизованы.",
        keyboard
    )


def handle_connect_via_bot(chat_id):
    """
    Пользователь нажал «Открыть в приложении Telegram» в профиле (подключить Telegram) и попал в бота (start=connect).
    Показываем кнопку для перехода на сайт и привязки аккаунта Telegram.
    """
    site_url = get_site_url().rstrip('/')
    connect_url = f"{site_url}/accounts/telegram/login/?process=connect&next=/profile/"
    keyboard = {
        'inline_keyboard': [[
            {'text': '🔗 Подключить аккаунт на сайте', 'url': connect_url}
        ]]
    }
    send_telegram_message(
        chat_id,
        "👋 <b>Подключение Telegram к аккаунту на сайте</b>\n\n"
        "Нажмите кнопку ниже — откроется страница сайта. Подтвердите подключение там.",
        keyboard
    )


def handle_specialist_connect_telegram(chat_id, user_id, token_str):
    """
    Специалист перешёл по ссылке «Подключить через приложение» со страницы интеграций (start=connect_spec_TOKEN).
    Показываем кнопку «Подтвердить»; по нажатию вызываем API appoinment_sistem для привязки chat_id к Integration.
    """
    keyboard = {
        'inline_keyboard': [[
            {'text': '✅ Подтвердить подключение', 'callback_data': f'spec_confirm_{token_str}'}
        ]]
    }
    send_telegram_message(
        chat_id,
        "👋 <b>Подключение Telegram для уведомлений специалиста</b>\n\n"
        "Нажмите кнопку ниже — после этого вы будете получать уведомления о новых записях и напоминания о консультациях.",
        keyboard
    )


def handle_specialist_connect_telegram_callback(chat_id, user_id, callback_query_id, token_str):
    """Обработка нажатия «Подтвердить» при подключении Telegram специалиста."""
    site_url = get_site_url().rstrip('/')
    api_url = f"{site_url}/api/specialist/connect-telegram/"
    logger.info("TG bot: API specialist/connect-telegram chat_id=%s user_id=%s token_len=%s", chat_id, user_id, len(token_str or ""))
    try:
        r = requests.post(api_url, json={'link_token': token_str, 'telegram_id': user_id}, timeout=15)
        data = r.json() if r.text else {}
        if r.status_code == 200 and data.get('success'):
            logger.info("TG bot: specialist connect OK chat_id=%s", chat_id)
            answer_callback_query(callback_query_id, 'Готово! Уведомления будут приходить сюда.')
            send_telegram_message(
                chat_id,
                "✅ <b>Telegram успешно подключён.</b>\n\n"
                "Вы будете получать:\n"
                "• уведомления о новых записях;\n"
                "• напоминания о консультациях за 24 часа и за 1 час."
            )
        else:
            msg = data.get('error', 'Ссылка недействительна или истекла.')
            logger.warning("TG bot: specialist connect FAIL chat_id=%s status=%s body=%s", chat_id, r.status_code, data)
            answer_callback_query(callback_query_id, msg[:200])
            send_telegram_message(
                chat_id,
                f"❌ Не удалось подключить: {msg}\n\n"
                "Попробуйте «Подключить через браузер» на странице интеграций на сайте — откройте сайт и нажмите эту кнопку там."
            )
    except requests.exceptions.ConnectionError as e:
        logger.warning("TG bot: specialist connect ConnectionError: %s SITE_URL=%s", e, site_url)
        answer_callback_query(callback_query_id, 'Сервер недоступен.')
        send_telegram_message(
            chat_id,
            "❌ Не удалось связаться с сервером. Проверьте, что на сервере в переменной SITE_URL указан адрес вашего сайта (например https://allyourclients.ru), и что бот запущен с правильными настройками."
        )
    except Exception as e:
        logger.warning("Ошибка вызова API подключения специалиста: %s", e)
        answer_callback_query(callback_query_id, 'Ошибка. Попробуйте позже.')
        send_telegram_message(chat_id, "❌ Ошибка связи с сервером. Попробуйте «Подключить через браузер» на странице интеграций на сайте.")


def handle_booking_link_confirm(chat_id, user_id, token_str):
    """
    Пользователь перешёл по ссылке с страницы «Запись создана» (start=link_TOKEN).
    Показываем кнопку «Подтвердить»; по нажатию вызываем API сайта (consultant_menu) для привязки telegram_id к записи.
    """
    site_url = get_site_url().rstrip('/')
    api_url = f"{site_url}/api/booking/confirm-telegram/"
    keyboard = {
        'inline_keyboard': [[
            {'text': '✅ Подтвердить и получать уведомления', 'callback_data': f'booklink_{token_str}'}
        ]]
    }
    send_telegram_message(
        chat_id,
        "📌 <b>Подтвердите привязку Telegram к вашей записи</b>\n\n"
        "Нажмите кнопку ниже — после этого напоминания о записи будут приходить сюда. Это необязательно.",
        keyboard
    )
    return True  # мы показали сообщение, не вызываем обычный /start


def handle_booking_link_callback(chat_id, user_id, callback_query_id, token_str):
    """Обработка нажатия кнопки «Подтвердить» после перехода по ссылке записи."""
    site_url = get_site_url().rstrip('/')
    api_url = f"{site_url}/api/booking/confirm-telegram/"
    logger.info("TG bot: API booking/confirm-telegram chat_id=%s user_id=%s token_len=%s", chat_id, user_id, len(token_str or ""))
    try:
        r = requests.post(api_url, json={'link_token': token_str, 'telegram_id': user_id}, timeout=10)
        data = r.json() if r.text else {}
        if r.status_code == 200 and data.get('success'):
            logger.info("TG bot: booking confirm OK chat_id=%s", chat_id)
            answer_callback_query(callback_query_id, 'Готово! Уведомления будут приходить сюда.')
            send_telegram_message(chat_id, "✅ Ваш Telegram привязан к записи. Напоминания будут приходить сюда.")
        else:
            logger.warning("TG bot: booking confirm FAIL chat_id=%s status=%s body=%s", chat_id, r.status_code, data)
            answer_callback_query(callback_query_id, 'Ссылка недействительна или уже использована.')
    except Exception as e:
        logger.warning("TG bot: booking confirm error: %s", e)
        answer_callback_query(callback_query_id, 'Ошибка. Попробуйте позже.')


def handle_specialist_booking_confirm_decline(chat_id, callback_query_id, message_id, booking_id, action):
    """Специалист нажал «Подтвердить» или «Отклонить» по новой записи — вызываем API сайта и обновляем сообщение."""
    ok, data = _fetch_site_api('/api/booking/specialist-set-status/', {
        'booking_id': booking_id,
        'action': action,
        'telegram_chat_id': str(chat_id),
    })
    if ok:
        if action == 'confirm':
            answer_callback_query(callback_query_id, 'Запись подтверждена.')
            edit_telegram_message(chat_id, message_id, '✅ <b>Запись подтверждена.</b>')
        else:
            answer_callback_query(callback_query_id, 'Запись отклонена.')
            edit_telegram_message(chat_id, message_id, '❌ <b>Запись отклонена.</b>')
    else:
        err = (data or {}).get('error', 'Ошибка сервера')
        answer_callback_query(callback_query_id, err[:200])
        edit_telegram_message(chat_id, message_id, f'⚠️ Не удалось изменить статус: {err}')


def handle_link_token(chat_id, user_id, username, first_name, token_str):
    """
    Обработка /start link_TOKEN: привязка Telegram к аккаунту специалиста (или клиента).
    Возвращает True, если токен найден и привязка выполнена.
    """
    try:
        link_token = TelegramLinkToken.objects.filter(token=token_str, used=False).first()
        if not link_token:
            return False
        user = link_token.user
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.telegram_id = user_id
        profile.telegram_username = username or profile.telegram_username
        profile.save()
        link_token.used = True
        link_token.save()
        if getattr(profile, 'user_type', None) == 'specialist':
            send_telegram_message(chat_id, "✅ Telegram привязан. Теперь вы можете пользоваться ботом как специалист.", get_main_reply_keyboard())
        else:
            send_telegram_message(chat_id, "✅ Telegram привязан к вашему аккаунту.", get_main_reply_keyboard())
        return True
    except Exception as e:
        logger.error(f"Ошибка привязки по токену: {e}")
        return False


def handle_start_command(chat_id, user_id, username, first_name):
    """Обработка команды /start"""
    try:
        # Обновляем/создаем TelegramClient и пытаемся найти связь со специалистом
        tg_client, _ = TelegramClient.objects.get_or_create(
            telegram_id=user_id,
            defaults={"telegram_username": username or "", "first_name": first_name or ""},
        )
        tg_client.telegram_username = username or tg_client.telegram_username
        tg_client.first_name = first_name or tg_client.first_name
        tg_client.last_seen_at = timezone.now()

        if not tg_client.last_specialist and username:
            maybe = Appointment.objects.filter(client_telegram__iexact=f"@{username}").order_by("-appointment_date").first()
            if maybe:
                tg_client.last_specialist = maybe.specialist
                TelegramClientSpecialist.objects.get_or_create(client=tg_client, specialist=maybe.specialist)

        tg_client.save()

        profile = UserProfile.objects.filter(telegram_id=user_id).first()

        # Авторизация клиента по записям: если записывался по ссылке с @username — создаём User+Profile и привязываем записи
        if not profile and username:
            norm = f"@{username}" if not username.startswith('@') else username
            appointments_by_telegram = Appointment.objects.filter(
                client_telegram__iexact=norm
            ).order_by('-appointment_date')
            if appointments_by_telegram.exists():
                first_app = appointments_by_telegram.first()
                uname = f"telegram_{user_id}"
                if User.objects.filter(username=uname).exists():
                    user = User.objects.get(username=uname)
                else:
                    user = User.objects.create_user(
                        username=uname,
                        email=first_app.client_email or f"{uname}@telegram.user",
                        password=uuid.uuid4().hex,
                    )
                    user.set_unusable_password()
                    user.save()
                profile, _ = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={"user_type": "client", "telegram_username": username or ""},
                )
                profile.telegram_id = user_id
                profile.telegram_username = username or profile.telegram_username
                profile.save()
                appointments_by_telegram.update(client=user)
                send_telegram_message(
                    chat_id,
                    "✅ Вы подтвердили Telegram по вашей записи. Теперь здесь видны «Мои записи».",
                    get_main_reply_keyboard(),
                )
                # Показываем кнопки как у зарегистрированного клиента
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '📱 Записаться на консультацию', 'url': _get_booking_url()}],
                        [{'text': '📋 Мои записи', 'callback_data': 'my_appointments'}, {'text': '❓ Помощь', 'callback_data': 'help'}],
                    ]
                }
                send_telegram_message(chat_id, "Выберите действие:", keyboard)
                return
            profile = UserProfile.objects.filter(telegram_id=user_id).first()
        
        # Специалист: по профилю (bookings) или по подключению на сайте (Integration.telegram_chat_id)
        is_specialist = profile and profile.user_type == "specialist"
        if not is_specialist:
            ok, data = _fetch_site_api('/api/telegram/specialist-bookings/', {'telegram_chat_id': str(chat_id)})
            if ok and data.get('is_specialist'):
                is_specialist = True
        if is_specialist:
            site_url = get_site_url().rstrip('/')
            web_stats = f"{site_url}/telegram/specialist/stats/"
            web_upcoming = f"{site_url}/telegram/specialist/upcoming/"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "📋 Записи", "url": f"{site_url}/booking/"},
                        {"text": "👥 Клиенты", "url": f"{site_url}/clients/"},
                    ],
                    [
                        {"text": "📊 Статистика", "web_app": {"url": web_stats}},
                        {"text": "📅 Ближайшие записи", "web_app": {"url": web_upcoming}},
                    ],
                    [
                        {"text": "📅 5 ближайших в чат", "callback_data": "spec_next"},
                    ],
                ]
            }
            msg = f"👋 Добро пожаловать, {first_name}!\n\nВы вошли как <b>специалист</b>.\nКнопки внизу: <b>Записи</b> — кто записался, <b>Клиенты</b> — карточки клиентов."
            send_telegram_message(chat_id, msg, keyboard)
            send_telegram_message(chat_id, "Используйте кнопки внизу экрана.", get_specialist_reply_keyboard())
            return

        # Кнопки: inline под сообщением + постоянное меню внизу
        booking_url = _get_booking_url()

        admin_username = getattr(settings, 'ADMIN_TELEGRAM_USERNAME', 'andrievskypsy').lstrip('@')
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '📱 Записаться на консультацию', 'url': booking_url},
                ],
                [
                    {'text': '📋 Мои записи', 'callback_data': 'my_appointments'},
                    {'text': '📜 История', 'callback_data': 'history'},
                ],
                [
                    {'text': '📞 Связаться с администрацией', 'url': f'https://t.me/{admin_username}'},
                    {'text': '❓ Помощь', 'callback_data': 'help'},
                ],
            ]
        }
        
        if profile:
            message = f"""
👋 Добро пожаловать, {first_name}!

Вы уже зарегистрированы в системе.
Используйте кнопки ниже для работы с ботом.
"""
        else:
            # Если нет связей со специалистами — показать нужный текст
            if not tg_client.last_specialist_id and not TelegramClientSpecialist.objects.filter(client=tg_client).exists():
                message = "Пока что вас еще ниразу не записывали и ваших данных нет у специалистов."
            else:
                message = f"""
👋 Добро пожаловать, {first_name}!

Для полной регистрации перейдите на сайт и создайте аккаунт.
После регистрации ваш Telegram будет автоматически привязан.

Используйте кнопки ниже для работы с ботом.
"""
        
        send_telegram_message(chat_id, message, keyboard)
    
    except Exception as e:
        logger.error(f"Ошибка обработки /start: {e}", exc_info=True)
        send_telegram_message(chat_id, "Произошла ошибка. Попробуйте позже или нажмите /start.", get_main_reply_keyboard())


def handle_register_command(chat_id, user_id, username, first_name):
    """Обработка команды /register: текст и кнопка перехода на страницу регистрации."""
    site = get_site_url().rstrip('/')
    register_url = f"{site}/register/"
    message = f"""
📝 <b>Регистрация</b>

Для регистрации перейдите на сайт по кнопке ниже, укажите ФИО и телефон, выберите способ входа (Google, Telegram или почта).

После регистрации вы сможете:
• Записываться на консультации
• Получать уведомления и напоминания
• Управлять записями
"""
    keyboard = {
        'inline_keyboard': [
            [{'text': '📝 Перейти на страницу регистрации', 'url': register_url}],
            [{'text': '📱 Записаться (без регистрации)', 'url': _get_booking_url()}],
        ]
    }
    send_telegram_message(chat_id, message, keyboard)


def handle_history_command(chat_id, user_id):
    """Показать историю: к каким специалистам уже записывался пользователь."""
    try:
        # Сначала записи с основного сайта (consultant_menu)
        ok, data = _fetch_site_api('/api/telegram/client-bookings/', {'telegram_id': user_id})
        if ok and data and data.get('bookings'):
            from collections import Counter
            bookings = data['bookings']
            names = [b.get('consultant_name') or 'Специалист' for b in bookings]
            by_name = Counter(names)
            name_to_calendar = {}
            for b in bookings:
                n = b.get('consultant_name') or 'Специалист'
                if n not in name_to_calendar and b.get('calendar_id'):
                    name_to_calendar[n] = b['calendar_id']
            if by_name:
                site = get_site_url().rstrip('/')
                lines = ["📜 <b>К кому вы уже записывались:</b>\n"]
                for name, cnt in by_name.most_common():
                    _raz = "раз" if cnt == 1 else ("раза" if 2 <= cnt <= 4 else "раз")
                    cal_id = name_to_calendar.get(name)
                    if cal_id:
                        url = f"{site}/book/{cal_id}/"
                        lines.append(f"• <a href=\"{url}\">{name}</a> — {cnt} {_raz}")
                    else:
                        lines.append(f"• {name} — {cnt} {_raz}")
                send_telegram_message(chat_id, "\n".join(lines), get_main_reply_keyboard())
                return
        # Иначе — из приложения bookings
        from django.db.models import Count
        profile = UserProfile.objects.filter(telegram_id=user_id).select_related('user').first()
        if not profile or not profile.user:
            tg_client = TelegramClient.objects.filter(telegram_id=user_id).first()
            if not tg_client or not tg_client.telegram_username:
                send_telegram_message(chat_id, "У вас пока нет записей. Запишитесь через кнопку «Записаться».", get_main_reply_keyboard())
                return
            norm = f"@{tg_client.telegram_username}" if not tg_client.telegram_username.startswith('@') else tg_client.telegram_username
            qs = Appointment.objects.filter(client_telegram__iexact=norm).exclude(status='cancelled')
        else:
            qs = Appointment.objects.filter(client=profile.user).exclude(status='cancelled')
        by_specialist = qs.values('specialist').annotate(cnt=Count('id')).order_by('-cnt')
        if not by_specialist:
            send_telegram_message(chat_id, "У вас пока нет записей к специалистам.", get_main_reply_keyboard())
            return
        specialists = Specialist.objects.filter(id__in=[x['specialist'] for x in by_specialist]).select_related('user')
        spec_map = {s.id: (s.user.get_full_name() or s.user.username) for s in specialists}
        lines = ["📜 <b>К кому вы уже записывались:</b>\n"]
        for item in by_specialist:
            name = spec_map.get(item['specialist'], 'Специалист')
            cnt = item['cnt']
            _raz = "раз" if cnt == 1 else ("раза" if 2 <= cnt <= 4 else "раз")
            lines.append(f"• {name} — {cnt} {_raz}")
        send_telegram_message(chat_id, "\n".join(lines), get_main_reply_keyboard())
    except Exception as e:
        logger.error("Ошибка истории записей: %s", e)
        send_telegram_message(chat_id, "Не удалось загрузить историю. Попробуйте позже.", get_main_reply_keyboard())


def handle_contact_admin_command(chat_id):
    """Связь с администрацией: кнопка для перехода в Telegram @andrievskypsy."""
    admin_username = getattr(settings, 'ADMIN_TELEGRAM_USERNAME', 'andrievskypsy').lstrip('@')
    url = f"https://t.me/{admin_username}"
    keyboard = {
        'inline_keyboard': [
            [{'text': '📞 Написать администрации', 'url': url}],
        ]
    }
    send_telegram_message(
        chat_id,
        "По вопросам записи и консультаций обращайтесь к администрации. Нажмите кнопку ниже, чтобы написать в Telegram:",
        keyboard,
    )


def _send_specialist_webapp(chat_id, app_type):
    """Отправить сообщение с кнопкой перехода на сайт (календари или запись). Открывается в браузере."""
    site = get_site_url().rstrip('/')
    if app_type == 'stats':
        url = f"{site}/calendars/"
        text = "📊 Откройте календари и записи на сайте:"
    else:
        url = f"{site}/calendars/"
        text = "📅 Откройте календари и ближайшие записи на сайте:"
    keyboard = {
        'inline_keyboard': [[{'text': 'Открыть на сайте', 'url': url}]]
    }
    send_telegram_message(chat_id, text, keyboard)


def handle_manage_accounts_command(chat_id):
    """Отправить ссылку на страницу управления аккаунтами (отключить Telegram/Google)."""
    site = get_site_url().rstrip('/')
    connections_url = f"{site}/accounts/social/connections/"
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔗 Открыть управление аккаунтами', 'url': connections_url}],
        ]
    }
    send_telegram_message(
        chat_id,
        "Чтобы отключить вход через Telegram или Google, откройте страницу управления на сайте и нажмите «Отключить» у нужного способа входа.",
        keyboard,
    )


def handle_appointments_command(chat_id, user_id):
    """Показать записи пользователя: сначала с основного сайта (consultant_menu), иначе из bookings."""
    keyboard = {
        'inline_keyboard': [[
            {'text': '📱 Записаться на консультацию', 'url': _get_booking_url()}
        ]]
    }
    try:
        # Записи с основного сайта (consultant_menu.Booking по telegram_id)
        ok, data = _fetch_site_api('/api/telegram/client-bookings/', {'telegram_id': user_id})
        if ok and data and data.get('bookings'):
            items = data['bookings']
            status_emoji = {'pending': '⏳', 'confirmed': '✅', 'completed': '✔️'}
            message = "📋 <b>Ваши записи:</b>\n\n"
            for b in items[:15]:
                em = status_emoji.get(b.get('status'), '📅')
                message += f"{em} <b>{b.get('date', '')} {b.get('time', '')}</b>\n"
                message += f"👤 {b.get('consultant_name', '—')}\n"
                message += f"💼 {b.get('service_name', 'Консультация')}\n\n"
            send_telegram_message(chat_id, message, keyboard)
            return

        # Иначе — записи из приложения bookings (Appointment)
        profile = UserProfile.objects.filter(telegram_id=user_id).first()
        if not profile or not profile.user:
            send_telegram_message(
                chat_id,
                "❌ Вы не зарегистрированы в системе.\nИспользуйте кнопку ниже для записи или /register для регистрации.",
                keyboard
            )
            return
        user = profile.user
        appointments = Appointment.objects.filter(client=user).order_by('-appointment_date')[:10]
        if not appointments:
            send_telegram_message(chat_id, "📋 У вас пока нет записей.", keyboard)
            return
        message = "📋 <b>Ваши записи:</b>\n\n"
        for appointment in appointments:
            specialist_name = appointment.specialist.user.get_full_name() or appointment.specialist.user.username
            service_name = appointment.service.name if appointment.service else "Консультация"
            date_str = appointment.appointment_date.strftime("%d.%m.%Y %H:%M")
            status_emoji = {
                'pending': '⏳', 'confirmed': '✅', 'cancelled': '❌', 'completed': '✔️'
            }.get(appointment.status, '📅')
            message += f"{status_emoji} <b>{date_str}</b>\n"
            message += f"👤 {specialist_name}\n"
            message += f"💼 {service_name}\n"
            message += f"Статус: {appointment.get_status_display()}\n\n"
        send_telegram_message(chat_id, message, keyboard)
    except Exception as e:
        logger.error("Ошибка получения записей: %s", e)
        send_telegram_message(chat_id, "Произошла ошибка при получении записей.")


def handle_cancel_appointment(chat_id, appointment_id):
    """Отменить запись"""
    try:
        profile = UserProfile.objects.filter(telegram_id=chat_id).first()
        if not profile or not profile.user:
            send_telegram_message(chat_id, "❌ Вы не зарегистрированы в системе.")
            return
        
        appointment = Appointment.objects.filter(id=appointment_id, client=profile.user).first()
        if not appointment:
            send_telegram_message(chat_id, "❌ Запись не найдена.")
            return
        
        appointment.status = 'cancelled'
        appointment.save()
        
        send_telegram_message(chat_id, "✅ Запись отменена.")
    
    except Exception as e:
        logger.error(f"Ошибка отмены записи: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при отмене записи.")


def handle_book_appointment(chat_id, service_id):
    """Записаться на консультацию"""
    try:
        profile = UserProfile.objects.filter(telegram_id=chat_id).first()
        if not profile or not profile.user:
            keyboard = {
                'inline_keyboard': [
                    [
                        {
                            'text': '📱 Записаться на консультацию',
                            'url': _get_booking_url()
                        }
                    ]
                ]
            }
            send_telegram_message(
                chat_id,
                "❌ Вы не зарегистрированы в системе.\nИспользуйте кнопку ниже для записи.",
                keyboard
            )
            return
        
        service = Service.objects.filter(id=service_id, is_active=True).first()
        if not service:
            send_telegram_message(chat_id, "❌ Услуга не найдена.")
            return
        
        # Ссылка на страницу записи (календарь выберется на сайте)
        keyboard = {
            'inline_keyboard': [
                [{'text': '📱 Записаться', 'url': _get_booking_url()}]
            ]
        }
        
        message = f"📅 <b>{service.name}</b>\n\nДля записи нажмите кнопку ниже:"
        send_telegram_message(chat_id, message, keyboard)
    
    except Exception as e:
        logger.error(f"Ошибка записи: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при получении слотов.")


def handle_help_command(chat_id):
    """Показать справку"""
    admin_username = getattr(settings, 'ADMIN_TELEGRAM_USERNAME', 'andrievskypsy').lstrip('@')
    site = get_site_url().rstrip('/')
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📱 Записаться', 'url': _get_booking_url()},
                {'text': '📋 Мои записи', 'callback_data': 'my_appointments'},
            ],
            [
                {'text': '📝 Регистрация', 'url': f'{site}/register/'},
                {'text': '📜 История', 'callback_data': 'history'},
                {'text': '📞 Связаться', 'url': f'https://t.me/{admin_username}'},
            ]
        ]
    }
    
    message = """
📖 <b>Справка по командам:</b>

/start - Начать работу с ботом
/register - Регистрация в системе
/appointments - Мои записи
/history - К кому уже записывались
/admin - Связаться с администрацией (@"""+admin_username+""")
/help - Эта справка

<b>Возможности:</b>
• Запись на консультацию — кнопка «Записаться» откроет сайт в браузере
• Просмотр своих записей и истории по специалистам
• Связь с администрацией в Telegram
• Уведомления и напоминания о записях (если подтвердили Telegram)
"""
    send_telegram_message(chat_id, message, keyboard)


def handle_specialist_next_appointments(chat_id, user_id):
    """
    Ближайшие записи специалиста: сначала с основного сайта (consultant_menu по chat_id),
    иначе из приложения bookings (Appointment).
    """
    try:
        # Специалист с основного сайта (Integration.telegram_chat_id == chat_id)
        ok, data = _fetch_site_api('/api/telegram/specialist-bookings/', {'telegram_chat_id': str(chat_id)})
        if ok and data and data.get('bookings'):
            upcoming = [b for b in data['bookings'] if b.get('is_upcoming')][:5]
            if upcoming:
                text = "📅 <b>5 ближайших записей:</b>\n\n"
                for b in upcoming:
                    text += f"• <b>{b.get('date', '')} {b.get('time', '')}</b> — {b.get('client_name', '—')}\n"
                    text += f"  Услуга: {b.get('service_name', 'Консультация')}\n\n"
                send_telegram_message(chat_id, text)
                return
            send_telegram_message(chat_id, "📭 Ближайших записей нет.")
            return

        # Иначе — специалист из приложения bookings
        profile = UserProfile.objects.filter(telegram_id=user_id, user_type="specialist").select_related("user").first()
        if not profile:
            send_telegram_message(chat_id, "❌ Вы не являетесь специалистом.")
            return
        specialist = getattr(profile.user, "specialist", None)
        if not specialist:
            send_telegram_message(chat_id, "❌ Профиль специалиста не найден.")
            return
        items = (
            Appointment.objects.filter(
                specialist=specialist,
                status__in=["pending", "confirmed"],
                appointment_date__gte=timezone.now(),
            )
            .order_by("appointment_date")[:5]
        )
        if not items:
            send_telegram_message(chat_id, "📭 Ближайших записей нет.")
            return
        text = "📅 <b>5 ближайших записей:</b>\n\n"
        for a in items:
            text += f"• <b>{a.appointment_date.strftime('%d.%m.%Y %H:%M')}</b> — {a.client_name}"
            if a.client_telegram:
                text += f" ({a.client_telegram})"
            if a.service:
                text += f"\n  Услуга: {a.service.name}"
            text += "\n\n"
        send_telegram_message(chat_id, text)
    except Exception as e:
        send_telegram_message(chat_id, f"Ошибка: {e}")


def handle_specialist_bookings_list(chat_id, user_id):
    """Список записей к специалисту (кто записался): с основного сайта consultant_menu."""
    site_url = get_site_url().rstrip('/')
    booking_url = f"{site_url}/booking/"
    try:
        ok, data = _fetch_site_api('/api/telegram/specialist-bookings/', {'telegram_chat_id': str(chat_id)})
        if not ok or not data.get('is_specialist'):
            send_telegram_message(chat_id, "Список записей доступен только специалистам с привязанным Telegram.")
            return
        bookings = data.get('bookings') or []
        upcoming = [b for b in bookings if b.get('is_upcoming')][:15]
        past = [b for b in bookings if not b.get('is_upcoming')][:5]
        def _fmt_date(d):
            if not d:
                return ''
            try:
                from datetime import datetime
                dt = datetime.strptime(d[:10], '%Y-%m-%d')
                return dt.strftime('%d.%m.%Y')
            except Exception:
                return d[:10]

        if not upcoming and not past:
            text = "📋 <b>Записи</b>\n\nПока нет записей."
        else:
            text = "📋 <b>Записи</b> (кто к вам записался)\n\n"
            if upcoming:
                text += "<b>Предстоящие:</b>\n"
                for b in upcoming:
                    text += f"• {_fmt_date(b.get('date'))} {b.get('time', '')} — {b.get('client_name', '—')}\n"
                    text += f"  {b.get('service_name', 'Консультация')}\n"
                text += "\n"
            if past:
                text += "<b>Прошедшие:</b>\n"
                for b in past:
                    text += f"• {_fmt_date(b.get('date'))} {b.get('client_name', '—')}\n"
        keyboard = {
            'inline_keyboard': [[{'text': '📅 Открыть календарь на сайте', 'url': booking_url}]]
        }
        send_telegram_message(chat_id, text, keyboard)
    except Exception as e:
        logger.exception("handle_specialist_bookings_list: %s", e)
        send_telegram_message(chat_id, "Не удалось загрузить записи. Попробуйте позже.")


def handle_specialist_clients_list(chat_id, user_id):
    """Список клиентов из карточек клиентов специалиста (consultant_menu.ClientCard)."""
    site_url = get_site_url().rstrip('/')
    clients_url = f"{site_url}/clients/"
    try:
        ok, data = _fetch_site_api('/api/telegram/specialist-clients/', {'telegram_chat_id': str(chat_id)})
        if not ok or not data.get('is_specialist'):
            send_telegram_message(chat_id, "Список клиентов доступен только специалистам с привязанным Telegram.")
            return
        clients = data.get('clients') or []
        if not clients:
            text = "👥 <b>Клиенты</b>\n\nПока нет карточек клиентов."
        else:
            text = "👥 <b>Клиенты</b> (карточки)\n\n"
            for c in clients[:20]:
                name = c.get('name') or '—'
                contact = []
                if c.get('phone'):
                    contact.append(c['phone'])
                if c.get('telegram'):
                    contact.append(c['telegram'])
                if c.get('email'):
                    contact.append(c['email'])
                text += f"• <b>{name}</b>\n"
                if contact:
                    text += "  " + ", ".join(contact) + "\n"
                else:
                    text += "  —\n"
            if len(clients) > 20:
                text += f"\n… и ещё {len(clients) - 20}. Полный список на сайте."
        keyboard = {
            'inline_keyboard': [[{'text': '👥 Карточки клиентов на сайте', 'url': clients_url}]]
        }
        send_telegram_message(chat_id, text, keyboard)
    except Exception as e:
        logger.exception("handle_specialist_clients_list: %s", e)
        send_telegram_message(chat_id, "Не удалось загрузить клиентов. Попробуйте позже.")


def send_broadcast_message(message_text, user_type=None):
    """Отправить массовое сообщение пользователям"""
    try:
        profiles = UserProfile.objects.filter(telegram_id__isnull=False)
        
        if user_type:
            profiles = profiles.filter(user_type=user_type)
        
        sent_count = 0
        for profile in profiles:
            if send_telegram_message(profile.telegram_id, message_text):
                sent_count += 1
        
        return sent_count
    except Exception as e:
        logger.error(f"Ошибка массовой рассылки: {e}")
        return 0

