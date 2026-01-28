from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Specialist, Appointment, Calendar, Service, TimeSlot


class UserRegistrationForm(UserCreationForm):
    """Форма регистрации пользователя"""
    user_type = forms.ChoiceField(
        choices=UserProfile.USER_TYPE_CHOICES,
        label='Тип пользователя',
        widget=forms.RadioSelect
    )
    telegram_username = forms.CharField(
        max_length=100,
        required=False,
        label='Telegram username',
        help_text='Необязательно'
    )
    specialization = forms.ChoiceField(
        choices=Specialist.SPECIALIZATION_CHOICES,
        required=False,
        label='Специализация',
        help_text='Только для специалистов'
    )
    email = forms.EmailField(required=True, label='Email')
    first_name = forms.CharField(max_length=30, required=True, label='Имя')
    last_name = forms.CharField(max_length=30, required=True, label='Фамилия')
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
    
    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        specialization = cleaned_data.get('specialization')
        
        if user_type == 'specialist' and not specialization:
            raise forms.ValidationError('Специалистам необходимо указать специализацию')
        
        return cleaned_data


class AppointmentForm(forms.ModelForm):
    """Форма записи на консультацию"""
    appointment_date = forms.DateTimeField(
        label='Дата и время',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=True
    )
    time_slot_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )
    
    client_telegram = forms.CharField(
        max_length=100,
        label='Telegram',
        required=True,
        help_text='Укажите ваш Telegram username (например: @username) или номер телефона'
    )
    
    class Meta:
        model = Appointment
        fields = ('client_name', 'client_email', 'client_phone', 'client_telegram', 'notes', 'appointment_date')
        labels = {
            'client_name': 'Ваше имя',
            'client_email': 'Email',
            'client_phone': 'Телефон',
            'client_telegram': 'Telegram',
            'notes': 'Дополнительная информация',
        }
    
    def __init__(self, *args, **kwargs):
        service = kwargs.pop('service', None)
        super().__init__(*args, **kwargs)
        self.service = service
        
        if service:
            # Предзаполняем длительность из услуги
            if 'duration' in self.fields:
                self.fields['duration'].initial = service.duration


class CalendarForm(forms.ModelForm):
    """Форма создания/редактирования календаря"""
    class Meta:
        model = Calendar
        fields = ('name', 'description', 'color', 'is_active')
        labels = {
            'name': 'Название календаря',
            'description': 'Описание',
            'color': 'Цвет',
            'is_active': 'Активен',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'color': forms.TextInput(attrs={'type': 'color'}),
        }


class ServiceForm(forms.ModelForm):
    """Форма создания/редактирования услуги"""
    class Meta:
        model = Service
        fields = ('calendar', 'name', 'description', 'duration', 'price', 
                  'work_hours_start', 'work_hours_end', 'buffer_time', 'is_active')
        labels = {
            'calendar': 'Календарь',
            'name': 'Название услуги',
            'description': 'Описание',
            'duration': 'Длительность (минуты)',
            'price': 'Цена',
            'work_hours_start': 'Начало рабочего дня',
            'work_hours_end': 'Конец рабочего дня',
            'buffer_time': 'Буферное время между записями (минуты)',
            'is_active': 'Активна',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'work_hours_start': forms.TimeInput(attrs={'type': 'time'}),
            'work_hours_end': forms.TimeInput(attrs={'type': 'time'}),
        }
    
    def __init__(self, *args, **kwargs):
        specialist = kwargs.pop('specialist', None)
        super().__init__(*args, **kwargs)
        
        if specialist:
            # Ограничиваем выбор календарей только календарями этого специалиста
            self.fields['calendar'].queryset = Calendar.objects.filter(
                specialist=specialist,
                is_active=True
            )


class TimeSlotForm(forms.ModelForm):
    """Форма создания временного слота"""
    class Meta:
        model = TimeSlot
        fields = ('date', 'start_time', 'end_time', 'service')
        labels = {
            'date': 'Дата',
            'start_time': 'Время начала',
            'end_time': 'Время окончания',
            'service': 'Услуга (необязательно)',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
    
    def __init__(self, *args, **kwargs):
        calendar = kwargs.pop('calendar', None)
        super().__init__(*args, **kwargs)
        
        if calendar:
            # Ограничиваем выбор услуг только услугами этого календаря
            self.fields['service'].queryset = Service.objects.filter(
                calendar=calendar,
                is_active=True
            )
            self.fields['service'].required = False
            self.fields['service'].empty_label = 'Без привязки к услуге'
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if start_time >= end_time:
                raise forms.ValidationError('Время окончания должно быть позже времени начала')
        
        return cleaned_data


