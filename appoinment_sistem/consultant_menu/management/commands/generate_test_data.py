"""
Management command для создания тестовых данных:
консультантов, календарей, услуг, временных окон и записей.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta, time
import random
import os

from consultant_menu.models import (
    Consultant, Category, Calendar, Service, TimeSlot, Booking
)


class Command(BaseCommand):
    help = 'Создает тестовые данные: консультантов, календари, услуги и записи'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаю создание тестовых данных...'))
        
        # Данные для консультантов
        consultants_data = [
            {
                'first_name': 'Анна',
                'last_name': 'Петрова',
                'middle_name': 'Ивановна',
                'email': 'anna.petrova@example.com',
                'phone': '+79001234567',
                'telegram_nickname': '@anna_petrova',
                'username': 'anna_petrova',
                'password': 'anna123456',
                'category': 'Психолог'
            },
            {
                'first_name': 'Дмитрий',
                'last_name': 'Соколов',
                'middle_name': 'Викторович',
                'email': 'dmitry.sokolov@example.com',
                'phone': '+79001234568',
                'telegram_nickname': '@dmitry_sokolov',
                'username': 'dmitry_sokolov',
                'password': 'dmitry123456',
                'category': 'Юрист'
            },
            {
                'first_name': 'Мария',
                'last_name': 'Козлова',
                'middle_name': 'Сергеевна',
                'email': 'maria.kozlova@example.com',
                'phone': '+79001234569',
                'telegram_nickname': '@maria_kozlova',
                'username': 'maria_kozlova',
                'password': 'maria123456',
                'category': 'Бухгалтер'
            },
            {
                'first_name': 'Игорь',
                'last_name': 'Волков',
                'middle_name': 'Александрович',
                'email': 'igor.volkov@example.com',
                'phone': '+79001234570',
                'telegram_nickname': '@igor_volkov',
                'username': 'igor_volkov',
                'password': 'igor123456',
                'category': 'Психолог'
            },
            {
                'first_name': 'Елена',
                'last_name': 'Морозова',
                'middle_name': 'Дмитриевна',
                'email': 'elena.morozova@example.com',
                'phone': '+79001234571',
                'telegram_nickname': '@elena_morozova',
                'username': 'elena_morozova',
                'password': 'elena123456',
                'category': 'Юрист'
            }
        ]

        # Создаем или получаем категории
        categories = {}
        for cat_name in ['Психолог', 'Юрист', 'Бухгалтер', 'Врач', 'Тренер']:
            category = Category.objects.filter(name_category=cat_name).first()
            if not category:
                category = Category.objects.create(name_category=cat_name)
                self.stdout.write(self.style.SUCCESS(f'Создана категория: {cat_name}'))
            categories[cat_name] = category

        # Имена клиентов для записей
        client_names = [
            'Иван Иванов', 'Петр Петров', 'Сергей Сергеев', 'Александр Александров',
            'Елена Еленова', 'Ольга Ольгова', 'Татьяна Татьянова', 'Наталья Натальева',
            'Михаил Михайлов', 'Андрей Андреев', 'Владимир Владимиров', 'Дмитрий Дмитриев'
        ]

        credentials = []
        
        # Создаем консультантов
        for consultant_data in consultants_data:
            # Создаем или получаем пользователя
            user, user_created = User.objects.get_or_create(
                username=consultant_data['username'],
                defaults={
                    'email': consultant_data['email'],
                    'first_name': consultant_data['first_name'],
                    'last_name': consultant_data['last_name'],
                }
            )
            
            if user_created:
                user.set_password(consultant_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Создан пользователь: {consultant_data["username"]}'))
            else:
                # Если пользователь существует, обновляем пароль
                user.set_password(consultant_data['password'])
                user.save()

            # Создаем консультанта
            consultant, consultant_created = Consultant.objects.get_or_create(
                email=consultant_data['email'],
                defaults={
                    'first_name': consultant_data['first_name'],
                    'last_name': consultant_data['last_name'],
                    'middle_name': consultant_data['middle_name'],
                    'phone': consultant_data['phone'],
                    'telegram_nickname': consultant_data['telegram_nickname'],
                    'category_of_specialist': categories[consultant_data['category']],
                    'user': user
                }
            )
            
            if not consultant_created:
                consultant.user = user
                consultant.save()

            credentials.append({
                'username': consultant_data['username'],
                'password': consultant_data['password'],
                'email': consultant_data['email'],
                'full_name': f"{consultant_data['first_name']} {consultant_data['last_name']}",
                'category': consultant_data['category']
            })

            # Создаем календари (2-3 календаря на консультанта)
            calendar_names = ['Основной календарь', 'Второй календарь', 'Дополнительный']
            num_calendars = random.randint(1, 3)
            
            for i in range(num_calendars):
                calendar, created = Calendar.objects.get_or_create(
                    consultant=consultant,
                    name=calendar_names[i] if i < len(calendar_names) else f'Календарь {i+1}',
                    defaults={
                        'color': random.choice(['#667eea', '#764ba2', '#f093fb', '#4facfe', '#00f2fe']),
                        'is_active': True
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  Создан календарь: {calendar.name}'))

                # Создаем услуги (2-4 услуги на календарь)
                services_data = [
                    {
                        'name': 'Консультация',
                        'description': 'Первичная консультация',
                        'duration_minutes': 60,
                        'price': 2000.00
                    },
                    {
                        'name': 'Расширенная консультация',
                        'description': 'Подробная консультация',
                        'duration_minutes': 90,
                        'price': 3000.00
                    },
                    {
                        'name': 'Короткая консультация',
                        'description': 'Быстрая консультация',
                        'duration_minutes': 30,
                        'price': 1000.00
                    },
                    {
                        'name': 'Повторная консультация',
                        'description': 'Последующая встреча',
                        'duration_minutes': 45,
                        'price': 1500.00
                    }
                ]
                
                num_services = random.randint(2, 4)
                services = []
                
                for service_data in services_data[:num_services]:
                    service, created = Service.objects.get_or_create(
                        consultant=consultant,
                        calendar=calendar,
                        name=service_data['name'],
                        defaults={
                            'description': service_data['description'],
                            'duration_minutes': service_data['duration_minutes'],
                            'price': service_data['price'],
                            'is_active': True
                        }
                    )
                    services.append(service)
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'    Создана услуга: {service.name}'))

                # Создаем временные окна (для нескольких дней недели)
                days_with_slots = random.sample([0, 1, 2, 3, 4], k=random.randint(3, 5))
                
                for day in days_with_slots:
                    # Создаем 2-3 окна на день
                    num_slots = random.randint(2, 3)
                    for slot_num in range(num_slots):
                        start_hour = random.randint(9, 14)
                        start_minute = random.choice([0, 30])
                        end_hour = start_hour + random.randint(1, 3)
                        end_minute = random.choice([0, 30])
                        
                        if end_hour >= 18:
                            end_hour = 18
                            end_minute = 0
                        
                        start_time = time(start_hour, start_minute)
                        end_time = time(end_hour, end_minute)
                        
                        # Проверяем, что end_time > start_time
                        if datetime.combine(datetime.today(), end_time) <= datetime.combine(datetime.today(), start_time):
                            end_time = time(start_hour + 2, start_minute)
                        
                        time_slot, created = TimeSlot.objects.get_or_create(
                            calendar=calendar,
                            day_of_week=day,
                            start_time=start_time,
                            end_time=end_time,
                            defaults={
                                'is_available': True
                            }
                        )
                        if created:
                            self.stdout.write(self.style.SUCCESS(
                                f'      Создано окно: {time_slot.get_day_of_week_display()} {start_time} - {end_time}'
                            ))

                # Создаем записи (5-10 записей на календарь)
                num_bookings = random.randint(5, 10)
                time_slots = TimeSlot.objects.filter(calendar=calendar)
                
                if not time_slots.exists() or not services:
                    continue
                
                for booking_num in range(num_bookings):
                    # Случайная дата в прошлом или будущем (в пределах месяца)
                    days_offset = random.randint(-15, 15)
                    booking_date = timezone.now().date() + timedelta(days=days_offset)
                    day_of_week = booking_date.weekday()
                    
                    # Берем слоты для этого дня недели
                    available_slots = time_slots.filter(day_of_week=day_of_week)
                    if not available_slots.exists():
                        continue
                    
                    time_slot = random.choice(list(available_slots))
                    
                    # Выбираем случайную услугу
                    service = random.choice(services)
                    
                    # Проверяем, что услуга помещается в окно
                    slot_start = datetime.combine(booking_date, time_slot.start_time)
                    slot_end = datetime.combine(booking_date, time_slot.end_time)
                    slot_duration = (slot_end - slot_start).total_seconds() / 60
                    
                    if service.duration_minutes > slot_duration:
                        continue
                    
                    # Генерируем случайное время начала в рамках окна
                    max_start = slot_end - timedelta(minutes=service.duration_minutes)
                    if max_start <= slot_start:
                        continue
                    
                    # Округляем до 15 минут
                    time_delta = max_start - slot_start
                    minutes = int(time_delta.total_seconds() / 60)
                    random_minutes = random.randint(0, minutes // 15) * 15
                    booking_start = slot_start + timedelta(minutes=random_minutes)
                    booking_end = booking_start + timedelta(minutes=service.duration_minutes)
                    
                    # Проверяем пересечения с существующими записями
                    existing_bookings = Booking.objects.filter(
                        calendar=calendar,
                        booking_date=booking_date,
                        status__in=['pending', 'confirmed']
                    )
                    
                    overlaps = False
                    for existing in existing_bookings:
                        existing_start = datetime.combine(booking_date, existing.booking_time)
                        existing_end = datetime.combine(booking_date, existing.booking_end_time or existing.booking_time)
                        if not (booking_end <= existing_start or booking_start >= existing_end):
                            overlaps = True
                            break
                    
                    if overlaps:
                        continue
                    
                    # Создаем запись
                    client_name = random.choice(client_names)
                    status = random.choice(['pending', 'confirmed', 'completed', 'cancelled'])
                    
                    booking = Booking.objects.create(
                        service=service,
                        time_slot=time_slot,
                        calendar=calendar,
                        client_name=client_name,
                        client_phone=f'+7900{random.randint(1000000, 9999999)}',
                        client_email=f'client{random.randint(1, 1000)}@example.com',
                        booking_date=booking_date,
                        booking_time=booking_start.time(),
                        booking_end_time=booking_end.time(),
                        status=status,
                        notes=random.choice(['', '', '', 'Важная запись', 'Повторный клиент', None])
                    )
                    
                    if booking_num < 3:  # Выводим только первые 3 для краткости
                        self.stdout.write(self.style.SUCCESS(
                            f'        Создана запись: {client_name} на {booking_date} {booking_start.time()}'
                        ))

        # Сохраняем логины и пароли в файл (в корне проекта)
        from django.conf import settings
        credentials_file = os.path.join(settings.BASE_DIR, '..', 'consultant_credentials.txt')
        credentials_file = os.path.normpath(credentials_file)
        
        with open(credentials_file, 'w', encoding='utf-8') as f:
            f.write('=' * 60 + '\n')
            f.write('ЛОГИНЫ И ПАРОЛИ КОНСУЛЬТАНТОВ\n')
            f.write('=' * 60 + '\n\n')
            
            for cred in credentials:
                f.write(f'Консультант: {cred["full_name"]}\n')
                f.write(f'Категория: {cred["category"]}\n')
                f.write(f'Email: {cred["email"]}\n')
                f.write(f'Логин: {cred["username"]}\n')
                f.write(f'Пароль: {cred["password"]}\n')
                f.write('-' * 60 + '\n\n')
            
            f.write('\n')
            f.write('=' * 60 + '\n')
            f.write('КРАТКАЯ ТАБЛИЦА\n')
            f.write('=' * 60 + '\n\n')
            f.write(f'{"Логин":<20} {"Пароль":<15} {"Имя":<30}\n')
            f.write('-' * 65 + '\n')
            for cred in credentials:
                f.write(f'{cred["username"]:<20} {cred["password"]:<15} {cred["full_name"]:<30}\n')

        self.stdout.write(self.style.SUCCESS(f'\n[OK] Данные успешно созданы!'))
        self.stdout.write(self.style.SUCCESS(f'[OK] Логины и пароли сохранены в файл: {credentials_file}'))
        self.stdout.write(self.style.SUCCESS(f'\nСоздано консультантов: {len(credentials)}'))
        
        # Выводим статистику
        total_calendars = Calendar.objects.count()
        total_services = Service.objects.count()
        total_time_slots = TimeSlot.objects.count()
        total_bookings = Booking.objects.count()
        
        self.stdout.write(self.style.SUCCESS(f'Всего календарей: {total_calendars}'))
        self.stdout.write(self.style.SUCCESS(f'Всего услуг: {total_services}'))
        self.stdout.write(self.style.SUCCESS(f'Всего временных окон: {total_time_slots}'))
        self.stdout.write(self.style.SUCCESS(f'Всего записей: {total_bookings}'))
