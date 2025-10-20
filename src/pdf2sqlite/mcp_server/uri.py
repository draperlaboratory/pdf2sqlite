from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class ResourceKind(str, Enum):
    PDF = "pdf"
    PDF_PAGE = "pdf_page"
    FIGURE = "figure"
    TABLE_IMAGE = "table_image"


@dataclass(slots=True)
class PdfResource:
    pdf_id: int
    page_number: int | None = None


@dataclass(slots=True)
class FigureResource:
    figure_id: int


@dataclass(slots=True)
class TableImageResource:
    table_id: int


ResourceDescriptor = PdfResource | FigureResource | TableImageResource


def parse_resource_uri(uri: str) -> ResourceDescriptor:
    parsed = urlparse(uri)
    if parsed.scheme != "pdf2sqlite":
        raise ValueError("Unsupported resource scheme")

    netloc = parsed.netloc
    if not netloc:
        raise ValueError("Resource URI must include a target segment")

    segments = [segment for segment in parsed.path.split("/") if segment]

    if netloc == "pdf":
        if not segments:
            raise ValueError("PDF resource path must include an identifier")
        pdf_id = _require_int(segments[0], "pdf id")
        if len(segments) == 1:
            return PdfResource(pdf_id=pdf_id)
        if len(segments) == 3 and segments[1] == "page":
            page_number = _require_int(segments[2], "page number")
            return PdfResource(pdf_id=pdf_id, page_number=page_number)
        raise ValueError("Unsupported PDF resource path")

    if netloc == "figure":
        if len(segments) != 1:
            raise ValueError("Figure resource requires a single identifier")
        return FigureResource(figure_id=_require_int(segments[0], "figure id"))

    if netloc == "table-image":
        if len(segments) != 1:
            raise ValueError("Table image resource requires a single identifier")
        return TableImageResource(table_id=_require_int(segments[0], "table id"))

    raise ValueError(f"Unsupported resource target '{netloc}'")


def build_pdf_uri(pdf_id: int) -> str:
    return f"pdf2sqlite://pdf/{pdf_id}"


def build_pdf_page_uri(pdf_id: int, page_number: int) -> str:
    return f"pdf2sqlite://pdf/{pdf_id}/page/{page_number}"


def build_figure_uri(figure_id: int) -> str:
    return f"pdf2sqlite://figure/{figure_id}"


def build_table_image_uri(table_id: int) -> str:
    return f"pdf2sqlite://table-image/{table_id}"


def _require_int(value: str, label: str) -> int:
    try:
        return int(value, 10)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: '{value}'") from exc
