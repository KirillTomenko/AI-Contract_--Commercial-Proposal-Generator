"""
Pydantic v2 schemas — входные/выходные модели API и внутренних сервисов.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    """Поддерживаемые типы документов."""
    COMMERCIAL_PROPOSAL = "commercial_proposal"   # Коммерческое предложение
    CLIENT_REPORT       = "client_report"          # Клиентский отчёт
    PRODUCT_CARD        = "product_card"           # Карточка товара


class DocumentStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"


# ---------------------------------------------------------------------------
# API — запрос / ответ
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """Тело POST /api/v1/generate."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=10_000,
        description="Произвольный текст, из которого нужно извлечь данные и создать документ",
        examples=[
            "Компания ООО Ромашка просит подготовить коммерческое предложение "
            "на поставку 10 ноутбуков стоимостью 70 000 рублей каждый."
        ],
    )
    document_type: DocumentType = Field(
        DocumentType.COMMERCIAL_PROPOSAL,
        description="Тип генерируемого документа",
    )

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class GenerateResponse(BaseModel):
    """Ответ на запрос генерации."""
    document_id: str
    status: DocumentStatus
    pdf_path: Optional[str] = None
    download_url: Optional[str] = None
    extracted_data: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = "Документ успешно создан"


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None


# ---------------------------------------------------------------------------
# Внутренние модели — извлечённые данные
# ---------------------------------------------------------------------------

class CommercialProposalData(BaseModel):
    """Структура данных для коммерческого предложения."""
    company_name:    Optional[str]   = Field(None, description="Название компании-заказчика")
    product:         Optional[str]   = Field(None, description="Наименование товара или услуги")
    quantity:        Optional[int]   = Field(None, description="Количество единиц")
    unit_price:      Optional[float] = Field(None, description="Цена за единицу, руб.")
    total_price:     Optional[float] = Field(None, description="Итоговая сумма, руб.")
    delivery_terms:  Optional[str]   = Field(None, description="Условия поставки")
    payment_terms:   Optional[str]   = Field(None, description="Условия оплаты")
    contact_person:  Optional[str]   = Field(None, description="Контактное лицо")
    notes:           Optional[str]   = Field(None, description="Дополнительные пожелания")


class ClientReportData(BaseModel):
    """Структура данных для клиентского отчёта."""
    client_name:  Optional[str] = Field(None, description="Имя клиента")
    topic:        Optional[str] = Field(None, description="Тема встречи/разговора")
    main_request: Optional[str] = Field(None, description="Основной запрос клиента")
    mood:         Optional[str] = Field(None, description="Настроение клиента")
    budget:       Optional[str] = Field(None, description="Бюджет")
    deadline:     Optional[str] = Field(None, description="Желаемые сроки")
    requirements: Optional[str] = Field(None, description="Основные требования к продукту")
    next_steps:   Optional[str] = Field(None, description="Рекомендуемые следующие шаги")


class ProductCardData(BaseModel):
    """Структура данных для карточки товара."""
    product_name: Optional[str]   = Field(None, description="Название товара")
    price:        Optional[float] = Field(None, description="Цена, руб.")
    description:  Optional[str]   = Field(None, description="Описание товара")
    category:     Optional[str]   = Field(None, description="Категория")
    sku:          Optional[str]   = Field(None, description="Артикул")
    features:     Optional[list[str]] = Field(None, description="Ключевые характеристики")