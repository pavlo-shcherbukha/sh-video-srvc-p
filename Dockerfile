# Використовуємо оптимізований базовий образ Python
FROM python:3.11-slim

# Встановлення системних залежностей
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    libgl1 \
    libsm6 \
    libxext6 --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*
# Встановлення робочої директорії
WORKDIR /app

# Копіювання файлу залежностей
COPY requirements.txt .

RUN pip install --upgrade pip
# Встановлення Python-залежностей.
# Зверніть увагу на "opencv-python-headless"!
RUN pip install --no-cache-dir -r requirements.txt

# Копіювання коду програми
COPY . .

# Визначення змінної середовища, якщо потрібно (наприклад, для Azure)
#ENV PYTHONUNBUFFERED 1

# Визначення порту (якщо потрібно для веб-сервера)
# EXPOSE 8080

# Команда для запуску вашого додатку (наприклад, Gunicorn, Uvicorn, або просто python)
CMD ["python", "vcam_runner.py"]