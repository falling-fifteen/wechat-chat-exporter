from __future__ import annotations

from pathlib import Path

import pytest

from wechat_chat_exporter.export.base import ExportContext
from wechat_chat_exporter.export.csv import CsvExporter, safe_cell
from wechat_chat_exporter.export.docx import DocxExporter
from wechat_chat_exporter.export.html import HtmlExporter
from wechat_chat_exporter.export.pdf import PdfExporter
from wechat_chat_exporter.export.xlsx import XlsxExporter
from wechat_chat_exporter.model.message import Message


def _message(text: str, sender: str = "我", ts: int = 1700000000) -> Message:
    return Message(
        local_id=1,
        server_id=1,
        timestamp=ts,
        sort_seq=ts * 1000,
        sender_id=1,
        sender_name=sender,
        local_type=1,
        base_type=1,
        sub_type=0,
        kind="文字",
        text=text,
    )


def test_csv_formula_injection() -> None:
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("正常文本") == "正常文本"


def test_csv_export(tmp_path: Path) -> None:
    ctx = ExportContext(out_dir=tmp_path)
    path = CsvExporter().write([_message("=1+1"), _message("你好")], tmp_path / "a.csv", ctx)
    raw = path.read_text(encoding="utf-8-sig")
    assert "'=1+1" in raw
    assert "你好" in raw


def test_html_escapes(tmp_path: Path) -> None:
    ctx = ExportContext(out_dir=tmp_path)
    path = HtmlExporter().write([_message("<script>alert(1)</script>")], tmp_path / "a.html", ctx)
    raw = path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in raw
    assert "&lt;script&gt;" in raw


def test_xlsx_export(tmp_path: Path) -> None:
    from openpyxl import load_workbook

    ctx = ExportContext(out_dir=tmp_path)
    path = XlsxExporter().write([_message("你好")], tmp_path / "a.xlsx", ctx)
    wb = load_workbook(path)
    ws = wb.active
    assert ws.max_row == 2
    assert ws.cell(row=2, column=4).value == "你好"


def test_docx_export(tmp_path: Path) -> None:
    from docx import Document

    ctx = ExportContext(out_dir=tmp_path)
    path = DocxExporter().write([_message("你好")], tmp_path / "a.docx", ctx)
    doc = Document(path)
    assert any("你好" in p.text for p in doc.paragraphs)


def test_pdf_export(tmp_path: Path) -> None:
    from wechat_chat_exporter.export.pdf import _find_font

    try:
        _find_font()
    except Exception:
        pytest.skip("no CJK font available on this platform")
    ctx = ExportContext(out_dir=tmp_path)
    path = PdfExporter().write([_message("你好")], tmp_path / "a.pdf", ctx)
    assert path.stat().st_size > 0
