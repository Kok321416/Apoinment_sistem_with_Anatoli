from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from datetime import datetime, date, time, timedelta
import uuid
from .models import Specialist, Appointment, UserProfile, TimeSlot, Calendar, Service, TelegramLinkToken
from telegram_bot.bot import send_appointment_notification
from .forms import UserRegistrationForm, AppointmentForm, CalendarForm, ServiceForm, TimeSlotForm


def home(request):
    """Главная страница"""
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile.user_type == 'specialist':
                return redirect('specialist_dashboard')
            else:
                return redirect('client_appointments')
        except UserProfile.DoesNotExist:
            pass
    return render(request, 'bookings/home.html')


def register(request):
    """Регистрация пользователя"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user_type = form.cleaned_data.get('user_type')
            telegram_username = form.cleaned_data.get('telegram_username')
            
            # Создаем профиль
            profile = UserProfile.objects.create(
                user=user,
                user_type=user_type,
                telegram_username=telegram_username
            )
            
            # Если специалист - создаем Specialist
            if user_type == 'specialist':
                specialization = form.cleaned_data.get('specialization')
                Specialist.objects.create(
                    user=user,
                    specialization=specialization
                )
            
            messages.success(request, 'Регистрация успешна! Войдите в систему.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'bookings/register.html', {'form': form})


def user_login(request):
    """Вход в систему"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            try:
                profile = user.profile
                if profile.user_type == 'specialist':
                    return redirect('specialist_dashboard')
                else:
                    return redirect('client_appointments')
            except UserProfile.DoesNotExist:
                return redirect('home')
        else:
            messages.error(request, 'Неверный логин или пароль')
    return render(request, 'bookings/login.html')


def user_logout(request):
    """Выход из системы"""
    from django.contrib.auth import logout
    logout(request)
    return redirect('home')


@login_required
def google_calendar_connect(request):
    """Редирект на Google OAuth для доступа к календарю (scope calendar.events)."""
    try:
        specialist = request.user.specialist
    except Specialist.DoesNotExist:
        messages.error(request, 'Доступно только для специалистов.')
        return redirect('home')
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or ''
    if not client_id or not client_secret:
        messages.error(request, 'Google Calendar не настроен. Обратитесь к администратору.')
        return redirect('specialist_calendars')
    try:
        from google_auth_oauthlib.flow import Flow
        redirect_uri = request.build_absolute_uri(reverse('google_calendar_callback'))
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
            state=str(specialist.id),
        )
        request.session['google_calendar_oauth_state'] = state
        return redirect(authorization_url)
    except Exception as e:
        messages.error(request, f'Ошибка подключения Google Calendar: {e}')
        return redirect('specialist_calendars')


@login_required
def google_calendar_callback(request):
    """Callback после авторизации Google: сохраняем refresh_token у специалиста."""
    if request.GET.get('error'):
        messages.error(request, 'Доступ к Google Calendar не был предоставлен.')
        return redirect('specialist_calendars')
    state = request.session.get('google_calendar_oauth_state')
    code = request.GET.get('code')
    if not code or not state:
        messages.error(request, 'Неверный ответ от Google.')
        return redirect('specialist_calendars')
    try:
        specialist_id = int(state)
        specialist = Specialist.objects.get(id=specialist_id)
        if specialist.user_id != request.user.id:
            messages.error(request, 'Доступ запрещён.')
            return redirect('specialist_calendars')
    except (ValueError, Specialist.DoesNotExist):
        messages.error(request, 'Сессия истекла. Попробуйте снова.')
        return redirect('specialist_calendars')
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '') or ''
    if not client_id or not client_secret:
        messages.error(request, 'Google Calendar не настроен.')
        return redirect('specialist_calendars')
    try:
        from google_auth_oauthlib.flow import Flow
        redirect_uri = request.build_absolute_uri(reverse('google_calendar_callback'))
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
        specialist.google_refresh_token = credentials.refresh_token or ''
        specialist.google_calendar_id = specialist.google_calendar_id or 'primary'
        specialist.save()
        if 'google_calendar_oauth_state' in request.session:
            del request.session['google_calendar_oauth_state']
        messages.success(request, 'Google Calendar успешно подключён. Новые записи будут отображаться в календаре.')
        return redirect('specialist_calendars')
    except Exception as e:
        messages.error(request, f'Ошибка сохранения доступа: {e}')
        return redirect('specialist_calendars')


