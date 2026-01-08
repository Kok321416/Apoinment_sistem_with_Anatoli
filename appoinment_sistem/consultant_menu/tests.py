"""
Тесты для системы записи консультантов
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import date, time, timedelta
import json

from consultant_menu.models import (
    Consultant, Category, Calendar, Service, TimeSlot, Booking, Clients
)


class ModelTests(TestCase):
    """Тесты моделей"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
    
    def test_category_creation(self):
        """Тест создания категории"""
        category = Category.objects.create(name_category="Юрист")
        self.assertEqual(category.name_category, "Юрист")
        self.assertIsNotNone(category.id)
    
    def test_consultant_creation(self):
        """Тест создания консультанта"""
        self.assertEqual(self.consultant.first_name, "Иван")
        self.assertEqual(self.consultant.last_name, "Иванов")
        self.assertEqual(self.consultant.email, "test@test.com")
        self.assertEqual(self.consultant.user, self.user)
    
    def test_calendar_creation(self):
        """Тест создания календаря"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Основной календарь",
            color="#667eea"
        )
        self.assertEqual(calendar.name, "Основной календарь")
        self.assertEqual(calendar.consultant, self.consultant)
        self.assertTrue(calendar.is_active)
    
    def test_time_slot_creation(self):
        """Тест создания временного окна"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        time_slot = TimeSlot.objects.create(
            calendar=calendar,
            day_of_week=0,  # Понедельник
            start_time=time(9, 0),
            end_time=time(12, 0)
        )
        self.assertEqual(time_slot.day_of_week, 0)
        self.assertEqual(time_slot.start_time, time(9, 0))
        self.assertTrue(time_slot.is_available)
    
    def test_service_creation(self):
        """Тест создания услуги"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        service = Service.objects.create(
            consultant=self.consultant,
            calendar=calendar,
            name="Консультация",
            description="Тестовая консультация",
            duration_minutes=60,
            price=2000.00
        )
        self.assertEqual(service.name, "Консультация")
        self.assertEqual(service.duration_minutes, 60)
        self.assertTrue(service.is_active)
    
    def test_booking_creation(self):
        """Тест создания записи"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        service = Service.objects.create(
            consultant=self.consultant,
            calendar=calendar,
            name="Консультация",
            duration_minutes=60
        )
        time_slot = TimeSlot.objects.create(
            calendar=calendar,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(12, 0)
        )
        booking = Booking.objects.create(
            service=service,
            time_slot=time_slot,
            calendar=calendar,
            client_name="Петр Петров",
            client_phone="+79001234567",
            client_email="client@test.com",
            booking_date=date.today() + timedelta(days=1),
            booking_time=time(10, 0),
            booking_end_time=time(11, 0),
            status='pending'
        )
        self.assertEqual(booking.client_name, "Петр Петров")
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.service, service)


