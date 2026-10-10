"""Convert any supported file to markdown with Docling. Images are dropped."""

from functools import cache
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.types.doc import ImageRefMode

PLAIN_TEXT = {".txt", ".md", ".markdown"}


@cache
def _converter() -> DocumentConverter:
    return DocumentConverter()


def to_markdown(path: Path) -> str:
    if path.suffix.lower() in PLAIN_TEXT:
        return path.read_text(encoding="utf-8", errors="replace")
    document = _converter().convert(path).document
    return document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="")
