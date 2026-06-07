"""
FastAPI application factory.
Конфигурирует middleware, lifespan, роутеры и обработчики ошибок.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.database.repository import DocumentRepository
from app.utils.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте, очистка при остановке."""
    # Создаём директории
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)

    # Инициализируем БД
    repo = DocumentRepository()
    await repo.init_db()

    logger.info("🚀 %s v%s запущен", settings.app_name, settings.app_version)
    logger.info("📁 PDF-отчёты: %s", settings.reports_dir)
    logger.info("🗃  База данных: %s", settings.database_url)

    yield

    logger.info("🛑 Приложение остановлено")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Сервис автоматической генерации PDF-документов. "
            "Принимает произвольный текст → извлекает структуру через LLM → "
            "возвращает готовый PDF."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Раздача PDF-файлов
    reports_path = Path(settings.reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    app.mount("/reports", StaticFiles(directory=str(reports_path)), name="reports")

    # Роутеры
    app.include_router(router)

    # Глобальный обработчик ошибок
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Необработанная ошибка: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    return app
