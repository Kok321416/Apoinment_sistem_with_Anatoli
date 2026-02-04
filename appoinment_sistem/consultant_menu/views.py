from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.urls import reverse
from consultant_menu.models import Consultant, Clients, Category, Calendar, Service, TimeSlot, Booking, Integration
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from allauth.socialaccount.models import SocialAccount
from allauth.account.models import EmailAddress
from datetime import datetime, date, timedelta
from django.utils import timezone
from django.conf import settings
import uuid
import hashlib
import hmac
from django.core.files.storage import default_storage
import os


def _normalize_url(value: str | None) -> str | None:
    """
    Make profile link fields optional and forgiving.

    - Empty -> None
    - Missing scheme -> prepend https://
    """
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value.lstrip('/')}"


def _parse_fio(fio_str):
    """Разбивает строку ФИО на фамилию, имя, отчество."""
    parts = (fio_str or "").strip().split()
    last_name = parts[0] if parts else ""
    first_name = parts[1] if len(parts) > 1 else ""
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else ""
    return first_name, last_name, middle_name


# ========== РЕГИСТРАЦИЯ (HTML) ==========
def register_view(request):
    """Регистрация: ФИО + телефон, выбор способа входа (Telegram / Google / Яндекс-заглушка / почта+пароль)."""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        fio = request.POST.get('fio', '').strip()
        phone = request.POST.get('phone', '').strip()
        auth_method = request.POST.get('auth_method', 'email')

        if not fio or not phone:
            return render(request, 'consultant_menu/register.html', {
                'error': 'Укажите ФИО и номер телефона',
                'fio': fio, 'phone': phone, 'email': request.POST.get('email', ''),
            })

        if auth_method == 'yandex':
            return render(request, 'consultant_menu/register.html', {
                'error': 'Вход через Яндекс будет доступен позже.',
                'fio': fio, 'phone': phone,
            })

        if auth_method == 'telegram':
            request.session['register_fio'] = fio
            request.session['register_phone'] = phone
            next_url = request.GET.get('next', '/')
            return redirect(f'/accounts/telegram/login/?process=signup&next={next_url}')

        if auth_method == 'google':
            request.session['register_fio'] = fio
            request.session['register_phone'] = phone
            next_url = request.GET.get('next', '/')
            return redirect(f'/accounts/google/login/?process=signup&next={next_url}')

        # auth_method == 'email'
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        if not email or not password:
            return render(request, 'consultant_menu/register.html', {
                'error': 'Укажите email и пароль',
                'fio': fio, 'phone': phone, 'email': email,
            })
        if password != password_confirm:
            return render(request, 'consultant_menu/register.html', {
                'error': 'Пароли не совпадают',
                'fio': fio, 'phone': phone, 'email': email,
            })
        if User.objects.filter(username=email).exists():
            return render(request, 'consultant_menu/register.html', {
                'error': 'Пользователь с таким email уже зарегистрирован',
                'fio': fio, 'phone': phone, 'email': email,
            })

        first_name, last_name, middle_name = _parse_fio(fio)
        user = User.objects.create_user(username=email, email=email, password=password)
        category, _ = Category.objects.get_or_create(name_category="Общая")
        Consultant.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            email=email,
            phone=phone,
            telegram_nickname="",
            category_of_specialist=category,
        )
        login(request, user)
        return redirect('home')

    return render(request, 'consultant_menu/register.html')


# ========== ВХОД (HTML) ==========
def login_view(request):
    """Вход через HTML форму"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not email or not password:
            return render(request, 'consultant_menu/login.html', {'error': 'Заполните все поля'})
        
        user = authenticate(username=email, password=password)
        if not user:
            return render(request, 'consultant_menu/login.html', {'error': 'Неверный email или пароль'})
        
        login(request, user)
        return redirect('home')
    
    return render(request, 'consultant_menu/login.html')


# ========== API VIEWS (для API запросов) ==========
class RegisterView(APIView):
    """Регистрация через API"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if User.objects.filter(username=email).exists():
            return Response({'error': 'Уже зарегистрирован'}, status=400)

        user = User.objects.create_user(username=email, email=email, password=password)
        category, _ = Category.objects.get_or_create(name_category="Общая")
        consultant = Consultant.objects.create(
            user=user,
            first_name="",
            last_name="",
            middle_name="",
            email=email,
            phone="",
            telegram_nickname="",
            category_of_specialist=category
        )

        login(request, user)
        return Response({
            'message': 'Успешно',
            'user_id': user.id,
            'consultant_id': consultant.id,
            'email': user.email
        }, status=201)


