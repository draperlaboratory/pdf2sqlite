from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import BlobResourceContents, EmbeddedResource
from pypdf import PdfReader, PdfWriter

from .config import ServerConfig
from .db import Database, NotFoundError
from .uri import (
    FigureResource,
    PdfResource,
    TableImageResource,
    build_figure_uri,
    build_pdf_page_uri,
    build_pdf_uri,
    build_table_image_uri,
)


class ResourceTooLargeError(ValueError):
    """Raised when a blob exceeds the configured size limit."""


@dataclass(slots=True)
class ResourceService:
    database: Database
    config: ServerConfig

    def _check_size(self, payload: bytes, label: str) -> bytes:
        if len(payload) > self.config.max_blob_bytes:
            raise ResourceTooLargeError(
                f"{label} is {len(payload)} bytes, which exceeds the configured "
                f"limit of {self.config.max_blob_bytes} bytes"
            )
        return payload

    async def load_pdf_blob(self, pdf: PdfResource) -> bytes:
        if pdf.page_number is None:
            pages = await self.database.get_pdf_page_rows(pdf.pdf_id)
            writer = PdfWriter()
            for page_bytes in pages:
                reader = PdfReader(io.BytesIO(page_bytes))
                for page in reader.pages:
                    writer.add_page(page)
            buffer = io.BytesIO()
            writer.write(buffer)
            payload = buffer.getvalue()
            if not payload:
                raise NotFoundError(f"PDF {pdf.pdf_id} is empty")
            return self._check_size(payload, f"PDF {pdf.pdf_id}")

        blob = await self.database.get_page_blob(pdf.pdf_id, pdf.page_number)
        return self._check_size(blob, f"PDF {pdf.pdf_id} page {pdf.page_number}")

    async def load_figure_blob(self, figure: FigureResource) -> tuple[bytes, str | None]:
        blob, mime = await self.database.get_figure_blob(figure.figure_id)
        blob = self._check_size(blob, f"figure {figure.figure_id}")
        return blob, mime

    async def load_table_image_blob(self, table: TableImageResource) -> bytes:
        blob = await self.database.get_table_image_blob(table.table_id)
        return self._check_size(blob, f"table image {table.table_id}")

    async def make_embedded_pdf(self, uri: str, data: bytes) -> EmbeddedResource:
        encoded = base64.b64encode(data).decode("ascii")
        return EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(
                uri=uri,
                mimeType="application/pdf",
                blob=encoded,
                _meta={"size": len(data)},
            ),
        )

    def as_image(self, data: bytes, mime_type: str | None) -> Image:
        subtype: str | None = None
        if mime_type and "/" in mime_type:
            subtype = mime_type.split("/", 1)[1]
        return Image(data=data, format=subtype)


def register_resources(server: FastMCP, service: ResourceService) -> None:
    @server.resource(
        "pdf2sqlite://pdf/{pdf_id}",
        name="pdf2sqlite.pdf",
        title="Full PDF document",
        description="Render the complete PDF reconstructed from stored pages",
        mime_type="application/pdf",
    )
    async def read_pdf(pdf_id: int, ctx: Context | None = None) -> bytes:  # noqa: ARG001
        pdf = PdfResource(pdf_id=pdf_id)
        return await service.load_pdf_blob(pdf)

    @server.resource(
        "pdf2sqlite://pdf/{pdf_id}/page/{page_number}",
        name="pdf2sqlite.pdf_page",
        title="Individual PDF page",
        description="A single-page PDF extracted during ingestion",
        mime_type="application/pdf",
    )
    async def read_pdf_page(pdf_id: int, page_number: int, ctx: Context | None = None) -> bytes:  # noqa: ARG001
        pdf = PdfResource(pdf_id=pdf_id, page_number=page_number)
        return await service.load_pdf_blob(pdf)

    @server.resource(
        "pdf2sqlite://figure/{figure_id}",
        name="pdf2sqlite.figure",
        title="Figure image",
        description="Image blob captured from the PDF",
    )
    async def read_figure(figure_id: int, ctx: Context | None = None) -> bytes:  # noqa: ARG001
        blob, _ = await service.load_figure_blob(FigureResource(figure_id))
        return blob

    @server.resource(
        "pdf2sqlite://table-image/{table_id}",
        name="pdf2sqlite.table_image",
        title="Table rendering",
        description="Rendered table image captured during parsing",
    )
    async def read_table_image(table_id: int, ctx: Context | None = None) -> bytes:  # noqa: ARG001
        return await service.load_table_image_blob(TableImageResource(table_id))


def build_page_payload(page: dict[str, int | str | None]) -> dict[str, object]:
    pdf_id = int(page["pdf_id"])
    page_number = int(page["page_number"])
    resource_uri = build_pdf_page_uri(pdf_id, page_number)
    return {
        "page_id": int(page["id"]),
        "pdf_id": pdf_id,
        "page_number": page_number,
        "gist": page.get("gist"),
        "text_length": page.get("text_length"),
        "data_bytes": page.get("data_bytes"),
        "resource": resource_uri,
    }


def build_pdf_payload(pdf: dict[str, object]) -> dict[str, object]:
    pdf_id = int(pdf["id"])
    return {
        "pdf_id": pdf_id,
        "title": pdf.get("title"),
        "description": pdf.get("description"),
        "page_count": pdf.get("page_count"),
        "resource": build_pdf_uri(pdf_id),
    }


def build_figure_payload(figure: dict[str, object]) -> dict[str, object]:
    figure_id = int(figure["id"])
    return {
        "figure_id": figure_id,
        "description": figure.get("description"),
        "mime_type": figure.get("mime_type"),
        "data_bytes": figure.get("data_bytes"),
        "resource": build_figure_uri(figure_id),
    }


def build_table_payload(table: dict[str, object]) -> dict[str, object]:
    table_id = int(table["id"])
    payload: dict[str, object] = {
        "table_id": table_id,
        "description": table.get("description"),
        "caption_above": table.get("caption_above"),
        "caption_below": table.get("caption_below"),
        "data_bytes": table.get("data_bytes"),
        "resource": build_table_image_uri(table_id),
    }
    if "pdf_id" in table and "page_number" in table:
        payload["pdf_id"] = table.get("pdf_id")
        payload["page_number"] = table.get("page_number")
        payload["page_resource"] = build_pdf_page_uri(
            int(table["pdf_id"]),
            int(table["page_number"]),
        )
    return payload
