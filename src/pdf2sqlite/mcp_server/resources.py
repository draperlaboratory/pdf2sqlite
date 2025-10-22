from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from types import MethodType
from typing import Any, Awaitable, Callable, Mapping, cast

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.resources.types import FunctionResource
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import BlobResourceContents, EmbeddedResource
from pydantic import AnyUrl
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
                uri=cast(AnyUrl, uri),
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


def _patch_dynamic_blob_template(
    server: FastMCP,
    uri_template: str,
    *,
    default_mime: str,
    loader: Callable[
        [Mapping[str, object], Context | None],
        Awaitable[tuple[bytes, str | None]],
    ],
) -> None:
    template = server._resource_manager._templates.get(uri_template)
    if template is None:
        raise RuntimeError(
            f"Resource template {uri_template} is not registered"
        )

    async def create_resource(
        self: Any,
        uri: str,
        params: Mapping[str, object],
        context: Context | None = None,
    ) -> FunctionResource:
        payload, mime_type = await loader(params, context)
        return FunctionResource(
            uri=uri,  # type: ignore[arg-type]
            name=self.name,
            title=self.title,
            description=self.description,
            mime_type=mime_type or default_mime,
            icons=self.icons,
            annotations=self.annotations,
            fn=lambda payload=payload: payload,
        )

    template.mime_type = default_mime
    object.__setattr__(template, "create_resource", MethodType(create_resource, template))


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

    async def _figure_loader(
        params: Mapping[str, object],
        ctx: Context | None,
    ) -> tuple[bytes, str | None]:  # noqa: ARG001
        figure_id = _require_int(params.get("figure_id"), "figure.figure_id")
        return await service.load_figure_blob(FigureResource(figure_id))

    async def _table_loader(
        params: Mapping[str, object],
        ctx: Context | None,
    ) -> tuple[bytes, str | None]:  # noqa: ARG001
        table_id = _require_int(params.get("table_id"), "table.table_id")
        data = await service.load_table_image_blob(
            TableImageResource(table_id)
        )
        return data, "image/jpeg"

    _patch_dynamic_blob_template(
        server,
        "pdf2sqlite://figure/{figure_id}",
        default_mime="application/octet-stream",
        loader=_figure_loader,
    )
    _patch_dynamic_blob_template(
        server,
        "pdf2sqlite://table-image/{table_id}",
        default_mime="image/jpeg",
        loader=_table_loader,
    )


def _require_int(value: object | None, label: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{label} must not be empty")
        try:
            return int(stripped)
        except ValueError as exc:
            msg = f"{label} must be an integer-compatible value, got {value!r}"
            raise ValueError(msg) from exc
    if value is None:
        raise ValueError(f"{label} is required")
    raise TypeError(f"{label} must be int-like, got {type(value).__name__}")


def _optional_int(value: object | None, label: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, label)


def build_page_payload(page: Mapping[str, object]) -> dict[str, object]:
    pdf_id = _require_int(page.get("pdf_id"), "page.pdf_id")
    page_number = _require_int(page.get("page_number"), "page.page_number")
    resource_uri = build_pdf_page_uri(pdf_id, page_number)
    return {
        "page_id": _require_int(page.get("id"), "page.id"),
        "pdf_id": pdf_id,
        "page_number": page_number,
        "gist": page.get("gist"),
        "text_length": _optional_int(page.get("text_length"), "page.text_length"),
        "data_bytes": _optional_int(page.get("data_bytes"), "page.data_bytes"),
        "resource": resource_uri,
    }


def build_pdf_payload(pdf: Mapping[str, object]) -> dict[str, object]:
    pdf_id = _require_int(pdf.get("id"), "pdf.id")
    return {
        "pdf_id": pdf_id,
        "title": pdf.get("title"),
        "description": pdf.get("description"),
        "page_count": _optional_int(pdf.get("page_count"), "pdf.page_count"),
        "resource": build_pdf_uri(pdf_id),
    }


def build_figure_payload(figure: Mapping[str, object]) -> dict[str, object]:
    figure_id = _require_int(figure.get("id"), "figure.id")
    return {
        "figure_id": figure_id,
        "description": figure.get("description"),
        "mime_type": figure.get("mime_type"),
        "data_bytes": _optional_int(figure.get("data_bytes"), "figure.data_bytes"),
        "resource": build_figure_uri(figure_id),
    }


def build_table_payload(table: Mapping[str, object]) -> dict[str, object]:
    table_id = _require_int(table.get("id"), "table.id")
    payload: dict[str, object] = {
        "table_id": table_id,
        "description": table.get("description"),
        "caption_above": table.get("caption_above"),
        "caption_below": table.get("caption_below"),
        "text": table.get("text"),
        "resource": build_table_image_uri(table_id),
    }
    text_length = _optional_int(table.get("text_length"), "table.text_length")
    if text_length is not None:
        payload["text_length"] = text_length
    data_bytes = _optional_int(table.get("data_bytes"), "table.data_bytes")
    if data_bytes is not None:
        payload["data_bytes"] = data_bytes
    xmin = _optional_int(table.get("xmin"), "table.xmin")
    if xmin is not None:
        payload["xmin"] = xmin
    ymin = _optional_int(table.get("ymin"), "table.ymin")
    if ymin is not None:
        payload["ymin"] = ymin
    pdf_id = _optional_int(table.get("pdf_id"), "table.pdf_id")
    page_number = _optional_int(table.get("page_number"), "table.page_number")
    if pdf_id is not None:
        payload["pdf_id"] = pdf_id
    if page_number is not None:
        payload["page_number"] = page_number
    if pdf_id is not None and page_number is not None:
        payload["page_resource"] = build_pdf_page_uri(pdf_id, page_number)
    return payload
