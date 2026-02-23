# Dockerfile.base

# Етап 1: Встановлення всіх системних залежностей та інструментів
FROM python:3.11-slim AS base-deps

# Встановлення системних залежностей
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    libgl1 \
    libsm6 \
    libxext6 --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Встановлення робочої директорії
WORKDIR /usr/src/app

# Етап 2: Встановлення "важких" Python-залежностей
# Для цього етапу потрібно мати "requirements.base.txt"
COPY requirements.base.txt .

# 2. Встановлення PyTorch (ОБОВ'ЯЗКОВО ДЛЯ CPU-ONLY)
# Використовуйте '--extra-index-url' для вказівки CPU-версії.
# Важливо: Ultralytics вимагає PyTorch 2.9.1, тому ставимо його:
RUN pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
# Встановлення залежностей (це найдовший крок)
RUN pip install --no-cache-dir -r requirements.base.txt

# 3. Копіювання ONNX моделі
# Цей шар не буде перезбиратися, поки модель не зміниться.
COPY yolov8n.pt .
# Збереження цього шару. Звідси починатиметься ваш основний Dockerfile