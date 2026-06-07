"""
PDFGeneratorService — формирование PDF-документов через ReportLab.
Поддерживает три типа: коммерческое предложение, клиентский отчёт, карточка товара.

Кириллица: регистрируем TTF-шрифты с поддержкой Unicode.
Приоритет поиска шрифтов:
  1. DejaVu (кросс-платформенный, кладём в app/fonts/)
  2. Arial из Windows (C:/Windows/Fonts/)
  3. Liberation Sans из Linux (/usr/share/fonts/)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Union

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.schemas import (
    ClientReportData,
    CommercialProposalData,
    DocumentType,
    ProductCardData,
)
from app.utils.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Цветовая палитра
# ---------------------------------------------------------------------------
PRIMARY   = colors.HexColor("#1a1a2e")
HIGHLIGHT = colors.HexColor("#0f3460")
LIGHT_BG  = colors.HexColor("#f8f9fa")
WHITE     = colors.white
GRAY      = colors.HexColor("#6c757d")
DIVIDER   = colors.HexColor("#dee2e6")

ExtractedData = Union[CommercialProposalData, ClientReportData, ProductCardData]


# ---------------------------------------------------------------------------
# Регистрация TTF-шрифтов с поддержкой кириллицы
# ---------------------------------------------------------------------------

def _register_fonts() -> tuple[str, str]:
    """
    Регистрирует TTF-шрифты и возвращает (regular_name, bold_name).

    Порядок поиска:
      1. DejaVu в app/fonts/ — кросс-платформенный, рекомендуемый
      2. Arial в Windows Fonts
      3. Liberation Sans в Linux
    """
    # --- Кандидаты (regular, bold) ---
    candidates = [
        # DejaVu — кладём в app/fonts/ для Docker/Linux
        (
            Path(__file__).parent.parent / "fonts" / "DejaVuSans.ttf",
            Path(__file__).parent.parent / "fonts" / "DejaVuSans-Bold.ttf",
            "DejaVuSans", "DejaVuSans-Bold",
        ),
        # Arial — Windows
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            "Arial", "Arial-Bold",
        ),
        # Calibri — Windows альтернатива
        (
            Path("C:/Windows/Fonts/calibri.ttf"),
            Path("C:/Windows/Fonts/calibrib.ttf"),
            "Calibri", "Calibri-Bold",
        ),
        # Liberation Sans — Linux
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            "LiberationSans", "LiberationSans-Bold",
        ),
    ]

    for reg_path, bold_path, reg_name, bold_name in candidates:
        if reg_path.exists() and bold_path.exists():
            try:
                pdfmetrics.registerFont(TTFont(reg_name,  str(reg_path)))
                pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
                logger.info("Шрифт зарегистрирован: %s / %s", reg_name, bold_name)
                return reg_name, bold_name
            except Exception as exc:
                logger.warning("Не удалось зарегистрировать %s: %s", reg_name, exc)

    # Fallback — Helvetica (без кириллицы, но не упадёт)
    logger.warning(
        "TTF-шрифт с кириллицей не найден! "
        "Положи DejaVuSans.ttf и DejaVuSans-Bold.ttf в app/fonts/ "
        "или установи шрифты Liberation: "
        "apt-get install fonts-liberation"
    )
    return "Helvetica", "Helvetica-Bold"


# Регистрируем шрифты при импорте модуля
FONT_REGULAR, FONT_BOLD = _register_fonts()


# ---------------------------------------------------------------------------
# PDF Generator
# ---------------------------------------------------------------------------

class PDFGeneratorService:
    """Генерирует PDF-документы из структурированных данных."""

    def __init__(self) -> None:
        self.reports_dir = Path(settings.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._styles = self._build_styles()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        data: ExtractedData,
        document_type: DocumentType,
        document_id: str,
        image_path: Path | None = None,
    ) -> Path:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M")
        filename  = f"report_{timestamp}_{document_id[:8]}.pdf"
        filepath  = self.reports_dir / filename

        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        if document_type == DocumentType.COMMERCIAL_PROPOSAL:
            story = self._build_commercial_proposal(data)        # type: ignore
        elif document_type == DocumentType.CLIENT_REPORT:
            story = self._build_client_report(data)              # type: ignore
        else:
            story = self._build_product_card(data, image_path)   # type: ignore

        doc.build(story)
        logger.info("PDF сохранён: %s", filepath)
        return filepath

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_commercial_proposal(self, data: CommercialProposalData) -> list:
        s = self._styles
        story: list = []

        story += self._header("КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ")
        story.append(Spacer(1, 6 * mm))

        rows = [
            ("Компания-заказчик",  data.company_name    or "—"),
            ("Товар / услуга",     data.product         or "—"),
            ("Количество",         str(data.quantity)   if data.quantity   else "—"),
            ("Цена за единицу",    self._fmt_money(data.unit_price)),
            ("Итоговая сумма",     self._fmt_money(data.total_price)),
            ("Условия поставки",   data.delivery_terms  or "—"),
            ("Условия оплаты",     data.payment_terms   or "—"),
            ("Контактное лицо",    data.contact_person  or "—"),
        ]
        story.append(self._data_table(rows))

        if data.notes:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph("Примечания", s["section_title"]))
            story.append(Paragraph(data.notes, s["body"]))

        story += self._footer()
        return story

    def _build_client_report(self, data: ClientReportData) -> list:
        s = self._styles
        story: list = []

        story += self._header("КЛИЕНТСКИЙ ОТЧЁТ")
        story.append(Spacer(1, 6 * mm))

        rows = [
            ("Клиент",             data.client_name  or "—"),
            ("Тема встречи",       data.topic        or "—"),
            ("Основной запрос",    data.main_request or "—"),
            ("Настроение клиента", data.mood         or "—"),
            ("Бюджет",             data.budget       or "—"),
            ("Желаемые сроки",     data.deadline     or "—"),
        ]
        story.append(self._data_table(rows))

        if data.requirements:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph("Требования к продукту", s["section_title"]))
            story.append(Paragraph(data.requirements, s["body"]))

        if data.next_steps:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("Следующие шаги", s["section_title"]))
            for step in data.next_steps.split(";"):
                step = step.strip()
                if step:
                    story.append(Paragraph(f"• {step}", s["body"]))

        story += self._footer()
        return story

    def _build_product_card(
        self,
        data: ProductCardData,
        image_path: Path | None = None,
    ) -> list:
        s = self._styles
        story: list = []

        story += self._header("КАРТОЧКА ТОВАРА")
        story.append(Spacer(1, 6 * mm))

        story.append(Paragraph(data.product_name, s["product_name"]))
        story.append(Paragraph(self._fmt_money(data.price), s["product_price"]))
        story.append(Spacer(1, 4 * mm))

        rows = [
            ("Категория", data.category or "—"),
            ("Артикул",   data.sku      or "—"),
        ]
        story.append(self._data_table(rows))

        if image_path and image_path.exists():
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph("Изображение товара", s["section_title"]))
            story.append(Spacer(1, 2 * mm))
            img = Image(str(image_path), width=170 * mm, height=100 * mm)
            img.hAlign = "LEFT"
            story.append(img)

        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("Описание", s["section_title"]))
        story.append(Paragraph(data.description, s["body"]))

        if data.features:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("Характеристики", s["section_title"]))
            for feat in data.features:
                story.append(Paragraph(f"• {feat}", s["body"]))

        story += self._footer()
        return story

    # ------------------------------------------------------------------
    # UI components
    # ------------------------------------------------------------------

    def _header(self, title: str) -> list:
        s = self._styles
        date_str = datetime.utcnow().strftime("%d.%m.%Y")

        header_data = [[
            Paragraph("AI DOC GEN", s["logo"]),
            Paragraph(f"Дата: {date_str}", s["date"]),
        ]]
        header_table = Table(header_data, colWidths=["70%", "30%"])
        header_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), PRIMARY),
            ("TEXTCOLOR",     (0, 0), (-1, -1), WHITE),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (0, -1),  12),
            ("RIGHTPADDING",  (1, 0), (1, -1),  12),
        ]))

        return [
            header_table,
            Spacer(1, 4 * mm),
            Paragraph(title, s["doc_title"]),
            HRFlowable(width="100%", thickness=2, color=HIGHLIGHT),
        ]

    def _data_table(self, rows: list[tuple[str, str]]) -> Table:
        table_data = [
            [Paragraph(k, self._styles["field_key"]),
             Paragraph(v, self._styles["field_val"])]
            for k, v in rows
        ]
        t = Table(table_data, colWidths=["35%", "65%"])
        t.setStyle(TableStyle([
            *[("BACKGROUND", (0, i), (-1, i), LIGHT_BG if i % 2 == 0 else WHITE)
              for i in range(len(rows))],
            ("GRID",          (0, 0), (-1, -1), 0.5, DIVIDER),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        return t

    def _footer(self) -> list:
        return [
            Spacer(1, 8 * mm),
            HRFlowable(width="100%", thickness=0.5, color=DIVIDER),
            Spacer(1, 2 * mm),
            Paragraph(
                "Сгенерировано автоматически системой AI Document Generator",
                self._styles["footer"],
            ),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_money(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value:,.2f} руб.".replace(",", " ")

    @staticmethod
    def _build_styles() -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        R = FONT_REGULAR
        B = FONT_BOLD
        return {
            "logo": ParagraphStyle(
                "logo", parent=base["Normal"],
                fontName=B, fontSize=16, textColor=WHITE, leading=20,
            ),
            "date": ParagraphStyle(
                "date", parent=base["Normal"],
                fontName=R, fontSize=9, textColor=WHITE, alignment=TA_RIGHT,
            ),
            "doc_title": ParagraphStyle(
                "doc_title", parent=base["Normal"],
                fontName=B, fontSize=18, textColor=PRIMARY,
                spaceAfter=4, alignment=TA_LEFT,
            ),
            "section_title": ParagraphStyle(
                "section_title", parent=base["Normal"],
                fontName=B, fontSize=12, textColor=HIGHLIGHT,
                spaceBefore=6, spaceAfter=3,
            ),
            "field_key": ParagraphStyle(
                "field_key", parent=base["Normal"],
                fontName=B, fontSize=9, textColor=PRIMARY,
            ),
            "field_val": ParagraphStyle(
                "field_val", parent=base["Normal"],
                fontName=R, fontSize=9, textColor=colors.black,
            ),
            "body": ParagraphStyle(
                "body", parent=base["Normal"],
                fontName=R, fontSize=10, textColor=colors.black, leading=14,
            ),
            "product_name": ParagraphStyle(
                "product_name", parent=base["Normal"],
                fontName=B, fontSize=22, textColor=PRIMARY, spaceAfter=2,
            ),
            "product_price": ParagraphStyle(
                "product_price", parent=base["Normal"],
                fontName=B, fontSize=18, textColor=HIGHLIGHT,
            ),
            "footer": ParagraphStyle(
                "footer", parent=base["Normal"],
                fontName=R, fontSize=8, textColor=GRAY, alignment=TA_CENTER,
            ),
        }