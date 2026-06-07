"""
ImageGeneratorService — генерация изображений.

Поддерживаемые бэкенды (IMAGE_BACKEND в .env):
  openai   → DALL-E 3 через ProxyAPI
  gigachat → GigaChat text2image (official SDK, ai-forever/gigachat)
  yandex   → YandexART через Yandex Cloud

Алгоритм GigaChat:
  1. chat-запрос с function_call="auto" и промптом на русском
  2. Модель вызывает встроенную функцию text2image и возвращает image_id
  3. GET /files/{image_id}/content → бинарный JPG
  4. Сохраняем на диск

Алгоритм OpenAI / ProxyAPI:
  images.generate → b64_json → PNG

Алгоритм YandexART:
  POST /imageGenerationAsync → operation_id → polling → b64_json → PNG
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from enum import Enum
from pathlib import Path

import httpx

from app.utils.config import settings

logger = logging.getLogger(__name__)


class ImageBackend(str, Enum):
    OPENAI   = "openai"
    GIGACHAT = "gigachat"
    YANDEX   = "yandex"


class ImageGeneratorService:
    """Генерирует изображение по текстовому промпту и сохраняет на диск."""

    def __init__(self) -> None:
        self._images_dir = Path(settings.reports_dir) / "images"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._backend = ImageBackend(settings.image_backend)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        document_id: str,
        size: str = "1024x1024",
    ) -> Path | None:
        """
        Генерирует изображение и возвращает Path к файлу.
        При ошибке логирует и возвращает None — не ломает основной пайплайн.

        Args:
            prompt:      Промпт для генерации. Для GigaChat — на русском.
            document_id: ID документа (в имени файла).
            size:        "1024x1024" / "1792x1024" / "1024x1792" (только OpenAI).
        """
        if not settings.image_generation_enabled:
            logger.info("Генерация изображений отключена (IMAGE_GENERATION_ENABLED=false)")
            return None

        logger.info(
            "Генерация изображения | бэкенд=%s | промпт=%s…",
            self._backend, prompt[:80],
        )

        try:
            if self._backend == ImageBackend.OPENAI:
                return await self._generate_openai(prompt, document_id, size)
            elif self._backend == ImageBackend.GIGACHAT:
                return await self._generate_gigachat(prompt, document_id)
            elif self._backend == ImageBackend.YANDEX:
                return await self._generate_yandex(prompt, document_id)
            else:
                logger.warning("Неизвестный бэкенд: %s", self._backend)
                return None
        except Exception as exc:
            logger.error("Ошибка генерации изображения [%s]: %s", self._backend, exc)
            return None

    async def build_image_prompt(
        self,
        text: str,
        product_name: str | None = None,
        for_gigachat: bool = False,
    ) -> str:
        """
        GPT/LLM генерирует промпт для изображения на основе описания.

        Args:
            for_gigachat: если True — промпт на русском (GigaChat лучше понимает).
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.proxyapi_api_key,
            base_url=settings.proxyapi_base_url,
            http_client=httpx.AsyncClient(timeout=30.0),
        )

        if for_gigachat:
            system = (
                "Ты — арт-директор. На основе описания товара напиши короткий промпт "
                "для генерации изображения на русском языке (не более 150 символов). "
                "Опиши стиль, цвета, композицию. Верни ТОЛЬКО промпт, без пояснений."
            )
        else:
            system = (
                "You are a creative director. Given a product description, "
                "write a concise DALL-E image prompt in English (max 150 chars). "
                "Focus on visual style, composition, mood. Return ONLY the prompt."
            )

        user = f"Товар: {product_name or ''}\nОписание: {text[:400]}"

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=150,
            temperature=0.7,
        )
        prompt = (response.choices[0].message.content or "").strip()
        logger.info("Промпт для изображения: %s", prompt)
        return prompt

    # ------------------------------------------------------------------
    # Backend: OpenAI DALL-E 3 через ProxyAPI
    # ------------------------------------------------------------------

    async def _generate_openai(self, prompt: str, document_id: str, size: str) -> Path:
        """DALL-E 3 через ProxyAPI — ответ в b64_json → PNG."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.proxyapi_api_key,
            base_url=settings.proxyapi_base_url,
            http_client=httpx.AsyncClient(timeout=90.0),
        )

        response = await client.images.generate(
            model=settings.image_model,   # gpt-image-1
            prompt=prompt,
            n=1,
            # gpt-image-1 всегда возвращает b64_json, size не поддерживается
        )

        # gpt-image-1 → b64_json, dall-e-3 → url
        item = response.data[0]
        if item.b64_json:
            img_bytes = base64.b64decode(item.b64_json)
        elif item.url:
            async with httpx.AsyncClient(timeout=60.0) as dl:
                r = await dl.get(item.url)
                r.raise_for_status()
                img_bytes = r.content
        else:
            raise ValueError("Пустой ответ от API изображений")

        return self._save_image(img_bytes, document_id, ext="png")

    # ------------------------------------------------------------------
    # Backend: GigaChat text2image
    # ------------------------------------------------------------------

    async def _generate_gigachat(self, prompt: str, document_id: str) -> Path:
        """
        GigaChat image generation через официальный Python SDK (gigachat).

        Механизм:
          1. client.chat() с function_call="auto" — модель вызывает text2image
          2. Из ответа извлекаем image_id (тег <img src="..."/>  или поле в tool_call)
          3. client.get_image(image_id) → бинарный JPG
          4. Сохраняем на диск

        Требует в .env:
            GIGACHAT_CREDENTIALS=<base64 client_id:client_secret>
            GIGACHAT_SCOPE=GIGACHAT_API_PERS   # или B2B / CORP
            GIGACHAT_VERIFY_SSL=false           # российский сертификат МЦД
        """
        try:
            from gigachat import GigaChat  # pip install gigachat
            from gigachat.models import Chat, Messages, MessagesRole
        except ImportError as exc:
            raise ImportError(
                "Установи SDK: pip install gigachat  "
                "(https://github.com/ai-forever/gigachat)"
            ) from exc

        if not settings.gigachat_credentials:
            raise ValueError(
                "GIGACHAT_CREDENTIALS не задан в .env. "
                "Получи ключ на https://developers.sber.ru/studio/"
            )

        # verify_ssl=False — обходит российский корневой сертификат МЦД
        # В продакшн лучше передать ca_bundle_file с сертификатом Госуслуг
        with GigaChat(
            credentials=settings.gigachat_credentials,
            scope=settings.gigachat_scope,
            verify_ssl_certs=False,
        ) as client:
            logger.info("GigaChat: отправляем запрос на генерацию изображения")

            response = client.chat(
                Chat(
                    messages=[
                        Messages(
                            role=MessagesRole.USER,
                            content=f"Нарисуй: {prompt}",
                        )
                    ],
                    function_call="auto",   # разрешаем вызов text2image
                )
            )

            message = response.choices[0].message
            content = message.content or ""
            logger.debug("GigaChat raw response: %s", content[:200])

            # Извлекаем image_id из тега <img src="{image_id}"/>
            image_id = self._extract_gigachat_image_id(content)
            if not image_id:
                raise ValueError(
                    f"GigaChat не вернул изображение. Ответ модели: {content[:200]}"
                )

            logger.info("GigaChat: image_id=%s, скачиваем...", image_id)

            # Скачиваем бинарный JPG
            img_response = client.get_image(image_id)
            img_bytes = img_response.content

            if not img_bytes:
                raise ValueError("GigaChat: пустой бинарный ответ")

        return self._save_image(img_bytes, document_id, ext="jpg")

    @staticmethod
    def _extract_gigachat_image_id(content: str) -> str | None:
        """
        Извлекает image_id из HTML-тега, который возвращает GigaChat:
        <img src="{image_id}"/>  или  <img src="{image_id}" fuse="true"/>
        """
        import re
        match = re.search(r'<img\s+src="([^"]+)"', content)
        return match.group(1) if match else None

    # ------------------------------------------------------------------
    # Backend: YandexART
    # ------------------------------------------------------------------

    async def _generate_yandex(self, prompt: str, document_id: str) -> Path:
        """
        YandexART через Yandex Cloud Foundation Models API.
        Асинхронная операция: POST → operation_id → polling → b64_json.

        Требует в .env:
            YANDEX_API_KEY=<IAM-токен или API-ключ>
            YANDEX_FOLDER_ID=<folder_id>
        """
        if not settings.yandex_api_key or not settings.yandex_folder_id:
            raise ValueError(
                "YandexART требует YANDEX_API_KEY и YANDEX_FOLDER_ID в .env. "
                "Инструкция: https://yandex.cloud/ru/docs/foundation-models/image-generation/"
            )

        headers = {
            "Authorization": f"Api-Key {settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": (
                f"art://{settings.yandex_folder_id}/yandex-art/latest"
            ),
            "generationOptions": {
                "seed": 42,
                "aspectRatio": {"widthRatio": 1, "heightRatio": 1},
            },
            "messages": [{"weight": 1, "text": prompt}],
        }

        async with httpx.AsyncClient(timeout=120.0) as http:
            # 1. Создать асинхронную задачу
            resp = await http.post(
                "https://llm.api.cloud.yandex.net"
                "/foundationModels/v1/imageGenerationAsync",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            operation_id = resp.json().get("id")
            if not operation_id:
                raise ValueError(f"YandexART: нет operation_id. Ответ: {resp.text[:200]}")

            logger.info("YandexART: операция %s создана, ожидаем...", operation_id)

            # 2. Поллинг (каждые 5 сек, максимум 60 сек)
            for attempt in range(12):
                await asyncio.sleep(5)
                poll = await http.get(
                    f"https://llm.api.cloud.yandex.net/operations/{operation_id}",
                    headers=headers,
                )
                poll.raise_for_status()
                data = poll.json()

                if data.get("done"):
                    b64_data = data.get("response", {}).get("image")
                    if not b64_data:
                        raise ValueError("YandexART: нет image в ответе операции")
                    logger.info(
                        "YandexART: изображение готово (попытка %d/12)", attempt + 1
                    )
                    return self._save_image(
                        base64.b64decode(b64_data), document_id, ext="png"
                    )

                logger.debug("YandexART: ожидание... попытка %d/12", attempt + 1)

        raise TimeoutError(
            "YandexART: изображение не готово за 60 секунд. "
            "Попробуй увеличить таймаут."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_image(self, data: bytes, document_id: str, ext: str = "png") -> Path:
        """Сохраняет бинарные данные изображения на диск."""
        filename = f"img_{document_id[:8]}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = self._images_dir / filename
        filepath.write_bytes(data)
        logger.info(
            "Изображение сохранено: %s (%.1f KB)", filepath, len(data) / 1024
        )
        return filepath