class LoginView(APIView):
    """Вход через API"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        user = authenticate(username=email, password=password)
        if not user:
            return Response({'error': 'Неверный логин/пароль'}, status=401)

        login(request, user)
        return Response({'message': 'OK', 'email': user.email}, status=200)


# ========== ВЫХОД ==========
def logout_view(request):
    """Выход пользователя (для HTML страниц)"""
    if request.method == 'POST':
        logout(request)
        return redirect('home')
    return redirect('home')


class LogoutView(APIView):
    """Выход (для API)"""
    def post(self, request):
        logout(request)
        return Response({'message': 'OK'}, status=200)


# ========== КОНСУЛЬТАНТЫ ==========
class ConsultantAPIView(APIView):
    """GET: список консультантов | POST: создать клиента"""
    def get(self, request):
        consultants = Consultant.objects.all().values()
        return Response({'consultants': list(consultants)})

    def post(self, request):
        # Получаем консультанта через связь с User
        consultant = Consultant.objects.get(user=request.user)
        # request.user - это User из таблицы auth_user
        # consultant - это Consultant из таблицы consultants

        client = Clients.objects.create(
            name=request.data.get('name'),
            number=request.data.get('number'),
            telegram_nickname=request.data.get('telegram_nickname'),
            who_your_consultant_name=consultant
        )

        return Response({'message': 'Клиент создан', 'id': client.id}, status=201)


# ========== ДОМАШНЯЯ СТРАНИЦА ==========
def home_view(request):
    """Главная страница с навигацией по инструментам"""
    return render(request, 'consultant_menu/home.html')


# ========== КАЛЕНДАРИ ==========
def calendars_view(request):
    """Страница календарей"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')
    calendars = Calendar.objects.filter(consultant=consultant).order_by('name')
    
    success = None
    error = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_calendar':
            name = request.POST.get('name')
            color = request.POST.get('color', '#667eea')
            
            if name:
                Calendar.objects.create(
                    consultant=consultant,
                    name=name,
                    color=color
                )
                success = 'Календарь создан успешно!'
            else:
                error = 'Укажите название календаря'
        
        elif action == 'delete_calendar':
            calendar_id = request.POST.get('calendar_id')
            try:
                calendar = Calendar.objects.get(id=calendar_id, consultant=consultant)
                calendar.delete()
                success = 'Календарь удален'
            except Calendar.DoesNotExist:
                error = 'Календарь не найден'
        
        # Перезагружаем календари после изменений
        calendars = Calendar.objects.filter(consultant=consultant).order_by('name')
    
    # Генерируем абсолютные ссылки для каждого календаря
    calendars_with_links = []
    for calendar in calendars:
        booking_url = request.build_absolute_uri(f'/book/{calendar.id}/')
        calendars_with_links.append({
            'calendar': calendar,
            'booking_url': booking_url
        })
    
    return render(request, 'consultant_menu/calendars.html', {
        'calendars_with_links': calendars_with_links,
        'calendars': calendars,  # Оставляем для обратной совместимости
        'success': success,
        'error': error
    })

def calendar_view(request, calendar_id):
    '''Страница календаря'''''
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        consultant = Consultant.objects.get(user=request.user)
        calendar = Calendar.objects.get(id=calendar_id, consultant=consultant)
    except (Consultant.DoesNotExist, Calendar.DoesNotExist):
        return redirect('calendars')

    time_slots_by_day = {}
    for day_num in range(7):  # 0-6 для дней недели
        time_slots_by_day[day_num] = TimeSlot.objects.filter(
            calendar=calendar,
            day_of_week=day_num
        ).order_by('start_time')

    success = None
    error = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_time_slot':
            day_of_week = request.POST.get('day_of_week')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')

            if day_of_week and start_time and end_time:
                TimeSlot.objects.create(
                    calendar=calendar,
                    day_of_week=int(day_of_week),
                    start_time=start_time,
                    end_time=end_time
                )
                success = 'Временное окно добавлено!'
            else:
                error = 'Заполните все поля'

        elif action == 'delete_time_slot':
            slot_id = request.POST.get('slot_id')
            try:
                slot = TimeSlot.objects.get(id=slot_id, calendar=calendar)
                slot.delete()
                success = 'Временное окно удалено'
            except TimeSlot.DoesNotExist:
                error = 'Временное окно не найдено'

        # Перезагружаем слоты
        for day_num in range(7):
            time_slots_by_day[day_num] = TimeSlot.objects.filter(
                calendar=calendar,
                day_of_week=day_num
            ).order_by('start_time')

    # Названия дней недели
    days_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    days_short = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

    return render(request, 'consultant_menu/calendar_detail.html', {
        'calendar': calendar,
        'time_slots_by_day': time_slots_by_day,
        'days_names': days_names,
        'days_short': days_short,
        'success': success,
        'error': error
    })


