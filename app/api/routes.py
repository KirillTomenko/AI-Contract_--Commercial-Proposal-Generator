"""
API роутер v1 — эндпоинты генерации и получения документов.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.models.schemas import (
    DocumentType,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["documents"])


def get_document_service() -> DocumentService:
    """Dependency injection — возвращает экземпляр DocumentService."""
    return DocumentService()


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Генерация документа из текста",
    description=(
        "Принимает произвольный текст, извлекает структурированные данные "
        "с помощью LLM и возвращает ссылку на готовый PDF-файл."
    ),
)
async def generate_document(
    request: GenerateRequest,
    service: DocumentService = Depends(get_document_service),
) -> GenerateResponse:
    try:
        return await service.generate(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Неожиданная ошибка при генерации: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера. Попробуйте позже.",
        ) from exc


@router.get(
    "/documents/{document_id}",
    summary="Информация о документе",
    description="Возвращает метаданные документа по его ID.",
)
async def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict:
    doc = await service.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Документ {document_id} не найден",
        )
    return doc


@router.get(
    "/documents/{document_id}/download",
    summary="Скачать PDF",
    description="Возвращает PDF-файл для скачивания.",
)
async def download_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> FileResponse:
    doc = await service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    pdf_path = doc.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF-файл не найден на диске")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=Path(pdf_path).name,
    )


@router.get(
    "/documents",
    summary="Список документов",
    description="Возвращает последние 20 сгенерированных документов.",
)
async def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> list[dict]:
    return await service.list_documents()


@router.get(
    "/health",
    summary="Healthcheck",
    tags=["system"],
)
async def health() -> dict:
    return {"status": "ok", "service": "AI Document Generator"}
