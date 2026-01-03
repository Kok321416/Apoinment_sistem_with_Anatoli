from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from consultant_menu.models import Consultant, Clients, Category, Calendar, Service, TimeSlot, Booking
from django.http import Http404, JsonResponse
from datetime import datetime, date, timedelta


# ========== РЕГИСТРАЦИЯ (HTML) ==========
def register_view(request):
    """Регистрация через HTML форму"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not email or not password:
            return render(request, 'consultant_menu/register.html', {'error': 'Заполните все поля'})
        
        if User.objects.filter(username=email).exists():
            return render(request, 'consultant_menu/register.html', {'error': 'Пользователь с таким email уже зарегистрирован'})
        
        # Создаем пользователя
        user = User.objects.create_user(username=email, email=email, password=password)
        
        # Создаем консультанта
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
        
        # Автоматически логиним
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
    
    return render(request, 'consultant_menu/calendars.html', {
        'calendars': calendars,
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
        booking_time = request.POST.get('booking_time')  # "09:00"
        booking_end_time = request.POST.get('booking_end_time')  # "09:15"

        client_name = request.POST.get('client_name')
        client_phone = request.POST.get('client_phone')
        client_email = request.POST.get('client_email', '')

        if not all([service_id, booking_date, booking_time, booking_end_time, client_name, client_phone]):
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

            # Проверяем пересечения с существующими записями
            existing_bookings = Booking.objects.filter(
                calendar=calendar,
                booking_date=booking_date,
                status__in=['pending', 'confirmed']
            )

            for booking in existing_bookings:
                # Пропускаем записи без времени окончания (старые записи)
                if not booking.booking_end_time:
                    continue
                    
                booking_start = datetime.combine(date_obj, booking.booking_time)
                booking_end = datetime.combine(date_obj, booking.booking_end_time)

                # Проверка пересечения
                if not (end_time_obj <= booking_start or start_time_obj >= booking_end):
                    return render(request, 'consultant_menu/public_booking.html', {
                        'calendar': calendar,
                        'services': services,
                        'error': 'Это время уже занято. Выберите другое.'
                    })

            # Находим подходящее окно (для информации, необязательно)
            day_of_week = date_obj.weekday()
            time_slot = TimeSlot.objects.filter(
                calendar=calendar,
                day_of_week=day_of_week,
                start_time__lte=booking_time,
                end_time__gte=booking_end_time,
                is_available=True
            ).first()

            # Создаем запись
            booking = Booking.objects.create(
                service=service,
                time_slot=time_slot,  # Может быть None
                calendar=calendar,
                booking_date=booking_date,
                booking_time=booking_time,
                booking_end_time=booking_end_time,  # НОВОЕ ПОЛЕ
                client_name=client_name,
                client_phone=client_phone,
                client_email=client_email,
                status='pending'
            )

            return render(request, 'consultant_menu/booking_success.html', {
                'booking': booking,
                'service': service
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
    existing_bookings = Booking.objects.filter(
        calendar=calendar,
        booking_date=booking_date,
        status__in=['pending', 'confirmed']
    )

    # Шаг для генерации слотов (15 минут)
    step_minutes = 15

    # Генерируем возможные временные слоты
    available_times = []

    for time_slot in time_slots:
        # Проверяем, что услуга помещается в окно
        slot_start = datetime.combine(date_obj, time_slot.start_time)
        slot_end = datetime.combine(date_obj, time_slot.end_time)
        slot_duration = (slot_end - slot_start).total_seconds() / 60

        if service.duration_minutes > slot_duration:
            continue  # Услуга не помещается в это окно

        # Генерируем возможные времена начала (каждые 15 минут)
        current_time = slot_start
        service_duration = timedelta(minutes=service.duration_minutes)

        while current_time + service_duration <= slot_end:
            start_time = current_time.time()
            end_time = (current_time + service_duration).time()

            # Проверяем, не пересекается ли с существующими записями
            overlaps = False
            for booking in existing_bookings:
                # Пропускаем записи без времени окончания (старые записи)
                if not booking.booking_end_time:
                    continue
                    
                booking_start = datetime.combine(date_obj, booking.booking_time)
                booking_end = datetime.combine(date_obj, booking.booking_end_time)

                # Проверка пересечения: новое время не должно пересекаться с существующим
                if not (current_time + service_duration <= booking_start or current_time >= booking_end):
                    overlaps = True
                    break

            if not overlaps:
                available_times.append({
                    'start_time': start_time.strftime('%H:%M'),
                    'end_time': end_time.strftime('%H:%M'),
                })

            # Переходим к следующему слоту (шаг 15 минут)
            current_time += timedelta(minutes=step_minutes)

    return JsonResponse({'available_slots': available_times})

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


def clients_view(request):
    """Страница клиентов (временная заглушка)"""
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'consultant_menu/home.html')  # Пока возвращаем на главную
