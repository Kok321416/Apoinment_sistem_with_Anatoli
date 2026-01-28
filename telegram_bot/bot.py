"""
Telegram бот для системы записи на консультации
"""
import logging
from django.conf import settings
from django.utils import timezone
from bookings.models import UserProfile, Appointment, Specialist, Service, TimeSlot
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
    """Отправить сообщение в Telegram"""
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
        data['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
        return False


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
            elif text == '/register':
                handle_register_command(chat_id, user_id, username, first_name)
            elif text == '/appointments' or text == '📋 Мои записи':
                handle_appointments_command(chat_id, user_id)
            elif text == '/help':
                handle_help_command(chat_id)
            else:
                send_telegram_message(chat_id, "Неизвестная команда. Используйте /help для списка команд.")
        
        elif 'callback_query' in update_data:
            callback_query = update_data['callback_query']
            chat_id = callback_query['message']['chat']['id']
            data = callback_query['data']
            
            if data == 'my_appointments':
                user_id = callback_query['from']['id']
                handle_appointments_command(chat_id, user_id)
            elif data.startswith('cancel_'):
                appointment_id = int(data.split('_')[1])
                handle_cancel_appointment(chat_id, appointment_id)
            elif data.startswith('book_'):
                service_id = int(data.split('_')[1])
                handle_book_appointment(chat_id, service_id)
    
    except Exception as e:
        logger.error(f"Ошибка обработки обновления Telegram: {e}")


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
        
        # Кнопка для мини-приложения записи
        webapp_url = f"{get_site_url()}/telegram/appointment/"
        if tg_client.last_specialist_id:
            webapp_url = f"{webapp_url}?specialist_id={tg_client.last_specialist_id}"

        keyboard = {
            'inline_keyboard': [
                [
                    {
                        'text': '📱 Записаться на консультацию',
                        'web_app': {'url': webapp_url}
                    }
                ],
                [
                    {'text': '📋 Мои записи', 'callback_data': 'my_appointments'},
                    {'text': '❓ Помощь', 'callback_data': 'help'}
                ]
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
        logger.error(f"Ошибка обработки /start: {e}")
        send_telegram_message(chat_id, "Произошла ошибка. Попробуйте позже.")


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
    keyboard = {
        'inline_keyboard': [
            [
                {
                    'text': '📱 Записаться на консультацию',
                            'web_app': {'url': f'{get_site_url()}/telegram/appointment/'}
                }
            ],
            [
                {'text': '📋 Мои записи', 'callback_data': 'my_appointments'}
            ]
        ]
    }
    
    message = """
📖 <b>Справка по командам:</b>

/start - Начать работу с ботом
/register - Регистрация в системе
/appointments - Мои записи
/help - Эта справка

<b>Возможности:</b>
• Запись на консультацию через мини-приложение
• Получение уведомлений о записях
• Просмотр своих записей
• Управление записями
• Информационные сообщения от администрации
"""
    send_telegram_message(chat_id, message, keyboard)


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