class AuthenticationTests(TestCase):
    """Тесты аутентификации"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
    
    def test_register_view_get(self):
        """Тест GET запроса на страницу регистрации"""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/register.html')
    
    def test_register_view_post_success(self):
        """Тест успешной регистрации"""
        response = self.client.post(reverse('register'), {
            'email': 'newuser@test.com',
            'password': 'newpass123'
        })
        self.assertEqual(response.status_code, 302)  # Редирект после регистрации
        self.assertTrue(User.objects.filter(username='newuser@test.com').exists())
    
    def test_register_view_post_duplicate(self):
        """Тест регистрации с существующим email"""
        response = self.client.post(reverse('register'), {
            'email': 'test@test.com',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
    
    def test_login_view_get(self):
        """Тест GET запроса на страницу входа"""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/login.html')
    
    def test_login_view_post_success(self):
        """Тест успешного входа"""
        response = self.client.post(reverse('login'), {
            'email': 'test@test.com',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Редирект после входа
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_view_post_failure(self):
        """Тест входа с неверными данными"""
        response = self.client.post(reverse('login'), {
            'email': 'test@test.com',
            'password': 'wrongpass'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
    
    def test_logout_view(self):
        """Тест выхода"""
        self.client.login(username='test@test.com', password='testpass123')
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
    
    def test_api_register(self):
        """Тест API регистрации"""
        response = self.client.post('/api/auth/register/', {
            'email': 'apiuser@test.com',
            'password': 'apipass123'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username='apiuser@test.com').exists())
    
    def test_api_login(self):
        """Тест API входа"""
        response = self.client.post('/api/auth/login/', {
            'email': 'test@test.com',
            'password': 'testpass123'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['email'], 'test@test.com')


class CalendarTests(TestCase):
    """Тесты календарей"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
        self.client.login(username='test@test.com', password='testpass123')
    
    def test_calendars_view_get(self):
        """Тест GET запроса на страницу календарей"""
        response = self.client.get(reverse('calendars'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/calendars.html')
    
    def test_calendar_creation(self):
        """Тест создания календаря"""
        response = self.client.post(reverse('calendars'), {
            'action': 'create_calendar',
            'name': 'Новый календарь',
            'color': '#667eea'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Calendar.objects.filter(name='Новый календарь').exists())
    
    def test_calendar_deletion(self):
        """Тест удаления календаря"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        response = self.client.post(reverse('calendars'), {
            'action': 'delete_calendar',
            'calendar_id': calendar.id
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Calendar.objects.filter(id=calendar.id).exists())
    
    def test_calendar_detail_view(self):
        """Тест страницы деталей календаря"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        response = self.client.get(reverse('calendar_detail', args=[calendar.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/calendar_detail.html')
    
    def test_time_slot_creation(self):
        """Тест создания временного окна"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        response = self.client.post(reverse('calendar_detail', args=[calendar.id]), {
            'action': 'add_time_slot',
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '12:00'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TimeSlot.objects.filter(
            calendar=calendar,
            day_of_week=0,
            start_time=time(9, 0)
        ).exists())
    
    def test_time_slot_deletion(self):
        """Тест удаления временного окна"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        time_slot = TimeSlot.objects.create(
            calendar=calendar,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(12, 0)
        )
        response = self.client.post(reverse('calendar_detail', args=[calendar.id]), {
            'action': 'delete_time_slot',
            'slot_id': time_slot.id
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TimeSlot.objects.filter(id=time_slot.id).exists())


class ServiceTests(TestCase):
    """Тесты услуг"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
        self.client.login(username='test@test.com', password='testpass123')
    
    def test_services_view_get(self):
        """Тест GET запроса на страницу услуг"""
        response = self.client.get(reverse('services'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/services.html')
    
    def test_service_creation(self):
        """Тест создания услуги"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        response = self.client.post(reverse('services'), {
            'action': 'create_service',
            'name': 'Новая услуга',
            'description': 'Описание услуги',
            'duration_minutes': '60',
            'price': '2000'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Service.objects.filter(name='Новая услуга').exists())
    
    def test_service_deletion(self):
        """Тест удаления услуги"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        service = Service.objects.create(
            consultant=self.consultant,
            calendar=calendar,
            name="Тестовая услуга",
            duration_minutes=60
        )
        response = self.client.post(reverse('services'), {
            'action': 'delete_service',
            'service_id': service.id
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Service.objects.filter(id=service.id).exists())
    
    def test_service_toggle(self):
        """Тест переключения статуса услуги"""
        calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        service = Service.objects.create(
            consultant=self.consultant,
            calendar=calendar,
            name="Тестовая услуга",
            duration_minutes=60,
            is_active=True
        )
        response = self.client.post(reverse('services'), {
            'action': 'toggle_service',
            'service_id': service.id
        })
        self.assertEqual(response.status_code, 200)
        service.refresh_from_db()
        self.assertFalse(service.is_active)


class BookingTests(TestCase):
    """Тесты записей"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
        self.calendar = Calendar.objects.create(
            consultant=self.consultant,
            name="Тестовый календарь"
        )
        self.service = Service.objects.create(
            consultant=self.consultant,
            calendar=self.calendar,
            name="Консультация",
            duration_minutes=60
        )
        self.time_slot = TimeSlot.objects.create(
            calendar=self.calendar,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(12, 0)
        )
        self.client.login(username='test@test.com', password='testpass123')
    
    def test_public_booking_view(self):
        """Тест публичной страницы записи"""
        response = self.client.get(reverse('public_booking', args=[self.calendar.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/public_booking.html')
    
    def test_public_booking_post(self):
        """Тест создания записи через публичную страницу"""
        booking_date = date.today() + timedelta(days=1)
        response = self.client.post(reverse('public_booking', args=[self.calendar.id]), {
            'service_id': self.service.id,
            'client_name': 'Петр Петров',
            'client_phone': '+79001234567',
            'client_email': 'client@test.com',
            'booking_date': booking_date.strftime('%Y-%m-%d'),
            'booking_time': '10:00',
            'booking_end_time': '11:00'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Booking.objects.filter(client_name='Петр Петров').exists())
    
    def test_get_available_slots_api(self):
        """Тест API получения доступных слотов"""
        booking_date = date.today() + timedelta(days=1)
        response = self.client.get(
            reverse('get_available_slots', args=[self.calendar.id]),
            {
                'date': booking_date.strftime('%Y-%m-%d'),
                'service_id': self.service.id
            }
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('available_slots', data)
    
    def test_booking_view_get(self):
        """Тест GET запроса на страницу записей"""
        response = self.client.get(reverse('booking'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'consultant_menu/booking.html')
    
    def test_booking_status_change(self):
        """Тест изменения статуса записи"""
        booking = Booking.objects.create(
            service=self.service,
            time_slot=self.time_slot,
            calendar=self.calendar,
            client_name="Петр Петров",
            client_phone="+79001234567",
            booking_date=date.today() + timedelta(days=1),
            booking_time=time(10, 0),
            booking_end_time=time(11, 0),
            status='pending'
        )
        response = self.client.post(reverse('booking'), {
            'action': 'confirm',
            'booking_id': booking.id
        })
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')


class ConsultantAPITests(TestCase):
    """Тесты API консультантов"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
        self.client.login(username='test@test.com', password='testpass123')
    
    def test_consultant_list_api(self):
        """Тест получения списка консультантов"""
        response = self.client.get('/consultant/consultant_list/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('consultants', data)
    
    def test_create_client_api(self):
        """Тест создания клиента через API"""
        response = self.client.post('/consultant/consultant_list/', {
            'name': 'Новый клиент',
            'number': 123456,
            'telegram_nickname': '@newclient'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Clients.objects.filter(name='Новый клиент').exists())


class IntegrationTests(TestCase):
    """Интеграционные тесты"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = Client()
        self.category = Category.objects.create(name_category="Психолог")
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="testpass123"
        )
        self.consultant = Consultant.objects.create(
            user=self.user,
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            email="test@test.com",
            phone="+79001234567",
            telegram_nickname="@test",
            category_of_specialist=self.category
        )
    
    def test_full_booking_flow(self):
        """Тест полного потока создания записи"""
        # 1. Регистрация и вход
        self.client.post(reverse('register'), {
            'email': 'newuser@test.com',
            'password': 'newpass123'
        })
        self.client.login(username='newuser@test.com', password='newpass123')
        
        # 2. Создание календаря
        response = self.client.post(reverse('calendars'), {
            'action': 'create_calendar',
            'name': 'Мой календарь',
            'color': '#667eea'
        })
        calendar = Calendar.objects.get(name='Мой календарь')
        
        # 3. Создание временного окна
        self.client.post(reverse('calendar_detail', args=[calendar.id]), {
            'action': 'add_time_slot',
            'day_of_week': '0',
            'start_time': '09:00',
            'end_time': '12:00'
        })
        
        # 4. Создание услуги
        self.client.post(reverse('services'), {
            'action': 'create_service',
            'name': 'Консультация',
            'duration_minutes': '60',
            'price': '2000'
        })
        service = Service.objects.get(name='Консультация')
        
        # 5. Создание записи
        booking_date = date.today() + timedelta(days=1)
        time_slot = TimeSlot.objects.get(calendar=calendar)
        booking = Booking.objects.create(
            service=service,
            time_slot=time_slot,
            calendar=calendar,
            client_name="Петр Петров",
            client_phone="+79001234567",
            booking_date=booking_date,
            booking_time=time(10, 0),
            booking_end_time=time(11, 0)
        )
        
        # Проверка
        self.assertIsNotNone(booking.id)
        self.assertEqual(booking.status, 'pending')
