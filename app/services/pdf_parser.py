from __future__ import annotations

# pyright: reportMissingImports=false,reportMissingTypeStubs=false,reportUnknownMemberType=false,reportUnknownVariableType=false,reportUnknownArgumentType=false,reportUnknownParameterType=false,reportAttributeAccessIssue=false,reportMissingTypeArgument=false,reportAny=false,reportExplicitAny=false,reportArgumentType=false

import asyncio
import importlib
import io
from dataclasses import dataclass, field
from typing import Any

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

from app.core.logging_config import get_logger

try:
    pytesseract = importlib.import_module("pytesseract")
except Exception:  # pragma: no cover - optional at runtime
    pytesseract = None


@dataclass
class PageContent:
    page_number: int
    text: str
    extraction_method: str
    confidence: float | None = None


@dataclass
class TableData:
    page_number: int
    table_index: int
    headers: list[str]
    rows: list[list[str]]


@dataclass
class PdfResult:
    filename: str
    total_pages: int
    pdf_type: str
    pages: list[PageContent] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    form_fields: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class PdfParserService:
    def __init__(self, tesseract_cmd: str = "tesseract", tesseract_lang: str = "chi_tra"):
        self.logger: Any = get_logger(__name__)
        self.tesseract_cmd: str = tesseract_cmd
        self.tesseract_lang: str = tesseract_lang

        if pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    async def parse_pdf(self, pdf_data: bytes, filename: str) -> PdfResult:
        return await asyncio.to_thread(self._parse_pdf_sync, pdf_data, filename)

    def _parse_pdf_sync(self, pdf_data: bytes, filename: str) -> PdfResult:
        errors: list[str] = []

        try:
            with fitz.open(stream=pdf_data, filetype="pdf") as doc:
                total_pages = len(doc)
                metadata = self._extract_metadata(doc)
        except Exception as exc:
            msg = f"Invalid or corrupted PDF: {exc}"
            self.logger.exception(msg)
            return PdfResult(
                filename=filename,
                total_pages=0,
                pdf_type="scanned",
                metadata={},
                errors=[msg],
            )

        pdf_type = self.detect_pdf_type(pdf_data)

        pages: list[PageContent] = []
        try:
            if pdf_type == "digital":
                pages = self.extract_digital_text(pdf_data)
            elif pdf_type == "scanned":
                pages = self.ocr_scanned_pages(pdf_data)
            else:
                digital_pages = self.extract_digital_text(pdf_data)
                by_page = {p.page_number: p for p in digital_pages}
                empty_pages = [p.page_number for p in digital_pages if not p.text.strip()]
                ocr_pages = self.ocr_scanned_pages(pdf_data, pages=empty_pages)
                for page in ocr_pages:
                    by_page[page.page_number] = page
                pages = [by_page[idx] for idx in sorted(by_page)]
        except Exception as exc:
            msg = f"Failed to extract page text: {exc}"
            self.logger.exception(msg)
            errors.append(msg)

        try:
            tables = self.extract_tables(pdf_data)
        except Exception as exc:
            msg = f"Failed to extract tables: {exc}"
            self.logger.exception(msg)
            errors.append(msg)
            tables = []

        try:
            form_fields = self.extract_form_fields(pdf_data)
        except Exception as exc:
            msg = f"Failed to extract form fields: {exc}"
            self.logger.exception(msg)
            errors.append(msg)
            form_fields = {}

        return PdfResult(
            filename=filename,
            total_pages=total_pages,
            pdf_type=pdf_type,
            pages=pages,
            tables=tables,
            form_fields=form_fields,
            metadata=metadata,
            errors=errors,
        )

    def detect_pdf_type(self, pdf_data: bytes) -> str:
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            text_pages = 0
            for page in doc:
                text = str(page.get_text("text") or "")
                if text and text.strip():
                    text_pages += 1

            if text_pages == 0:
                return "scanned"
            if text_pages == len(doc):
                return "digital"
            return "mixed"

    def extract_digital_text(self, pdf_data: bytes) -> list[PageContent]:
        pages: list[PageContent] = []

        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for idx in range(len(doc)):
                page = doc[idx]
                blocks = page.get_text("blocks")
                text = self._compose_text_from_blocks(blocks, page.rect.width)
                pages.append(
                    PageContent(
                        page_number=idx + 1,
                        text=text,
                        extraction_method="digital",
                        confidence=None,
                    )
                )

        return pages

    def extract_tables(self, pdf_data: bytes) -> list[TableData]:
        extracted_tables: list[TableData] = []

        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                for table_idx, table in enumerate(tables, start=1):
                    normalized = self._normalize_table(table)
                    if not normalized:
                        continue

                    headers = normalized[0]
                    rows = normalized[1:] if len(normalized) > 1 else []
                    extracted_tables.append(
                        TableData(
                            page_number=page_idx,
                            table_index=table_idx,
                            headers=headers,
                            rows=rows,
                        )
                    )

        return extracted_tables

    def ocr_scanned_pages(self, pdf_data: bytes, pages: list[int] | None = None) -> list[PageContent]:
        if pytesseract is None:
            self.logger.error("pytesseract is not installed; skipping OCR")
            return []

        page_contents: list[PageContent] = []

        try:
            with fitz.open(stream=pdf_data, filetype="pdf") as doc:
                page_numbers = pages if pages is not None else list(range(1, len(doc) + 1))
                dpi_scale = 300 / 72
                matrix = fitz.Matrix(dpi_scale, dpi_scale)

                for page_number in page_numbers:
                    if page_number < 1 or page_number > len(doc):
                        self.logger.warning("Skipping invalid page number for OCR: %s", page_number)
                        continue

                    page = doc[page_number - 1]
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))

                    text = pytesseract.image_to_string(image, lang=self.tesseract_lang)
                    data = pytesseract.image_to_data(
                        image,
                        lang=self.tesseract_lang,
                        output_type=pytesseract.Output.DICT,
                    )

                    conf_values: list[float] = []
                    for conf in data.get("conf", []):
                        try:
                            conf_val = float(conf)
                        except (TypeError, ValueError):
                            continue
                        if conf_val >= 0:
                            conf_values.append(conf_val)

                    confidence = None
                    if conf_values:
                        confidence = sum(conf_values) / (len(conf_values) * 100)

                    page_contents.append(
                        PageContent(
                            page_number=page_number,
                            text=(text or "").strip(),
                            extraction_method="ocr",
                            confidence=confidence,
                        )
                    )

        except Exception as exc:
            self.logger.exception("OCR processing failed: %s", exc)
            return []

        return page_contents

    def extract_form_fields(self, pdf_data: bytes) -> dict[str, str]:
        fields: dict[str, str] = {}

        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page in doc:
                widgets = page.widgets()
                if not widgets:
                    continue

                for widget in widgets:
                    name = str(widget.field_name or "").strip()
                    if not name:
                        continue
                    value = widget.field_value
                    fields[name] = "" if value is None else str(value)

        return fields

    def _extract_metadata(self, doc: fitz.Document) -> dict[str, str]:
        raw_meta = doc.metadata or {}
        metadata: dict[str, str] = {}
        for key, value in raw_meta.items():
            if value is None:
                continue
            metadata[str(key)] = str(value)
        return metadata

    def _compose_text_from_blocks(self, blocks: list[Any], page_width: float) -> str:
        clean_blocks: list[tuple[float, float, float, float, str]] = []
        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            if not text or not str(text).strip():
                continue
            clean_blocks.append((float(x0), float(y0), float(x1), float(y1), str(text).strip()))

        if not clean_blocks:
            return ""

        columns = self._split_columns(clean_blocks, page_width)
        ordered: list[tuple[float, float, float, float, str]] = []
        for col_blocks in columns:
            ordered.extend(sorted(col_blocks, key=lambda b: (b[1], b[0])))

        paragraphs: list[str] = []
        for _, _, _, _, text in ordered:
            normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if normalized:
                paragraphs.append(normalized)

        return "\n\n".join(paragraphs).strip()

    def _split_columns(
        self,
        blocks: list[tuple[float, float, float, float, str]],
        page_width: float,
    ) -> list[list[tuple[float, float, float, float, str]]]:
        if len(blocks) < 4:
            return [blocks]

        mid_x = page_width / 2
        left = [b for b in blocks if ((b[0] + b[2]) / 2) <= mid_x]
        right = [b for b in blocks if ((b[0] + b[2]) / 2) > mid_x]

        if not left or not right:
            return [blocks]

        left_max = max(b[2] for b in left)
        right_min = min(b[0] for b in right)
        gap = right_min - left_max
        if gap < page_width * 0.05:
            return [blocks]

        return [left, right]

    def _normalize_table(self, table: list[list[str | None]] | None) -> list[list[str]]:
        if not table:
            return []

        normalized_table: list[list[str]] = []
        for row in table:
            normalized_row: list[str] = []
            prev_val = ""
            for cell in row:
                if cell is None:
                    normalized_row.append(prev_val)
                    continue

                text = str(cell).strip()
                normalized_row.append(text)
                if text:
                    prev_val = text

            if any(cell.strip() for cell in normalized_row):
                normalized_table.append(normalized_row)

        return normalized_table