def calendar_settings_edit(request, calendar_id):
    """Редактирование настроек календаря (перерыв, лимит в день, запись за N часов)."""
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        consultant = Consultant.objects.get(user=request.user)
        calendar = Calendar.objects.get(id=calendar_id, consultant=consultant)
    except (Consultant.DoesNotExist, Calendar.DoesNotExist):
        return redirect('calendars')

    if request.method == 'POST':
        calendar.break_between_services_minutes = int(request.POST.get('break_between_services_minutes', 0) or 0)
        calendar.book_ahead_hours = int(request.POST.get('book_ahead_hours', 24) or 24)
        calendar.max_services_per_day = int(request.POST.get('max_services_per_day', 0) or 0)
        calendar.reminder_hours_first = int(request.POST.get('reminder_hours_first', 24) or 24)
        calendar.reminder_hours_second = int(request.POST.get('reminder_hours_second', 1) or 1)
        calendar.save()
        return redirect('calendar_detail', calendar_id=calendar.id)

    return render(request, 'consultant_menu/calendar_settings_edit.html', {
        'calendar': calendar,
    })


def public_booking_view(request, calendar_id):
    """Публичная страница записи через календарь (без авторизации)"""
    try:
        calendar = Calendar.objects.get(id=calendar_id, is_active=True)
    except Calendar.DoesNotExist:
        raise Http404("Календарь не найден")

    consultant = calendar.consultant
    services = Service.objects.filter(consultant=consultant, is_active=True)

    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        booking_date = request.POST.get('booking_date')
        booking_time = request.POST.get('booking_time')
        booking_end_time = request.POST.get('booking_end_time')

        client_name = request.POST.get('client_name')
        client_phone = request.POST.get('client_phone', '').strip()
        client_email = request.POST.get('client_email', '').strip()

        # Контакт: телефон обязателен для связи. Telegram подтверждается на странице успеха (приложение или браузер).
        if not client_phone:
            return render(request, 'consultant_menu/public_booking.html', {
                'calendar': calendar,
                'services': services,
                'error': 'Укажите телефон для связи'
            })

        if not all([service_id, booking_date, booking_time, booking_end_time, client_name]):
            return render(request, 'consultant_menu/public_booking.html', {
                'calendar': calendar,
                'services': services,
                'error': 'Заполните все обязательные поля'
            })

        try:
            service = Service.objects.get(id=service_id, consultant=consultant, is_active=True)

            # Преобразуем время
            date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()
            start_time_obj = datetime.combine(date_obj, datetime.strptime(booking_time, '%H:%M').time())
            end_time_obj = datetime.combine(date_obj, datetime.strptime(booking_end_time, '%H:%M').time())

            # Длительность должна совпадать с услугой (допуск 1 мин)
            duration_minutes = (end_time_obj - start_time_obj).total_seconds() / 60
            if abs(duration_minutes - service.duration_minutes) > 1:
                return render(request, 'consultant_menu/public_booking.html', {
                    'calendar': calendar,
                    'services': services,
                    'error': 'Неверная длительность. Выберите время из списка доступных слотов.'
                })

            day_of_week = date_obj.weekday()

            # Время записи должно попадать в одно из доступных окон консультанта
            start_time_val = start_time_obj.time()
            end_time_val = end_time_obj.time()
            time_slot = TimeSlot.objects.filter(
                calendar=calendar,
                day_of_week=day_of_week,
                start_time__lte=start_time_val,
                end_time__gte=end_time_val,
                is_available=True
            ).first()
            if not time_slot:
                return render(request, 'consultant_menu/public_booking.html', {
                    'calendar': calendar,
                    'services': services,
                    'error': 'Выбранное время не входит в доступные окна приёма. Выберите предложенное время или введите своё в пределах показанных окон.'
                })

            break_minutes = getattr(calendar, 'break_between_services_minutes', 0) or 0
            break_delta = timedelta(minutes=break_minutes)

            with transaction.atomic():
                # Блокируем записи на эту дату, чтобы не допустить двойную запись при одновременной отправке
                existing_bookings = list(
                    Booking.objects.select_for_update().filter(
                        calendar=calendar,
                        booking_date=booking_date,
                        status__in=['pending', 'confirmed']
                    )
                )

                for booking in existing_bookings:
                    if not booking.booking_end_time:
                        continue
                    booking_start = datetime.combine(date_obj, booking.booking_time)
                    booking_end = datetime.combine(date_obj, booking.booking_end_time)
                    # Учитываем перерыв между консультациями: между концом одной и началом другой должно быть >= break_minutes
                    if not (end_time_obj + break_delta <= booking_start or start_time_obj >= booking_end + break_delta):
                        return render(request, 'consultant_menu/public_booking.html', {
                            'calendar': calendar,
                            'services': services,
                            'error': 'Это время уже занято или слишком близко к другой записи. Выберите другое.'
                        })

                # Создаем запись (link_token для подтверждения в Telegram — необязательно)
                link_token = uuid.uuid4().hex[:24]
                booking = Booking.objects.create(
                    service=service,
                    time_slot=time_slot,
                    calendar=calendar,
                    booking_date=booking_date,
                    booking_time=booking_time,
                    booking_end_time=booking_end_time,
                    client_name=client_name,
                    client_phone=client_phone or "",
                    client_telegram="",  # заполняется при подтверждении в Telegram (приложение или браузер)
                    client_email=client_email or "",
                    status='pending',
                    link_token=link_token,
                )

            return render(request, 'consultant_menu/booking_success.html', {
                'booking': booking,
                'service': service,
                'telegram_bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', ''),
            })

        except (Service.DoesNotExist, ValueError) as e:
            return render(request, 'consultant_menu/public_booking.html', {
                'calendar': calendar,
                'services': services,
                'error': 'Ошибка при создании записи'
            })

    return render(request, 'consultant_menu/public_booking.html', {
        'calendar': calendar,
        'services': services
    })


