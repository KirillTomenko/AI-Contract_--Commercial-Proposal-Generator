"""
DocumentService — оркестратор всего пайплайна:
  Текст → LLM → Structured Data → (Image) → PDF → DB-запись

Генерация изображения подключается автоматически для ProductCard
если IMAGE_GENERATION_ENABLED=true в .env.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.repository import DocumentRepository
from app.models.schemas import (
    DocumentStatus,
    DocumentType,
    GenerateRequest,
    GenerateResponse,
    ProductCardData,
)
from app.services.ai_processor import AIProcessorService
from app.services.image_generator import ImageGeneratorService
from app.services.pdf_generator import PDFGeneratorService
from app.utils.config import settings

logger = logging.getLogger(__name__)


class DocumentService:
    """Центральный сервис генерации документов."""

    def __init__(self) -> None:
        self._ai    = AIProcessorService()
        self._pdf   = PDFGeneratorService()
        self._img   = ImageGeneratorService()
        self._repo  = DocumentRepository()

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """
        Полный цикл генерации:
        1. Создать запись в БД (PENDING).
        2. Извлечь структуру через LLM.
        3. Для ProductCard — опционально сгенерировать изображение.
        4. Сгенерировать PDF (с изображением или без).
        5. Обновить запись (DONE).
        """
        document_id = str(uuid.uuid4())
        logger.info(
            "Начало генерации | id=%s | тип=%s", document_id, request.document_type
        )

        await self._repo.create(
            document_id=document_id,
            document_type=request.document_type,
            input_text=request.text,
        )

        try:
            # ── Шаг 1: извлечь данные из текста ──────────────────────
            extracted = await self._ai.extract(request.text, request.document_type)
            logger.info("Данные извлечены | id=%s", document_id)

            # ── Шаг 2: генерация изображения (опционально) ────────────
            image_path: Path | None = None
            if settings.image_generation_enabled:
                image_path = await self._generate_image_for(
                    extracted, request.document_type, document_id, request.text
                )

            # ── Шаг 3: создать PDF ────────────────────────────────────
            pdf_path: Path = self._pdf.generate(
                data=extracted,
                document_type=request.document_type,
                document_id=document_id,
                image_path=image_path,
            )

            # ── Шаг 4: обновить статус ────────────────────────────────
            await self._repo.update_status(
                document_id=document_id,
                status=DocumentStatus.DONE,
                pdf_path=str(pdf_path),
            )

            return GenerateResponse(
                document_id=document_id,
                status=DocumentStatus.DONE,
                pdf_path=str(pdf_path),
                download_url=f"/api/v1/documents/{document_id}/download",
                extracted_data=extracted.model_dump(),
                message="Документ успешно создан",
            )

        except Exception as exc:
            logger.exception("Ошибка генерации | id=%s | %s", document_id, exc)
            await self._repo.update_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_image_for(
        self,
        extracted: Any,
        document_type: DocumentType,
        document_id: str,
        source_text: str,
    ) -> Path | None:
        """
        Генерирует изображение для нужных типов документов.

        - ProductCard  → всегда генерируем (товар должен быть красивым)
        - ClientReport → опционально, если нужна иллюстрация
        - CommercialProposal → пропускаем (деловой документ)
        """
        if document_type == DocumentType.PRODUCT_CARD:
            product_name = getattr(extracted, "product_name", None)
            description  = getattr(extracted, "description", source_text)
            use_gigachat = settings.image_backend == "gigachat"

            prompt = await self._img.build_image_prompt(
                text=description,
                product_name=product_name,
                for_gigachat=use_gigachat,
            )
            return await self._img.generate(prompt=prompt, document_id=document_id)

        # Другие типы — без изображения
        return None

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        return await self._repo.get(document_id)

    async def list_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._repo.list_recent(limit=limit)
