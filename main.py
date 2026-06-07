"""
Точка входа — запускает FastAPI через uvicorn.

Локальный запуск:
    python main.py

Через Docker:
    docker compose up
"""

import uvicorn
from app.app import create_app
from app.utils.config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