@csrf_exempt
@require_http_methods(["POST"])
def confirm_booking_telegram_api(request):
    """
    API для бота: привязать telegram_id к записи по одноразовому link_token.
    POST JSON: {"link_token": "...", "telegram_id": 123456789}
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        import json
        data = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    link_token = (data.get('link_token') or '').strip()
    telegram_id = data.get('telegram_id')
    if not link_token or telegram_id is None:
        return JsonResponse({'success': False, 'error': 'link_token and telegram_id required'}, status=400)
    try:
        booking = Booking.objects.get(link_token=link_token)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid or expired link'}, status=404)
    booking.telegram_id = int(telegram_id)
    booking.link_token = None
    booking.save(update_fields=['telegram_id', 'link_token'])
    # Сразу отправить клиенту сообщение «Вы записаны» с деталями консультации
    try:
        from consultant_menu.telegram_reminders import send_telegram_to_client, format_client_booked_message
        text = format_client_booked_message(booking)
        send_telegram_to_client(booking.telegram_id, text)
    except Exception:
        pass
    return JsonResponse({'success': True, 'message': 'Telegram привязан к записи'})


def connect_telegram_app(request):
    """
    Подключение Telegram специалиста через приложение.
    Генерирует одноразовый токен и перенаправляет в бота (t.me/Bot?start=connect_spec_TOKEN).
    """
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')
    integration, _ = Integration.objects.get_or_create(consultant=consultant)
    # Включаем уведомления и создаём токен
    integration.telegram_enabled = True
    integration.telegram_link_token = uuid.uuid4().hex
    integration.telegram_link_token_created_at = timezone.now()
    integration.save(update_fields=['telegram_enabled', 'telegram_link_token', 'telegram_link_token_created_at'])
    bot_username = (getattr(settings, 'TELEGRAM_BOT_USERNAME', '') or '').strip().lstrip('@')
    if not bot_username:
        request.session['integrations_error'] = 'TELEGRAM_BOT_USERNAME не настроен.'
        return redirect('integrations')
    url = f"https://t.me/{bot_username}?start=connect_spec_{integration.telegram_link_token}"
    return redirect(url)


@csrf_exempt
@require_http_methods(["POST"])
def confirm_specialist_telegram_api(request):
    """
    API для бота: привязать telegram_id специалиста к Integration по одноразовому link_token.
    POST JSON: {"link_token": "...", "telegram_id": 123456789}
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        import json
        data = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    link_token = (data.get('link_token') or '').strip()
    telegram_id = data.get('telegram_id')
    if not link_token or telegram_id is None:
        logger.warning("confirm_specialist_telegram_api: missing link_token or telegram_id")
        return JsonResponse({'success': False, 'error': 'link_token and telegram_id required'}, status=400)
    try:
        integration = Integration.objects.get(telegram_link_token=link_token)
    except Integration.DoesNotExist:
        logger.warning("confirm_specialist_telegram_api: Integration not found for token (len=%s)", len(link_token))
        return JsonResponse({'success': False, 'error': 'Ссылка недействительна или уже использована'}, status=404)
    created_at = integration.telegram_link_token_created_at
    # Токен действует 30 минут (1800 сек)
    if created_at and (timezone.now() - created_at).total_seconds() > 1800:
        integration.telegram_link_token = None
        integration.telegram_link_token_created_at = None
        integration.save(update_fields=['telegram_link_token', 'telegram_link_token_created_at'])
        logger.info("confirm_specialist_telegram_api: token expired for consultant id=%s", integration.consultant_id)
        return JsonResponse({'success': False, 'error': 'Ссылка истекла. Запросите новую на странице интеграций.'}, status=400)
    integration.telegram_chat_id = str(int(telegram_id))
    integration.telegram_connected = True
    integration.telegram_enabled = True
    integration.telegram_link_token = None
    integration.telegram_link_token_created_at = None
    integration.save(update_fields=['telegram_chat_id', 'telegram_connected', 'telegram_enabled', 'telegram_link_token', 'telegram_link_token_created_at'])
    logger.info("confirm_specialist_telegram_api: OK consultant_id=%s telegram_id=%s", integration.consultant_id, telegram_id)
    return JsonResponse({'success': True, 'message': 'Telegram подключен'})


