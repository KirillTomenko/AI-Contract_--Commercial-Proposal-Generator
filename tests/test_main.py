"""
Тесты для AI Document Generator.
Запуск: pytest tests/ -v
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.app import create_app
from app.models.schemas import DocumentType
from app.services.pdf_generator import PDFGeneratorService
from app.models.schemas import CommercialProposalData, ClientReportData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Unit: PDF Generator
# ---------------------------------------------------------------------------

class TestPDFGenerator:
    def test_generate_commercial_proposal(self, tmp_path, monkeypatch):
        """PDF генерируется без ошибок для коммерческого предложения."""
        monkeypatch.setattr(
            "app.services.pdf_generator.settings",
            type("S", (), {"reports_dir": str(tmp_path)})(),
        )
        svc = PDFGeneratorService()
        svc.reports_dir = tmp_path

        data = CommercialProposalData(
            company_name="ООО Тест",
            product="Ноутбук",
            quantity=5,
            unit_price=70_000.0,
            total_price=350_000.0,
        )
        path = svc.generate(data, DocumentType.COMMERCIAL_PROPOSAL, "test-id-123")
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.stat().st_size > 1_000   # файл не пустой

    def test_generate_client_report(self, tmp_path, monkeypatch):
        """PDF генерируется для клиентского отчёта."""
        svc = PDFGeneratorService()
        svc.reports_dir = tmp_path

        data = ClientReportData(
            client_name="Иван Петров",
            topic="Разработка лендинга",
            main_request="Лендинг для продажи курса",
            mood="позитивный",
            budget="80 000 ₽",
            deadline="2 недели",
            next_steps="Подготовить ТЗ; Согласовать дизайн",
        )
        path = svc.generate(data, DocumentType.CLIENT_REPORT, "test-id-456")
        assert path.exists()


# ---------------------------------------------------------------------------
# Unit: AI Processor JSON parsing
# ---------------------------------------------------------------------------

class TestAIProcessor:
    def test_parse_clean_json(self):
        from app.services.ai_processor import AIProcessorService
        raw = '{"company_name": "ООО Тест", "product": "Ноутбук", "quantity": 5}'
        result = AIProcessorService._parse_json(raw)
        assert result["company_name"] == "ООО Тест"

    def test_parse_markdown_wrapped_json(self):
        from app.services.ai_processor import AIProcessorService
        raw = '```json\n{"company_name": "Test"}\n```'
        result = AIProcessorService._parse_json(raw)
        assert result["company_name"] == "Test"

    def test_parse_invalid_json_raises(self):
        from app.services.ai_processor import AIProcessorService
        with pytest.raises(ValueError, match="невалидный JSON"):
            AIProcessorService._parse_json("это не JSON")


# ---------------------------------------------------------------------------
# Integration: API endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAPIRoutes:
    async def test_health(self, client):
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_generate_validation_error(self, client):
        """Слишком короткий текст должен вернуть 422."""
        r = await client.post("/api/v1/generate", json={"text": "ok"})
        assert r.status_code == 422

    async def test_document_not_found(self, client):
        r = await client.get("/api/v1/documents/nonexistent-id")
        assert r.status_code == 404

    async def test_list_documents(self, client):
        r = await client.get("/api/v1/documents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
