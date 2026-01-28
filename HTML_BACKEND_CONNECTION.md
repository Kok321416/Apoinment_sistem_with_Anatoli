# Связь HTML с бэкендом в Django

## Как это работает

### 1. URL → View → Template

```
Пользователь → URL (urls.py) → View (views.py) → Template (HTML) → Ответ пользователю
```

### 2. Структура файлов

```
appoinment_sistem/
├── appoinment_sistem/
│   └── urls.py              # Маршрутизация URL → View
├── consultant_menu/
│   ├── views.py             # Обработка запросов (бизнес-логика)
│   └── templates/
│       └── consultant_menu/
│           └── *.html        # HTML шаблоны
```

### 3. Пример связи

#### URLs (urls.py)
```python
path("", home_view, name="home"),           # URL "/" → функция home_view
path("calendars/", calendars_view, name="calendars"),  # URL "/calendars/" → функция calendars_view
```

#### View (views.py)
```python
def home_view(request):
    """Обрабатывает запрос и возвращает HTML"""
    return render(request, 'consultant_menu/home.html')
    # render() находит шаблон и передает ему данные
```

#### Template (home.html)
```html
{% if user.is_authenticated %}
    <h2>Добро пожаловать, {{ user.email }}!</h2>
{% endif %}
```

### 4. Передача данных из View в HTML

```python
# views.py
def calendars_view(request):
    consultant = Consultant.objects.get(user=request.user)
    calendars = Calendar.objects.filter(consultant=consultant)
    
    return render(request, 'consultant_menu/calendars.html', {
        'calendars': calendars,  # Передаем данные в шаблон
        'consultant': consultant
    })
```

```html
<!-- calendars.html -->
{% for calendar in calendars %}
    <div>{{ calendar.name }}</div>
{% endfor %}
```

### 5. Получение данных из HTML формы

```html
<!-- HTML форма -->
<form method="POST" action="{% url 'calendars' %}">
    {% csrf_token %}
    <input name="name" type="text">
    <button type="submit">Создать</button>
</form>
```

```python
# views.py
def calendars_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')  # Получаем данные из формы
        Calendar.objects.create(name=name)  # Сохраняем в БД
        return redirect('calendars')
    
    calendars = Calendar.objects.all()
    return render(request, 'consultant_menu/calendars.html', {'calendars': calendars})
```

### 6. Django Template Tags

```html
{% load static %}                    # Загрузка статических файлов
{% url 'home' %}                     # Генерация URL по имени
{% static 'css/style.css' %}         # Путь к статическому файлу
{% if user.is_authenticated %}       # Условие
{% for item in items %}              # Цикл
{{ variable }}                       # Вывод переменной
{% csrf_token %}                     # CSRF защита для форм
```

### 7. Полный цикл запроса

```
1. Пользователь открывает: http://site.com/calendars/
   ↓
2. urls.py находит маршрут: path("calendars/", calendars_view)
   ↓
3. Вызывается функция: calendars_view(request)
   ↓
4. View получает данные из БД: Calendar.objects.all()
   ↓
5. View передает данные в шаблон: render(request, 'template.html', {'data': data})
   ↓
6. Django рендерит HTML с данными
   ↓
7. Пользователь получает готовую HTML страницу
```

### 8. Основные компоненты

- **URLs** (`urls.py`) - определяют, какая функция обработает запрос
- **Views** (`views.py`) - обрабатывают запросы, работают с БД, возвращают ответ
- **Templates** (`*.html`) - HTML шаблоны с данными от View
- **Models** (`models.py`) - структура данных в БД
- **Static files** (`static/`) - CSS, JS, изображения

### 9. Пример полной связи

**URL:**
```python
path("book/<int:calendar_id>/", public_booking_view, name="public_booking")
```

**View:**
```python
def public_booking_view(request, calendar_id):
    calendar = Calendar.objects.get(id=calendar_id)
    return render(request, 'consultant_menu/public_booking.html', {
        'calendar': calendar
    })
```

**Template:**
```html
<h1>Запись на {{ calendar.name }}</h1>
```

**Результат:** При переходе на `/book/1/` отобразится страница с названием календаря.