def _verify_telegram_widget_hash(payload: dict, received_hash: str) -> bool:
    """Проверка подписи данных от Telegram Login Widget. payload — все поля кроме hash."""
    bot_token = (getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or '').strip()
    if not bot_token or not received_hash:
        return False
    data_check_string = '\n'.join(f'{k}={payload[k]}' for k in sorted(payload.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_hash)


def confirm_booking_telegram_browser(request, link_token):
    """
    Страница подтверждения записи через Telegram в браузере (Login Widget).
    Показывает виджет; при возврате с hash JS отправляет данные в API.
    При ?telegram=confirmed — показываем сообщение об успехе.
    """
    if request.GET.get('telegram') == 'confirmed':
        return render(request, 'consultant_menu/confirm_telegram_browser.html', {
            'error': None,
            'success': True,
            'link_token': None,
        })
    try:
        booking = Booking.objects.get(link_token=link_token)
    except Booking.DoesNotExist:
        return render(request, 'consultant_menu/confirm_telegram_browser.html', {
            'error': 'Ссылка недействительна или уже использована',
            'link_token': None,
            'success': False,
        })
    bot_username = (getattr(settings, 'TELEGRAM_BOT_USERNAME', '') or '').strip().lstrip('@')
    auth_url = request.build_absolute_uri(request.path)
    return render(request, 'consultant_menu/confirm_telegram_browser.html', {
        'link_token': link_token,
        'auth_url': auth_url,
        'telegram_bot_username': bot_username,
        'error': None,
        'success': False,
    })


@csrf_exempt
@require_http_methods(["POST"])
def confirm_booking_telegram_browser_api(request):
    """
    API для подтверждения записи через Telegram Login Widget (браузер).
    POST JSON: { "link_token": "...", "id": 123, "first_name": "...", "username": "...", "auth_date": 123, "hash": "..." }
    Проверяем подпись, привязываем telegram_id к записи, отправляем сообщение в бота.
    """
    try:
        import json
        data = json.loads(request.body) if request.body else {}
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    link_token = (data.get('link_token') or '').strip()
    telegram_id = data.get('id')
    auth_date = data.get('auth_date')
    received_hash = (data.get('hash') or '').strip()
    if not link_token or telegram_id is None or not received_hash:
        return JsonResponse({'success': False, 'error': 'link_token, id and hash required'}, status=400)
    payload = {k: str(data[k]) for k in ['id', 'first_name', 'username', 'auth_date'] if k in data and data[k] is not None}
    if 'id' not in payload:
        payload['id'] = str(telegram_id)
    if 'auth_date' not in payload:
        payload['auth_date'] = str(auth_date or '')
    if not _verify_telegram_widget_hash(payload, received_hash):
        return JsonResponse({'success': False, 'error': 'Invalid signature'}, status=400)
    auth_ts = int(payload.get('auth_date', 0) or 0)
    if auth_ts and (timezone.now().timestamp() - auth_ts) > 86400:
        return JsonResponse({'success': False, 'error': 'Data expired'}, status=400)
    try:
        booking = Booking.objects.get(link_token=link_token)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid or expired link'}, status=404)
    booking.telegram_id = int(telegram_id)
    booking.link_token = None
    username = data.get('username') or ''
    if username and not username.startswith('@'):
        username = '@' + username
    booking.client_telegram = username
    booking.save(update_fields=['telegram_id', 'link_token', 'client_telegram'])
    try:
        from consultant_menu.telegram_reminders import send_telegram_to_client, format_client_booked_message
        text = format_client_booked_message(booking)
        send_telegram_to_client(booking.telegram_id, text)
    except Exception:
        pass
    return JsonResponse({'success': True, 'message': 'Telegram привязан, сообщение отправлено'})


def get_available_slots_api(request, calendar_id):
    """API для получения доступных слотов внутри окон (AJAX запрос)"""
    try:
        calendar = Calendar.objects.get(id=calendar_id, is_active=True)
    except Calendar.DoesNotExist:
        return JsonResponse({'error': 'Календарь не найден'}, status=404)

    service_id = request.GET.get('service_id')
    booking_date = request.GET.get('date')

    if not booking_date:
        return JsonResponse({'error': 'Не указана дата'}, status=400)

    if not service_id:
        return JsonResponse({'error': 'Не указана услуга'}, status=400)

    try:
        service = Service.objects.get(id=service_id, consultant=calendar.consultant, is_active=True)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Услуга не найдена'}, status=404)

    # День недели
    date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()
    day_of_week = date_obj.weekday()

    # Получаем временные окна для этого дня
    time_slots = TimeSlot.objects.filter(
        calendar=calendar,
        day_of_week=day_of_week,
        is_available=True
    ).order_by('start_time')

    # Получаем существующие записи на эту дату
    existing_bookings = list(Booking.objects.filter(
        calendar=calendar,
        booking_date=booking_date,
        status__in=['pending', 'confirmed']
    ))

    # Лимит записей в день: если уже достигнут — не показываем слоты
    max_per_day = getattr(calendar, 'max_services_per_day', 0) or 0
    if max_per_day > 0 and len(existing_bookings) >= max_per_day:
        return JsonResponse({'available_slots': [], 'available_windows': []})

    break_minutes = getattr(calendar, 'break_between_services_minutes', 0) or 0
    break_delta = timedelta(minutes=break_minutes)
    now = datetime.now()
    book_ahead_hours = getattr(calendar, 'book_ahead_hours', 24) or 24
    min_start = now + timedelta(hours=book_ahead_hours)

    # Шаг для генерации слотов (15 минут)
    step_minutes = 15

    # Доступные окна (диапазоны) на этот день — чтобы клиент видел, какие окна остались, и мог ввести своё время
    available_windows = []
    available_times = []

    for time_slot in time_slots:
        # Проверяем, что услуга помещается в окно
        slot_start = datetime.combine(date_obj, time_slot.start_time)
        slot_end = datetime.combine(date_obj, time_slot.end_time)
        slot_duration = (slot_end - slot_start).total_seconds() / 60

        if service.duration_minutes > slot_duration:
            continue  # Услуга не помещается в это окно

        available_windows.append({
            'start_time': time_slot.start_time.strftime('%H:%M'),
            'end_time': time_slot.end_time.strftime('%H:%M'),
        })

        # Генерируем возможные времена начала (каждые 15 минут)
        current_time = slot_start
        service_duration = timedelta(minutes=service.duration_minutes)

        while current_time + service_duration <= slot_end:
            # Не показывать слоты раньше чем за book_ahead_hours от текущего момента
            if current_time < min_start:
                current_time += timedelta(minutes=step_minutes)
                continue

            start_time = current_time.time()
            end_time = (current_time + service_duration).time()

            # Проверяем пересечение с существующими записями с учётом перерыва между консультациями
            overlaps = False
            for booking in existing_bookings:
                if not booking.booking_end_time:
                    continue
                booking_start = datetime.combine(date_obj, booking.booking_time)
                booking_end = datetime.combine(date_obj, booking.booking_end_time)
                if not (current_time + service_duration + break_delta <= booking_start or current_time >= booking_end + break_delta):
                    overlaps = True
                    break

            if not overlaps:
                available_times.append({
                    'start_time': start_time.strftime('%H:%M'),
                    'end_time': end_time.strftime('%H:%M'),
                })

            # Переходим к следующему слоту (шаг 15 минут)
            current_time += timedelta(minutes=step_minutes)

    return JsonResponse({
        'available_slots': available_times,
        'available_windows': available_windows,
    })

# ========== УСЛУГИ ==========
def services_view(request):
    """Страница услуг"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')
    services = Service.objects.filter(consultant=consultant).order_by('name')
    
    success = None
    error = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_service':
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            duration_minutes = request.POST.get('duration_minutes', 60)
            price = request.POST.get('price') or None
            
            if name:
                Service.objects.create(
                    consultant=consultant,
                    name=name,
                    description=description,
                    duration_minutes=int(duration_minutes),
                    price=price
                )
                success = 'Услуга создана успешно!'
            else:
                error = 'Укажите название услуги'
        
        elif action == 'toggle_service':
            service_id = request.POST.get('service_id')
            try:
                service = Service.objects.get(id=service_id, consultant=consultant)
                service.is_active = not service.is_active
                service.save()
                success = 'Статус услуги изменен'
            except Service.DoesNotExist:
                error = 'Услуга не найдена'
        
        elif action == 'delete_service':
            service_id = request.POST.get('service_id')
            try:
                service = Service.objects.get(id=service_id, consultant=consultant)
                service.delete()
                success = 'Услуга удалена'
            except Service.DoesNotExist:
                error = 'Услуга не найдена'
        
        # Перезагружаем услуги после изменений
        services = Service.objects.filter(consultant=consultant).order_by('name')
    
    return render(request, 'consultant_menu/services.html', {
        'services': services,
        'success': success,
        'error': error
    })



def  booking_view(request):
    '''Страница клиенты, которые уже записались и проведеннные консультации'''
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')

    calendars = Calendar.objects.filter(consultant=consultant)
    bookings = Booking.objects.filter(calendar__in = calendars).order_by('booking_date', 'booking_time')
    status_filter = request.GET.get('status', 'all')

    if status_filter != 'all':
        bookings = bookings.filter(status=status_filter)

    today = date.today()
    now = datetime.now().time()

    if status_filter == 'cancelled':
        upcoming_bookings = bookings
        past_bookings = Booking.objects.none()
    else:
        upcoming_bookings = bookings.filter(
            booking_date__gte=today
        ).exclude(status='cancelled')

        past_bookings = bookings.filter(
            booking_date__lt=today
        ) | bookings.filter(
            booking_date=today,
            booking_time__lt=now
        )

    if request.method == 'POST':
        action = request.POST.get('action')
        booking_id = request.POST.get('booking_id')

        try:
            booking = Booking.objects.get(id=booking_id, calendar__in=calendars)

            if action == 'confirm':
                booking.status = 'confirmed'
                booking.save()
            elif action == 'cancel':
                booking.status = 'cancelled'
                booking.save()
            elif action == 'complete':
                booking.status = 'completed'
                booking.save()

        except Booking.DoesNotExist:
            pass


        bookings = Booking.objects.filter(calendar__in = calendars).order_by('booking_date', 'booking_time')
        if status_filter:
            bookings = bookings.filter(status=status_filter)

    return render(request, 'consultant_menu/booking.html', {
        'upcoming_bookings': upcoming_bookings,
        'past_bookings': past_bookings,
        'status_filter': status_filter,
        'today': today
    })



def profile_view(request):
    '''Страница профиля консультанта'''
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')

    success = None
    error = None
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            # Обновляем основную информацию о консультанте
            consultant.first_name = request.POST.get('first_name', '')
            consultant.last_name = request.POST.get('last_name', '')
            consultant.middle_name = request.POST.get('middle_name', '')
            consultant.phone = request.POST.get('phone', '')
            consultant.telegram_nickname = request.POST.get('telegram_nickname', '')
            consultant.email = request.POST.get('email', '')

            # Обновляем поля профиля
            consultant.profile_description = request.POST.get('profile_description', '')
            consultant.video_link = _normalize_url(request.POST.get('video_link'))
            consultant.social_instagram = _normalize_url(request.POST.get('social_instagram'))
            consultant.social_facebook = _normalize_url(request.POST.get('social_facebook'))
            consultant.social_vk = _normalize_url(request.POST.get('social_vk'))
            consultant.social_telegram = _normalize_url(request.POST.get('social_telegram'))
            consultant.social_youtube = _normalize_url(request.POST.get('social_youtube'))
            consultant.website = _normalize_url(request.POST.get('website'))

            if 'profile_photo' in request.FILES:
                if consultant.profile_photo:
                    try:
                        if os.path.isfile(consultant.profile_photo.path):
                            os.remove(consultant.profile_photo.path)
                    except:
                        pass

                consultant.profile_photo = request.FILES['profile_photo']

            try:
                consultant.save()
                success = 'Профиль успешно обновлен!'
            except Exception as e:
                error = f'Ошибка при обновлении: {str(e)}'

    # Подключённые способы входа (Telegram, Google, почта) для блока «Способы входа»
    connected_providers = set(
        sa.provider for sa in SocialAccount.objects.filter(user=request.user)
    )
    primary_email = None
    primary_obj = EmailAddress.objects.filter(user=request.user, primary=True).first()
    if primary_obj:
        primary_email = primary_obj.email

    return render(request, 'consultant_menu/profile.html', {
        'consultant': consultant,
        'success': success,
        'error': error,
        'connected_providers': connected_providers,
        'primary_email': primary_email,
    })


# ========== ИНТЕГРАЦИИ ==========
def google_calendar_connect(request):
    """Редирект на Google OAuth для доступа к календарю (scope calendar.events)."""
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or ''
    if not client_id or not client_secret:
        return redirect('integrations')
    try:
        from google_auth_oauthlib.flow import Flow
        # Без завершающего слэша — в Google Console добавьте тот же URL: https://allyourclients.ru/integrations/google/callback
        redirect_uri = request.build_absolute_uri(reverse('google_calendar_callback')).rstrip('/')
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=getattr(settings, 'GOOGLE_CALENDAR_SCOPES', ['https://www.googleapis.com/auth/calendar.events']),
        )
        flow.redirect_uri = redirect_uri
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            state=str(consultant.id),
        )
        request.session['google_calendar_oauth_state'] = state
        return redirect(authorization_url)
    except Exception:
        request.session['integrations_error'] = 'Ошибка подключения Google Calendar. Проверьте настройки GOOGLE_OAUTH в .env.'
        return redirect('integrations')


def google_calendar_callback(request):
    """Callback после авторизации Google: сохраняем refresh_token в Integration."""
    if not request.user.is_authenticated:
        return redirect('login')
    if request.GET.get('error'):
        request.session['integrations_error'] = 'Доступ к Google Calendar не был предоставлен.'
        return redirect('integrations')
    state = request.session.get('google_calendar_oauth_state')
    code = request.GET.get('code')
    if not code or not state:
        request.session['integrations_error'] = 'Неверный ответ от Google. Попробуйте снова.'
        return redirect('integrations')
    try:
        consultant_id = int(state)
        consultant = Consultant.objects.get(id=consultant_id)
        if consultant.user_id != request.user.id:
            request.session['integrations_error'] = 'Доступ запрещён.'
            return redirect('integrations')
    except (ValueError, Consultant.DoesNotExist):
        request.session['integrations_error'] = 'Сессия истекла. Попробуйте снова.'
        return redirect('integrations')
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or ''
    if not client_id or not client_secret:
        request.session['integrations_error'] = 'Google Calendar не настроен.'
        return redirect('integrations')
    try:
        from google_auth_oauthlib.flow import Flow
        redirect_uri = request.build_absolute_uri(reverse('google_calendar_callback')).rstrip('/')
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=getattr(settings, 'GOOGLE_CALENDAR_SCOPES', ['https://www.googleapis.com/auth/calendar.events']),
        )
        flow.redirect_uri = redirect_uri
        flow.fetch_token(code=code)
        credentials = flow.credentials
        integration, _ = Integration.objects.get_or_create(consultant=consultant)
        integration.google_refresh_token = credentials.refresh_token or ''
        integration.google_calendar_id = integration.google_calendar_id or 'primary'
        integration.google_calendar_connected = True
        integration.google_calendar_enabled = True
        integration.save()
        if 'google_calendar_oauth_state' in request.session:
            del request.session['google_calendar_oauth_state']
        request.session['integrations_success'] = 'Google Calendar успешно подключён. Новые записи будут отображаться в календаре.'
        return redirect('integrations')
    except Exception as e:
        request.session['integrations_error'] = f'Ошибка сохранения доступа: {e}'
        return redirect('integrations')


def integrations_view(request):
    """Страница интеграций с сервисами"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    try:
        consultant = Consultant.objects.get(user=request.user)
    except Consultant.DoesNotExist:
        return redirect('home')
    
    # Создаем или получаем объект интеграции для консультанта
    integration, created = Integration.objects.get_or_create(consultant=consultant)
    
    success = request.session.pop('integrations_success', None)
    error = request.session.pop('integrations_error', None)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'toggle_google':
            integration.google_calendar_enabled = not integration.google_calendar_enabled
            integration.save()
            if integration.google_calendar_enabled:
                success = 'Google Calendar включен'
            else:
                success = 'Google Calendar отключен'
        
        elif action == 'connect_google':
            # Редирект на OAuth — обработка в google_calendar_callback
            return redirect('google_calendar_connect')
        
        elif action == 'disconnect_google':
            integration.google_calendar_connected = False
            integration.google_calendar_enabled = False
            integration.google_calendar_id = None
            integration.google_refresh_token = None
            integration.save()
            success = 'Google Calendar отключен'
        
        elif action == 'toggle_telegram':
            integration.telegram_enabled = not integration.telegram_enabled
            integration.save()
            if integration.telegram_enabled:
                success = 'Telegram уведомления включены (пока в режиме заглушки)'
            else:
                success = 'Telegram уведомления отключены'
        
        elif action == 'connect_telegram':
            integration.telegram_connected = True
            integration.telegram_bot_token = request.POST.get('bot_token', '')
            integration.telegram_chat_id = request.POST.get('chat_id', '')
            integration.save()
            success = 'Telegram подключен (заглушка - реальное подключение будет добавлено позже)'
        
        elif action == 'disconnect_telegram':
            integration.telegram_connected = False
            integration.telegram_enabled = False
            integration.telegram_bot_token = None
            integration.telegram_chat_id = None
            integration.telegram_link_token = None
            integration.telegram_link_token_created_at = None
            integration.save()
            success = 'Telegram отключен'
    
    return render(request, 'consultant_menu/integrations.html', {
        'integration': integration,
        'success': success,
        'error': error
    })

