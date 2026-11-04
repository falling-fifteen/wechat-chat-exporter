"""Orchestrate one session's export across formats and time buckets."""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..model.message import Message
from . import EXPORTERS
from .base import ExportContext, Exporter
from .naming import sanitize
from .pdf import PdfExporter

BUCKET_FORMATS = {"html", "pdf", "docx"}


@dataclass
class ExportResult:
    files: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    records: int = 0


def bucket_for(timestamp: int, split: str, tz: datetime.tzinfo | None) -> str:
    if split == "none":
        return ""
    dt = datetime.datetime.fromtimestamp(timestamp, tz)
    return dt.strftime("%Y") if split == "year" else dt.strftime("%Y-%m")


def _groups(messages: list[Message], split: str, tz: datetime.tzinfo | None):
    if split == "none":
        yield "", messages
        return
    current = None
    bucket: list[Message] = []
    for msg in messages:
        key = bucket_for(msg.timestamp, split, tz)
        if current is None:
            current = key
        if key != current:
            yield current, bucket
            bucket = []
            current = key
        bucket.append(msg)
    if bucket:
        yield current or "", bucket


def export_session(
    messages: list[Message],
    *,
    out_dir: Path,
    display_name: str,
    session_username: str,
    formats: list[str],
    split: str,
    tz: datetime.tzinfo | None,
    image_mode: str,
    overwrite: str,
    pdf_font: str | None = None,
    me_label: str = "我",
) -> ExportResult:
    result = ExportResult(records=len(messages))
    out_dir.mkdir(parents=True, exist_ok=True)
    title = display_name or session_username or "聊天记录"
    slug = sanitize(title)

    for fmt in formats:
        exporter_cls = EXPORTERS.get(fmt)
        if exporter_cls is None:
            result.errors.append(f"未知格式: {fmt}")
            continue
        exporter: Exporter = PdfExporter(pdf_font) if fmt == "pdf" else exporter_cls()
        mode = split
        if mode == "auto":
            mode = "month" if fmt in BUCKET_FORMATS else "none"
        for bucket, part in _groups(messages, mode, tz):
            suffix = f"_{bucket}" if bucket else ""
            filename = f"{slug}{suffix}.{exporter.ext}"
            path = out_dir / filename
            if path.exists() and overwrite != "force":
                result.skipped.append(path)
                continue
            ctx = ExportContext(
                out_dir=out_dir,
                title=f"{title}{(' ' + bucket) if bucket else ''}",
                me_label=me_label,
                session_username=session_username,
                session_display=display_name,
                bucket=bucket,
                image_mode=image_mode,
                overwrite=overwrite,
                tz=tz,
            )
            try:
                exporter.write(part, path, ctx)
                result.files.append(path)
            except Exception as exc:  # keep other formats going
                result.errors.append(f"{filename}: {exc}")

    manifest = {
        "schema_version": 1,
        "session": {"username": session_username, "display": display_name},
        "records": len(messages),
        "formats": formats,
        "split": split,
        "files": [
            {
                "path": p.name,
                "bytes": p.stat().st_size,
                "sha256": _sha256(p),
            }
            for p in result.files
            if p.exists()
        ],
        "skipped": [p.name for p in result.skipped],
        "errors": result.errors,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
