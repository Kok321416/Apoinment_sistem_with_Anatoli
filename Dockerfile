FROM python:3.10-slim

WORKDIR /app

# Копирование requirements (из корня проекта)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование всего проекта
COPY . .

# Переходим в директорию Django проекта
WORKDIR /app/appoinment_sistem

# Создание директории для статики
RUN mkdir -p /app/appoinment_sistem/staticfiles

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "appoinment_sistem.wsgi:application"]
