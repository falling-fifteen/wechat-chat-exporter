"""Output writers."""

from __future__ import annotations

from .base import ExportContext, Exporter
from .csv import CsvExporter
from .docx import DocxExporter
from .html import HtmlExporter
from .jsonl import JsonlExporter
from .pdf import PdfExporter
from .xlsx import XlsxExporter

EXPORTERS: dict[str, type[Exporter]] = {
    "csv": CsvExporter,
    "xlsx": XlsxExporter,
    "html": HtmlExporter,
    "pdf": PdfExporter,
    "docx": DocxExporter,
    "jsonl": JsonlExporter,
}

__all__ = ["EXPORTERS", "ExportContext"]
