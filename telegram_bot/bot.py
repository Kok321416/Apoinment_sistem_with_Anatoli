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


def get_main_reply_keyboard():
    """Постоянное меню внизу экрана (кнопки всегда видны)."""
    return {
        'keyboard': [
            [{'text': '📱 Записаться'}, {'text': '📋 Мои записи'}],
            [{'text': '📜 История'}, {'text': '📞 Связаться'}],
            [{'text': '❓ Помощь'}],
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
                {'text': '📱 Записаться', 'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}}
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


def _send_webapp_button(chat_id):
    """Отправить сообщение с кнопкой открытия мини-приложения записи."""
    webapp_url = f"{get_site_url()}/telegram/appointment/"
    keyboard = {
        'inline_keyboard': [[{'text': '📱 Открыть запись на консультацию', 'web_app': {'url': webapp_url}}]]
    }
    send_telegram_message(chat_id, "Нажмите кнопку ниже, чтобы записаться:", keyboard)
    send_telegram_message(chat_id, "Меню:", get_main_reply_keyboard())


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
            elif text.startswith('/start connect') or text == '/start connect':
                handle_connect_via_bot(chat_id)
            elif text == '/register':
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
            else:
                send_telegram_message(chat_id, "Неизвестная команда. Нажмите кнопку внизу или /help.", get_main_reply_keyboard())
        
        elif 'callback_query' in update_data:
            callback_query = update_data['callback_query']
            callback_query_id = callback_query['id']
            chat_id = callback_query['message']['chat']['id']
            data = callback_query.get('data', '')
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
            else:
                send_telegram_message(chat_id, "Выберите действие в меню.", get_main_reply_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка обработки обновления Telegram: {e}")


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
    try:
        r = requests.post(api_url, json={'link_token': token_str, 'telegram_id': user_id}, timeout=10)
        data = r.json() if r.text else {}
        if r.status_code == 200 and data.get('success'):
            answer_callback_query(callback_query_id, 'Готово! Уведомления будут приходить сюда.')
            send_telegram_message(chat_id, "✅ Ваш Telegram привязан к записи. Напоминания будут приходить сюда.")
        else:
            answer_callback_query(callback_query_id, 'Ссылка недействительна или уже использована.')
    except Exception as e:
        logger.warning(f"Ошибка вызова API подтверждения записи: {e}")
        answer_callback_query(callback_query_id, 'Ошибка. Попробуйте позже.')


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
                webapp_url = f"{get_site_url()}/telegram/appointment/"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '📱 Записаться на консультацию', 'web_app': {'url': webapp_url}}],
                        [{'text': '📋 Мои записи', 'callback_data': 'my_appointments'}, {'text': '❓ Помощь', 'callback_data': 'help'}],
                    ]
                }
                send_telegram_message(chat_id, "Выберите действие:", keyboard)
                send_telegram_message(chat_id, "Меню:", get_main_reply_keyboard())
                return
            profile = UserProfile.objects.filter(telegram_id=user_id).first()
        
        # Если это специалист — показываем меню специалиста
        if profile and profile.user_type == "specialist":
            web_stats = f"{get_site_url()}/telegram/specialist/stats/"
            web_upcoming = f"{get_site_url()}/telegram/specialist/upcoming/"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "📊 Статистика", "web_app": {"url": web_stats}},
                        {"text": "📅 Ближайшие записи", "web_app": {"url": web_upcoming}},
                    ],
                    [
                        {"text": "📅 Показать 5 ближайших (в чат)", "callback_data": "spec_next"},
                    ],
                ]
            }
            msg = f"👋 Добро пожаловать, {first_name}!\n\nВы вошли как <b>специалист</b>.\nВыберите действие:"
            send_telegram_message(chat_id, msg, keyboard)
            send_telegram_message(chat_id, "Или используйте меню внизу:", get_main_reply_keyboard())
            return

        # Кнопки: inline под сообщением + постоянное меню внизу
        webapp_url = f"{get_site_url()}/telegram/appointment/"
        if tg_client.last_specialist_id:
            webapp_url = f"{webapp_url}?specialist_id={tg_client.last_specialist_id}"

        admin_username = getattr(settings, 'ADMIN_TELEGRAM_USERNAME', 'andrievskypsy').lstrip('@')
        keyboard = {
            'inline_keyboard': [
                [
                    {'text': '📱 Записаться на консультацию', 'web_app': {'url': webapp_url}},
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
        send_telegram_message(chat_id, "Или выберите действие в меню внизу:", get_main_reply_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка обработки /start: {e}", exc_info=True)
        send_telegram_message(chat_id, "Произошла ошибка. Попробуйте позже или нажмите /start.", get_main_reply_keyboard())


def handle_register_command(chat_id, user_id, username, first_name):
    """Обработка команды /register"""
    message = f"""
📝 <b>Регистрация</b>

Для регистрации в системе:
1. Перейдите на сайт
2. Создайте аккаунт
3. Укажите ваш Telegram: @{username if username else 'username'}

После регистрации вы сможете:
• Записываться на консультации
• Получать уведомления
• Управлять записями
"""
    send_telegram_message(chat_id, message)


def handle_history_command(chat_id, user_id):
    """Показать историю: к каким специалистам уже записывался пользователь."""
    try:
        from django.db.models import Count
        profile = UserProfile.objects.filter(telegram_id=user_id).select_related('user').first()
        if not profile or not profile.user:
            # Пробуем по TelegramClient — записи по client_telegram
            tg_client = TelegramClient.objects.filter(telegram_id=user_id).first()
            if not tg_client or not tg_client.telegram_username:
                send_telegram_message(chat_id, "У вас пока нет записей. Запишитесь через кнопку «Записаться».", get_main_reply_keyboard())
                return
            norm = f"@{tg_client.telegram_username}" if not tg_client.telegram_username.startswith('@') else tg_client.telegram_username
            qs = Appointment.objects.filter(client_telegram__iexact=norm).exclude(status='cancelled')
        else:
            qs = Appointment.objects.filter(client=profile.user).exclude(status='cancelled')
        # Группируем по специалисту: specialist_id -> count
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
        logger.error(f"Ошибка истории записей: {e}")
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
    send_telegram_message(chat_id, "Меню:", get_main_reply_keyboard())


def handle_appointments_command(chat_id, user_id):
    """Показать записи пользователя"""
    try:
        profile = UserProfile.objects.filter(telegram_id=user_id).first()
        
        if not profile or not profile.user:
            keyboard = {
                'inline_keyboard': [
                    [
                        {
                            'text': '📱 Записаться на консультацию',
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}
                        }
                    ]
                ]
            }
            send_telegram_message(
                chat_id,
                "❌ Вы не зарегистрированы в системе.\nИспользуйте кнопку ниже для записи или /register для регистрации.",
                keyboard
            )
            return
        
        user = profile.user
        appointments = Appointment.objects.filter(client=user).order_by('-appointment_date')[:10]
        
        if not appointments:
            keyboard = {
                'inline_keyboard': [
                    [
                        {
                            'text': '📱 Записаться на консультацию',
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}
                        }
                    ]
                ]
            }
            send_telegram_message(chat_id, "📋 У вас пока нет записей.", keyboard)
            return
        
        message = "📋 <b>Ваши записи:</b>\n\n"
        for appointment in appointments:
            specialist_name = appointment.specialist.user.get_full_name() or appointment.specialist.user.username
            service_name = appointment.service.name if appointment.service else "Консультация"
            date_str = appointment.appointment_date.strftime("%d.%m.%Y %H:%M")
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'cancelled': '❌',
                'completed': '✔️'
            }.get(appointment.status, '📅')
            
            message += f"{status_emoji} <b>{date_str}</b>\n"
            message += f"👤 {specialist_name}\n"
            message += f"💼 {service_name}\n"
            message += f"Статус: {appointment.get_status_display()}\n\n"
        
        keyboard = {
            'inline_keyboard': [
                [
                    {
                        'text': '📱 Записаться еще',
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}
                    }
                ]
            ]
        }
        
        send_telegram_message(chat_id, message, keyboard)
    
    except Exception as e:
        logger.error(f"Ошибка получения записей: {e}")
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
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}
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
        
        # Перенаправляем в мини-приложение
        keyboard = {
            'inline_keyboard': [
                [
                    {
                        'text': '📱 Записаться',
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/?service_id={service_id}'}
                    }
                ]
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
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📱 Записаться', 'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}},
                {'text': '📋 Мои записи', 'callback_data': 'my_appointments'},
            ],
            [
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
• Запись на консультацию через мини-приложение
• Просмотр своих записей и истории по специалистам
• Связь с администрацией в Telegram
• Уведомления о записях
"""
    send_telegram_message(chat_id, message, keyboard)
    send_telegram_message(chat_id, "Меню:", get_main_reply_keyboard())


def handle_specialist_next_appointments(chat_id, user_id):
    """
    Быстрый вывод ближайших записей специалиста прямо в чат.
    """
    try:
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

