"""
AIProcessorService — взаимодействие с OpenAI через ProxyAPI.
Извлекает структурированные данные из произвольного текста.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.models.schemas import (
    DocumentType,
    CommercialProposalData,
    ClientReportData,
    ProductCardData,
)
from app.prompts.extraction_prompts import (
    COMMERCIAL_PROPOSAL_SYSTEM, COMMERCIAL_PROPOSAL_USER,
    CLIENT_REPORT_SYSTEM,       CLIENT_REPORT_USER,
    PRODUCT_CARD_SYSTEM,        PRODUCT_CARD_USER,
)
from app.utils.config import settings

logger = logging.getLogger(__name__)

# Маппинг: тип документа → (system_prompt, user_template, pydantic_model)
_PROMPT_MAP: dict[DocumentType, tuple[str, str, Any]] = {
    DocumentType.COMMERCIAL_PROPOSAL: (
        COMMERCIAL_PROPOSAL_SYSTEM,
        COMMERCIAL_PROPOSAL_USER,
        CommercialProposalData,
    ),
    DocumentType.CLIENT_REPORT: (
        CLIENT_REPORT_SYSTEM,
        CLIENT_REPORT_USER,
        ClientReportData,
    ),
    DocumentType.PRODUCT_CARD: (
        PRODUCT_CARD_SYSTEM,
        PRODUCT_CARD_USER,
        ProductCardData,
    ),
}


class AIProcessorService:
    """Сервис извлечения структурированных данных через LLM."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.proxyapi_api_key,
            base_url=settings.proxyapi_base_url,
            http_client=httpx.AsyncClient(timeout=60.0),
        )

    async def extract(
        self,
        text: str,
        document_type: DocumentType,
    ) -> CommercialProposalData | ClientReportData | ProductCardData:
        """
        Отправляет текст в LLM и возвращает валидированную Pydantic-модель.

        Args:
            text: Исходный неструктурированный текст.
            document_type: Тип документа для выбора промпта и схемы.

        Returns:
            Pydantic-модель с извлечёнными данными.

        Raises:
            ValueError: Если ответ LLM не удаётся распарсить.
        """
        system_prompt, user_template, schema_cls = _PROMPT_MAP[document_type]
        user_message = user_template.format(text=text)

        logger.info(
            "Отправка запроса к LLM | тип=%s | модель=%s | текст=%d символов",
            document_type,
            settings.openai_model,
            len(text),
        )

        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.1,   # минимальная случайность для предсказуемого JSON
            max_tokens=1024,
        )

        raw = response.choices[0].message.content or ""
        logger.debug("Сырой ответ LLM: %s", raw[:500])

        extracted = self._parse_json(raw)
        logger.info("Данные извлечены успешно: %s", list(extracted.keys()))

        return schema_cls(**extracted)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """
        Парсит JSON из ответа LLM.
        Устойчив к markdown-обёртке (```json ... ```).
        """
        text = raw.strip()

        # Убираем возможные markdown-блоки
        if text.startswith("```"):
            lines = text.splitlines()
            # Первая строка — ```json или ```, последняя — ```
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Не удалось распарсить JSON: %s\nСырой текст: %s", exc, raw[:300])
            raise ValueError(f"LLM вернул невалидный JSON: {exc}") from exc
