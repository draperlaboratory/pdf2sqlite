from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.types import EmbeddedResource, TextContent, ToolAnnotations

from .config import ServerConfig
from .db import Database, NotFoundError
from .resources import (
    ResourceService,
    build_figure_payload,
    build_page_payload,
    build_pdf_payload,
    build_table_payload,
)
from .uri import (
    FigureResource,
    PdfResource,
    TableImageResource,
    parse_resource_uri,
)


@dataclass(slots=True)
class ToolSuite:
    server: FastMCP
    database: Database
    resources: ResourceService
    config: ServerConfig

    def register(self) -> None:
        annotations = ToolAnnotations(readOnlyHint=True)

        @self.server.tool(
            name="list_pdfs",
            description=
            "List the PDFs stored in the database along with metadata and "
            "resource URIs",
            annotations=annotations,
        )
        async def list_pdfs(
            limit: int | None = None,
            offset: int = 0,
        ) -> dict[str, object]:
            capped_limit = self.config.clamp_limit(limit)
            rows = await self.database.get_pdf_counts(capped_limit, offset)
            items = [build_pdf_payload(row) for row in rows]
            return {"pdfs": items, "limit": capped_limit, "offset": offset}

        @self.server.tool(
            name="list_pdf_pages",
            description=
            "List pages for a PDF with summaries and resource identifiers",
            annotations=annotations,
        )
        async def list_pdf_pages(
            pdf_id: int,
            limit: int | None = None,
            offset: int = 0,
        ) -> dict[str, object]:
            await self.database.ensure_pdf_exists(pdf_id)
            capped_limit = self.config.clamp_limit(limit)
            rows = await self.database.get_pdf_pages(pdf_id, capped_limit, offset)
            pages = [build_page_payload(row) for row in rows]
            return {
                "pdf_id": pdf_id,
                "pages": pages,
                "limit": capped_limit,
                "offset": offset,
            }

        @self.server.tool(
            name="list_page_assets",
            description=
            "List figures and tables associated with a page",
            annotations=annotations,
        )
        async def list_page_assets(page_id: int) -> dict[str, object]:
            summary = await self.database.get_page_summary(page_id)
            figures = await self.database.get_figures_for_page(page_id)
            tables = await self.database.get_tables_for_page(page_id)
            return {
                "page": build_page_payload(summary),
                "figures": [build_figure_payload(row) for row in figures],
                "tables": [build_table_payload(row) for row in tables],
            }

        @self.server.tool(
            name="get_schema",
            description="Return CREATE statements for tables or views",
            annotations=annotations,
        )
        async def get_schema(table: str | None = None) -> dict[str, object]:
            statements = await self.database.get_schema(table)
            return {"table": table, "sql": statements}

        @self.server.tool(
            name="get_image",
            description="Return an image resource as inline tool output",
            annotations=annotations,
        )
        async def get_image(resource: str) -> Image:
            descriptor = parse_resource_uri(resource)
            if isinstance(descriptor, FigureResource):
                data, mime = await self.resources.load_figure_blob(descriptor)
                return self.resources.as_image(data, mime)
            if isinstance(descriptor, TableImageResource):
                data = await self.resources.load_table_image_blob(descriptor)
                return self.resources.as_image(data, "image/jpeg")
            raise ValueError(
                "get_image expects a figure or table-image resource URI"
            )

        @self.server.tool(
            name="get_pdf",
            description="Return a PDF resource embedded in the tool response",
            annotations=annotations,
        )
        async def get_pdf(resource: str) -> list[EmbeddedResource | TextContent]:
            descriptor = parse_resource_uri(resource)
            if not isinstance(descriptor, PdfResource):
                raise ValueError(
                    "get_pdf expects a pdf resource URI, optionally targeting "
                    "a single page"
                )
            data = await self.resources.load_pdf_blob(descriptor)
            embed = await self.resources.make_embedded_pdf(resource, data)
            summary = _pdf_summary_block(resource, len(data), descriptor)
            return [summary, embed]


def _pdf_summary_block(
    resource: str,
    size: int,
    descriptor: PdfResource,
) -> TextContent:
    if descriptor.page_number is None:
        target = f"PDF {descriptor.pdf_id}"
    else:
        target = (
            f"PDF {descriptor.pdf_id} page {descriptor.page_number}"
        )
    text = (
        f"Returning {target} as an embedded PDF resource. URI: {resource}. "
        f"Bytes: {size}."
    )
    return TextContent(type="text", text=text)
