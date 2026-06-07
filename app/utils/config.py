"""
Конфигурация приложения через pydantic-settings.
Все переменные загружаются из .env-файла.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # OpenAI / ProxyAPI
    # ------------------------------------------------------------------
    proxyapi_api_key:  str = "your-api-key-here"
    proxyapi_base_url: str = "https://api.proxyapi.ru/openai/v1"
    openai_model:      str = "gpt-4o-mini"

    # ------------------------------------------------------------------
    # Telegram (опционально)
    # ------------------------------------------------------------------
    telegram_bot_token: str  = ""
    telegram_proxy:     str  = "socks5://127.0.0.1:1080"   # Karing SOCKS5
    telegram_enabled:   bool = False

    # ------------------------------------------------------------------
    # Приложение
    # ------------------------------------------------------------------
    app_name:    str = "AI Document Generator"
    app_version: str = "1.0.0"
    debug:       bool = False
    host:        str  = "0.0.0.0"
    port:        int  = 8000

    # ------------------------------------------------------------------
    # База данных и файлы
    # ------------------------------------------------------------------
    database_url: str = "sqlite:///./data/documents.db"
    reports_dir:  str = "./reports"
    max_text_len: int = 10_000

    # ------------------------------------------------------------------
    # Генерация изображений (опционально)
    # ------------------------------------------------------------------
    image_generation_enabled: bool = False
    # Бэкенд: "openai" | "gigachat" | "yandex"
    image_backend: str = "openai"
    # Модель генерации изображений — gpt-image-1 поддерживается ProxyAPI
    image_model:   str = "gpt-image-1"

    # GigaChat — https://developers.sber.ru/studio/
    # Credentials = base64(client_id:client_secret) из личного кабинета Sber
    gigachat_credentials: str = ""
    gigachat_scope:       str = "GIGACHAT_API_PERS"   # PERS | B2B | CORP
    # Примечание: GigaChat использует российский сертификат МЦД.
    # В dev-режиме verify_ssl_certs=False. В проде передай ca_bundle_file.

    # YandexART — https://yandex.cloud/ru/docs/foundation-models/
    yandex_api_key:   str = ""
    yandex_folder_id: str = ""


# Глобальный синглтон
settings = Settings()