@login_required
def specialist_dashboard(request):
    """Дашборд специалиста"""
    try:
        specialist = request.user.specialist
        # Сначала фильтруем, потом делаем срез
        upcoming = Appointment.objects.filter(
            specialist=specialist,
            status__in=['pending', 'confirmed']
        ).order_by('appointment_date')[:5]
        
        calendars = Calendar.objects.filter(specialist=specialist, is_active=True)[:5]
        services = Service.objects.filter(specialist=specialist, is_active=True)[:5]
        
        context = {
            'specialist': specialist,
            'upcoming_appointments': upcoming,
            'total_appointments': Appointment.objects.filter(specialist=specialist).count(),
            'calendars': calendars,
            'services': services,
            'total_calendars': Calendar.objects.filter(specialist=specialist).count(),
            'total_services': Service.objects.filter(specialist=specialist).count(),
        }
        return render(request, 'bookings/specialist/dashboard.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def link_telegram_specialist(request):
    """Страница привязки Telegram для специалиста: генерирует одноразовую ссылку t.me/bot?start=link_TOKEN."""
    try:
        request.user.specialist
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')
    # Удаляем старые неиспользованные токены этого пользователя
    TelegramLinkToken.objects.filter(user=request.user, used=False).delete()
    token_str = uuid.uuid4().hex[:32]
    TelegramLinkToken.objects.create(user=request.user, token=token_str)
    bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'All_Clients_bot').lstrip('@')
    link = f"https://t.me/{bot_username}?start=link_{token_str}"
    context = {'link': link, 'bot_username': bot_username}
    return render(request, 'bookings/specialist/link_telegram.html', context)


