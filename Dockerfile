FROM python:3.12-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

# Создание директории для статики
RUN mkdir -p /app/staticfiles

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "appoinment_sistem.wsgi:application"]
