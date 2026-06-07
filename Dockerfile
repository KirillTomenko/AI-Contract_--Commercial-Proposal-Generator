# ============================================================
# AI Document Generator — Dockerfile
# Multi-stage build: меньший итоговый образ
# ============================================================

FROM python:3.11-slim AS base

# Системные зависимости для ReportLab
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ------ Установка зависимостей --------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------ Копирование кода --------------------------------------
COPY . .

# ------ Директории -------------------------------------------
RUN mkdir -p reports data

# ------ Порт -------------------------------------------------
EXPOSE 8000

# ------ Запуск -----------------------------------------------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