@login_required
def specialist_calendar(request):
    """Календарь специалиста"""
    try:
        specialist = request.user.specialist
        if request.method == 'POST':
            # Создание нового временного слота
            from datetime import date, time
            slot_date = request.POST.get('date')
            start_time_str = request.POST.get('start_time')
            end_time_str = request.POST.get('end_time')
            
            if slot_date and start_time_str and end_time_str:
                try:
                    slot_date = date.fromisoformat(slot_date)
                    start_time = time.fromisoformat(start_time_str)
                    end_time = time.fromisoformat(end_time_str)
                    
                    TimeSlot.objects.create(
                        specialist=specialist,
                        date=slot_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_available=True,
                        is_booked=False
                    )
                    messages.success(request, 'Временной слот успешно создан!')
                except Exception as e:
                    messages.error(request, f'Ошибка при создании слота: {str(e)}')
        
        time_slots = TimeSlot.objects.filter(specialist=specialist).order_by('date', 'start_time')
        context = {
            'specialist': specialist,
            'time_slots': time_slots,
        }
        return render(request, 'bookings/specialist/calendar.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def specialist_appointments(request):
    """Список записей специалиста"""
    try:
        specialist = request.user.specialist
        if request.method == 'POST':
            appointment_id = request.POST.get('appointment_id')
            action = request.POST.get('action')
            try:
                appointment = Appointment.objects.get(id=appointment_id, specialist=specialist)
                if action == 'confirm':
                    appointment.status = 'confirmed'
                    appointment.save()
                    messages.success(request, 'Запись подтверждена!')
            except Appointment.DoesNotExist:
                messages.error(request, 'Запись не найдена')
        
        appointments = Appointment.objects.filter(specialist=specialist).order_by('-appointment_date')
        context = {
            'specialist': specialist,
            'appointments': appointments,
        }
        return render(request, 'bookings/specialist/appointments.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def client_appointments(request):
    """Список записей клиента"""
    if request.method == 'POST':
        appointment_id = request.POST.get('appointment_id')
        action = request.POST.get('action')
        try:
            appointment = Appointment.objects.get(id=appointment_id, client=request.user)
            if action == 'cancel':
                appointment.status = 'cancelled'
                if appointment.time_slot:
                    appointment.time_slot.is_booked = False
                    appointment.time_slot.save()
                appointment.save()
                messages.success(request, 'Запись отменена!')
        except Appointment.DoesNotExist:
            messages.error(request, 'Запись не найдена')
    
    appointments = Appointment.objects.filter(client=request.user).order_by('-appointment_date')
    context = {
        'appointments': appointments,
    }
    return render(request, 'bookings/client/appointments.html', context)


def book_appointment(request, invite_link):
    """Запись на консультацию по пригласительной ссылке услуги"""
    service = get_object_or_404(Service, invite_link=invite_link, is_active=True)
    
    if request.method == 'POST':
        form = AppointmentForm(request.POST, service=service)
        if form.is_valid():
            calendar = service.calendar
            max_per_day = getattr(calendar, 'max_services_per_day', 0) or 0
            if max_per_day > 0:
                appt_date = form.cleaned_data.get('appointment_date')
                if appt_date:
                    slot_date = appt_date.date() if hasattr(appt_date, 'date') else appt_date
                    existing = Appointment.objects.filter(
                        calendar=calendar,
                        appointment_date__date=slot_date,
                        status__in=['pending', 'confirmed']
                    ).count()
                    if existing >= max_per_day:
                        messages.error(
                            request,
                            f'На эту дату достигнут лимит записей ({max_per_day} в день). Выберите другой день.'
                        )
                        context = {'service': service, 'specialist': service.specialist, 'form': form}
                        return render(request, 'bookings/book_appointment.html', context)
            appointment = form.save(commit=False)
            if request.user.is_authenticated:
                appointment.client = request.user
                # Обновляем telegram_id в профиле, если есть
                try:
                    profile = request.user.profile
                    if appointment.client_telegram and not profile.telegram_id:
                        # Можно попытаться найти telegram_id по username
                        pass
                except UserProfile.DoesNotExist:
                    pass
            
            appointment.specialist = service.specialist
            appointment.service = service
            appointment.calendar = service.calendar
            appointment.status = 'pending'
            appointment.save()
            
            # Отправляем уведомление в Telegram
            try:
                send_appointment_notification(appointment)
            except Exception as e:
                # Логируем ошибку, но не прерываем процесс
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Ошибка отправки уведомления в Telegram: {e}")
            
            messages.success(request, 'Запись успешно создана!')
            if appointment.client_telegram:
                bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', 'All_Clients_bot').lstrip('@')
                messages.info(
                    request,
                    f'Чтобы видеть запись в боте и получать уведомления, откройте @{bot_username} и нажмите /start.',
                )
            return redirect('book_appointment', invite_link=invite_link)
    else:
        form = AppointmentForm(service=service)
    
    context = {
        'service': service,
        'specialist': service.specialist,
        'form': form,
    }
    return render(request, 'bookings/book_appointment.html', context)


# Новые views для календарей и услуг
@login_required
def specialist_calendars(request):
    """Список календарей специалиста"""
    try:
        specialist = request.user.specialist
        calendars = Calendar.objects.filter(specialist=specialist).order_by('name')
        context = {
            'specialist': specialist,
            'calendars': calendars,
        }
        return render(request, 'bookings/specialist/calendars.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def calendar_create(request):
    """Создание календаря"""
    try:
        specialist = request.user.specialist
        if request.method == 'POST':
            form = CalendarForm(request.POST)
            if form.is_valid():
                calendar = form.save(commit=False)
                calendar.specialist = specialist
                calendar.save()
                messages.success(request, 'Календарь успешно создан!')
                return redirect('calendar_detail', calendar_id=calendar.id)
        else:
            form = CalendarForm()
        return render(request, 'bookings/specialist/calendar_form.html', {'form': form, 'specialist': specialist})
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def calendar_edit(request, calendar_id):
    """Редактирование календаря (в т.ч. настройки на каждый день)"""
    try:
        specialist = request.user.specialist
        calendar = get_object_or_404(Calendar, id=calendar_id, specialist=specialist)
        if request.method == 'POST':
            form = CalendarForm(request.POST, instance=calendar)
            if form.is_valid():
                form.save()
                messages.success(request, 'Настройки календаря сохранены.')
                return redirect('calendar_detail', calendar_id=calendar.id)
        else:
            form = CalendarForm(instance=calendar)
        return render(request, 'bookings/specialist/calendar_form.html', {
            'form': form, 'specialist': specialist, 'calendar': calendar,
        })
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def calendar_detail(request, calendar_id):
    """Детали календаря с временными слотами"""
    try:
        specialist = request.user.specialist
        calendar = get_object_or_404(Calendar, id=calendar_id, specialist=specialist)
        
        if request.method == 'POST':
            # Обработка создания слотов (может быть несколько для одного дня)
            date_str = request.POST.get('date')
            start_time_str = request.POST.get('start_time')
            end_time_str = request.POST.get('end_time')
            service_id = request.POST.get('service')
            
            if date_str and start_time_str and end_time_str:
                try:
                    slot_date = date.fromisoformat(date_str)
                    start_time = time.fromisoformat(start_time_str)
                    end_time = time.fromisoformat(end_time_str)
                    
                    # Проверка, что время окончания позже времени начала
                    if start_time >= end_time:
                        messages.error(request, 'Время окончания должно быть позже времени начала')
                    else:
                        # Проверка на пересечение с существующими слотами
                        existing_slots = TimeSlot.objects.filter(
                            calendar=calendar,
                            date=slot_date,
                            is_available=True
                        )
                        
                        overlaps = False
                        for existing in existing_slots:
                            # Проверка пересечения временных интервалов
                            if not (end_time <= existing.start_time or start_time >= existing.end_time):
                                overlaps = True
                                break
                        
                        if overlaps:
                            messages.error(request, 'Этот временной слот пересекается с существующим слотом')
                        else:
                            slot = TimeSlot.objects.create(
                                calendar=calendar,
                                date=slot_date,
                                start_time=start_time,
                                end_time=end_time,
                                is_available=True,
                                is_booked=False
                            )
                            
                            if service_id:
                                try:
                                    service = Service.objects.get(id=service_id, calendar=calendar)
                                    slot.service = service
                                    slot.save()
                                except Service.DoesNotExist:
                                    pass
                            
                            messages.success(request, 'Временной слот успешно создан!')
                except (ValueError, TypeError) as e:
                    messages.error(request, f'Ошибка при создании слота: {str(e)}')
            
            return redirect('calendar_detail', calendar_id=calendar_id)
        
        # Группировка слотов по дням
        time_slots = TimeSlot.objects.filter(calendar=calendar).order_by('date', 'start_time')
        slots_by_date = {}
        for slot in time_slots:
            date_key = slot.date  # Используем объект date напрямую
            if date_key not in slots_by_date:
                slots_by_date[date_key] = []
            slots_by_date[date_key].append(slot)
        
        services = Service.objects.filter(calendar=calendar, is_active=True)
        
        context = {
            'specialist': specialist,
            'calendar': calendar,
            'slots_by_date': slots_by_date,
            'services': services,
        }
        return render(request, 'bookings/specialist/calendar_detail.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def specialist_services(request):
    """Список услуг специалиста"""
    try:
        specialist = request.user.specialist
        services = Service.objects.filter(specialist=specialist).order_by('name')
        context = {
            'specialist': specialist,
            'services': services,
        }
        return render(request, 'bookings/specialist/services.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def service_create(request):
    """Создание услуги"""
    try:
        specialist = request.user.specialist
        if request.method == 'POST':
            form = ServiceForm(request.POST, specialist=specialist)
            if form.is_valid():
                service = form.save(commit=False)
                service.specialist = specialist
                service.save()
                messages.success(request, 'Услуга успешно создана!')
                return redirect('service_detail', service_id=service.id)
        else:
            form = ServiceForm(specialist=specialist)
        return render(request, 'bookings/specialist/service_form.html', {'form': form, 'specialist': specialist})
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')


@login_required
def service_detail(request, service_id):
    """Детали услуги"""
    try:
        specialist = request.user.specialist
        service = get_object_or_404(Service, id=service_id, specialist=specialist)
        
        # Генерация временных слотов в стиле Google Calendar
        if request.method == 'POST' and 'generate_slots_calendar' in request.POST:
            days = request.POST.getlist('days')  # Дни недели (0=Пн, 6=Вс)
            time_start_str = request.POST.get('time_start')
            time_end_str = request.POST.get('time_end')
            calendar = service.calendar
            # Интервал = длительность услуги + перерыв между услугами (настройка календаря)
            interval = service.duration + getattr(calendar, 'break_between_services_minutes', 0)
            interval = int(request.POST.get('interval', interval))
            period_start = request.POST.get('period_start')
            period_end = request.POST.get('period_end')
            max_per_day = getattr(calendar, 'max_services_per_day', 0) or 0

            if days and time_start_str and time_end_str and period_start and period_end:
                try:
                    start_date = date.fromisoformat(period_start)
                    end_date = date.fromisoformat(period_end)
                    time_start = time.fromisoformat(time_start_str)
                    time_end = time.fromisoformat(time_end_str)
                    selected_days = [int(d) for d in days]

                    slots_created = 0
                    current_date = start_date

                    while current_date <= end_date:
                        day_of_week = current_date.weekday()
                        if day_of_week in selected_days:
                            current_time = datetime.combine(current_date, time_start)
                            end_datetime = datetime.combine(current_date, time_end)
                            day_slots_count = 0

                            while current_time + timedelta(minutes=service.duration) <= end_datetime:
                                if max_per_day > 0 and day_slots_count >= max_per_day:
                                    break
                                slot_start = current_time.time()
                                slot_end = (current_time + timedelta(minutes=service.duration)).time()

                                if not TimeSlot.objects.filter(
                                    calendar=service.calendar,
                                    service=service,
                                    date=current_date,
                                    start_time=slot_start
                                ).exists():
                                    TimeSlot.objects.create(
                                        calendar=service.calendar,
                                        service=service,
                                        date=current_date,
                                        start_time=slot_start,
                                        end_time=slot_end,
                                        is_available=True,
                                        is_booked=False
                                    )
                                    slots_created += 1
                                    day_slots_count += 1

                                current_time += timedelta(minutes=interval)

                        current_date += timedelta(days=1)

                    messages.success(request, f'Создано {slots_created} временных слотов!')
                except Exception as e:
                    messages.error(request, f'Ошибка при создании слотов: {str(e)}')
        
        # Старая генерация (для обратной совместимости)
        elif request.method == 'POST' and 'generate_slots' in request.POST:
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            calendar = service.calendar
            break_minutes = getattr(calendar, 'break_between_services_minutes', 0) or service.buffer_time
            max_per_day = getattr(calendar, 'max_services_per_day', 0) or 0

            if start_date and end_date:
                try:
                    start = date.fromisoformat(start_date)
                    end = date.fromisoformat(end_date)
                    current_date = start
                    slots_created = 0
                    while current_date <= end:
                        current_time = datetime.combine(current_date, service.work_hours_start)
                        end_time_dt = datetime.combine(current_date, service.work_hours_end)
                        day_slots_count = 0

                        while current_time + timedelta(minutes=service.duration) <= end_time_dt:
                            if max_per_day > 0 and day_slots_count >= max_per_day:
                                break
                            slot_start = current_time.time()
                            slot_end = (current_time + timedelta(minutes=service.duration)).time()

                            if not TimeSlot.objects.filter(
                                calendar=service.calendar,
                                service=service,
                                date=current_date,
                                start_time=slot_start
                            ).exists():
                                TimeSlot.objects.create(
                                    calendar=service.calendar,
                                    service=service,
                                    date=current_date,
                                    start_time=slot_start,
                                    end_time=slot_end,
                                    is_available=True,
                                    is_booked=False
                                )
                                slots_created += 1
                                day_slots_count += 1

                            current_time += timedelta(minutes=service.duration + break_minutes)

                        current_date += timedelta(days=1)

                    messages.success(request, f'Создано {slots_created} временных слотов!')
                except Exception as e:
                    messages.error(request, f'Ошибка при создании слотов: {str(e)}')
        
        time_slots = TimeSlot.objects.filter(service=service).order_by('date', 'start_time')
        
        context = {
            'specialist': specialist,
            'service': service,
            'time_slots': time_slots,
        }
        return render(request, 'bookings/specialist/service_detail.html', context)
    except Specialist.DoesNotExist:
        messages.error(request, 'Вы не являетесь специалистом')
        return redirect('home')
