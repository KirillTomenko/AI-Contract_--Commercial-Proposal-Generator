"""
DocumentRepository — CRUD-операции с SQLite через aiosqlite.
Хранит историю всех запросов и статусы генерации.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from app.models.schemas import DocumentStatus, DocumentType
from app.utils.config import settings

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Асинхронный репозиторий для хранения документов в SQLite."""

    def __init__(self) -> None:
        # sqlite:///./data/documents.db  →  ./data/documents.db
        self._db_path = settings.database_url.replace("sqlite:///", "")
        # Создаём директорию заранее, иначе aiosqlite упадёт на Windows
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        """Создаёт таблицу при первом запуске (вызывается из lifespan)."""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id           TEXT PRIMARY KEY,
                    type         TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending',
                    input_text   TEXT,
                    pdf_path     TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                )
            """)
            await conn.commit()
        logger.info("БД инициализирована: %s", self._db_path)

    async def create(
        self,
        document_id: str,
        document_type: DocumentType,
        input_text: str,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """INSERT INTO documents (id, type, status, input_text, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (document_id, document_type.value, DocumentStatus.PENDING.value,
                 input_text, now, now),
            )
            await conn.commit()

    async def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        pdf_path: str | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """UPDATE documents
                   SET status=?, pdf_path=?, updated_at=?
                   WHERE id=?""",
                (status.value, pdf_path, now, document_id),
            )
            await conn.commit()

    async def get(self, document_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM documents WHERE id=?", (document_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]