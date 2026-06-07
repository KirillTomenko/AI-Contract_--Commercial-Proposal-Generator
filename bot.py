"""
Telegram-бот на aiogram 3 с поддержкой SOCKS5-прокси (Karing).

Запуск:
    python bot.py

Переменные окружения:
    TELEGRAM_BOT_TOKEN — токен бота
    TELEGRAM_PROXY     — socks5://127.0.0.1:1080  (Karing)
    TELEGRAM_ENABLED   — true/false
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.client.session.aiohttp import AiohttpSession

from app.models.schemas import DocumentType, GenerateRequest
from app.services.document_service import DocumentService
from app.utils.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class GenerateFlow(StatesGroup):
    choosing_type = State()
    waiting_text  = State()


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def doc_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📄 Коммерческое предложение",
            callback_data="type:commercial_proposal",
        )],
        [InlineKeyboardButton(
            text="📋 Клиентский отчёт",
            callback_data="type:client_report",
        )],
        [InlineKeyboardButton(
            text="🛒 Карточка товара",
            callback_data="type:product_card",
        )],
    ])


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Привет! Я генерирую PDF-документы из текста.\n\n"
        "Выбери тип документа:",
        reply_markup=doc_type_keyboard(),
    )
    await state.set_state(GenerateFlow.choosing_type)


async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Как пользоваться:</b>\n\n"
        "1. Нажми /start\n"
        "2. Выбери тип документа\n"
        "3. Отправь произвольный текст\n"
        "4. Получи готовый PDF\n\n"
        "<b>Примеры текстов:</b>\n"
        "• <i>«ООО Ромашка просит коммерческое предложение на 10 ноутбуков по 70 000 ₽»</i>\n"
        "• <i>«Клиент Иван хочет лендинг за 2 недели, бюджет 50 000»</i>",
        parse_mode=ParseMode.HTML,
    )


async def on_doc_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    doc_type_str = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(doc_type=doc_type_str)
    await state.set_state(GenerateFlow.waiting_text)

    type_labels = {
        "commercial_proposal": "коммерческое предложение",
        "client_report":       "клиентский отчёт",
        "product_card":        "карточку товара",
    }
    label = type_labels.get(doc_type_str, doc_type_str)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"✅ Выбран тип: <b>{label}</b>\n\n"
        "📝 Теперь отправь текст, из которого нужно создать документ:",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


async def on_text_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    doc_type_str = data.get("doc_type", "commercial_proposal")

    await state.clear()
    processing_msg = await message.answer("⏳ Генерирую документ...")

    try:
        service = DocumentService()
        request = GenerateRequest(
            text=message.text or "",
            document_type=DocumentType(doc_type_str),
        )
        response = await service.generate(request)

        pdf_path = Path(response.pdf_path)  # type: ignore[arg-type]
        if pdf_path.exists():
            await message.answer_document(
                FSInputFile(str(pdf_path), filename=pdf_path.name),
                caption=(
                    f"✅ <b>Документ готов!</b>\n\n"
                    f"🆔 ID: <code>{response.document_id[:8]}</code>\n"
                    f"📄 Файл: {pdf_path.name}"
                ),
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer("✅ Документ создан, но файл не найден на диске.")

        await processing_msg.delete()

    except Exception as exc:
        logger.exception("Ошибка генерации в боте: %s", exc)
        await processing_msg.edit_text(
            f"❌ Ошибка при генерации документа:\n<code>{exc}</code>",
            parse_mode=ParseMode.HTML,
        )

    # После генерации — снова предлагаем выбор
    await message.answer("Хочешь создать ещё один документ?", reply_markup=doc_type_keyboard())
    await state.set_state(GenerateFlow.choosing_type)


# ---------------------------------------------------------------------------
# Bot factory
# ---------------------------------------------------------------------------

def create_bot_and_dp() -> tuple[Bot, Dispatcher]:
    """
    Создаёт Bot с SOCKS5-прокси (Karing) и Dispatcher.
    aiogram 3.20+ поддерживает proxy URL напрямую в AiohttpSession.
    """
    if settings.telegram_proxy:
        logger.info("Telegram прокси: %s", settings.telegram_proxy)
        session = AiohttpSession(proxy=settings.telegram_proxy)
    else:
        session = AiohttpSession()

    bot = Bot(
        token=settings.telegram_bot_token,
        session=session,
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация хендлеров
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.callback_query.register(on_doc_type_chosen, F.data.startswith("type:"))
    dp.message.register(on_text_received, GenerateFlow.waiting_text)

    return bot, dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env!")
        return

    bot, dp = create_bot_and_dp()
    logger.info("🤖 Telegram-бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())