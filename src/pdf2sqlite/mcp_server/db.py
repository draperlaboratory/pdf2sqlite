from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

Row = sqlite3.Row


class DatabaseError(Exception):
    """Base error for database access issues."""


class NotFoundError(DatabaseError):
    """Raised when the requested entity is not present."""


@dataclass(slots=True)
class Database:
    path: Path

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    async def fetch_one(self, query: str, params: Iterable[Any] = ()) -> Row | None:
        def task() -> Row | None:
            with closing(self._connect()) as conn, closing(conn.cursor()) as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchone()

        return await asyncio.to_thread(task)

    async def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[Row]:
        def task() -> list[Row]:
            with closing(self._connect()) as conn, closing(conn.cursor()) as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchall()

        return await asyncio.to_thread(task)

    async def fetch_value(self, query: str, params: Iterable[Any] = ()) -> Any:
        row = await self.fetch_one(query, params)
        if row is None:
            raise NotFoundError("No result for query")
        return row[0]

    async def ensure_pdf_exists(self, pdf_id: int) -> None:
        row = await self.fetch_one("SELECT id FROM pdfs WHERE id = ?", (pdf_id,))
        if row is None:
            raise NotFoundError(f"PDF {pdf_id} not found")

    async def get_pdf_counts(
        self,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT
                pdfs.id,
                pdfs.title,
                pdfs.description,
                COUNT(pdf_pages.id) AS page_count
            FROM pdfs
            LEFT JOIN pdf_pages ON pdf_pages.pdf_id = pdfs.id
            GROUP BY pdfs.id
            ORDER BY pdfs.id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(row) for row in rows]

    async def get_pdf_pages(
        self,
        pdf_id: int,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT
                id,
                pdf_id,
                page_number,
                gist,
                LENGTH(text) AS text_length,
                LENGTH(data) AS data_bytes
            FROM pdf_pages
            WHERE pdf_id = ?
            ORDER BY page_number
            LIMIT ? OFFSET ?
            """,
            (pdf_id, limit, offset),
        )
        return [dict(row) for row in rows]

    async def get_page_summary(self, page_id: int) -> dict[str, Any]:
        row = await self.fetch_one(
            """
            SELECT
                id,
                pdf_id,
                page_number,
                gist,
                LENGTH(text) AS text_length,
                LENGTH(data) AS data_bytes
            FROM pdf_pages
            WHERE id = ?
            """,
            (page_id,),
        )
        if row is None:
            raise NotFoundError(f"Page {page_id} not found")
        return dict(row)

    async def get_page_id(self, pdf_id: int, page_number: int) -> int:
        row = await self.fetch_one(
            "SELECT id FROM pdf_pages WHERE pdf_id = ? AND page_number = ?",
            (pdf_id, page_number),
        )
        if row is None:
            raise NotFoundError(
                f"Page {page_number} not found for PDF {pdf_id}"
            )
        return int(row[0])

    async def get_page_blob(self, pdf_id: int, page_number: int) -> bytes:
        row = await self.fetch_one(
            "SELECT data FROM pdf_pages WHERE pdf_id = ? AND page_number = ?",
            (pdf_id, page_number),
        )
        if row is None or row[0] is None:
            raise NotFoundError(
                f"No PDF data for page {page_number} in PDF {pdf_id}"
            )
        return bytes(row[0])

    async def get_page_blob_by_id(self, page_id: int) -> bytes:
        row = await self.fetch_one(
            "SELECT data FROM pdf_pages WHERE id = ?",
            (page_id,),
        )
        if row is None or row[0] is None:
            raise NotFoundError(f"No PDF data for page {page_id}")
        return bytes(row[0])

    async def get_pdf_page_rows(self, pdf_id: int) -> list[bytes]:
        rows = await self.fetch_all(
            "SELECT data FROM pdf_pages WHERE pdf_id = ? ORDER BY page_number",
            (pdf_id,),
        )
        if not rows:
            raise NotFoundError(f"No pages found for PDF {pdf_id}")
        payloads = []
        for row in rows:
            blob = row[0]
            if blob is None:
                raise NotFoundError(
                    f"PDF {pdf_id} has a page without stored PDF data"
                )
            payloads.append(bytes(blob))
        return payloads

    async def get_figures_for_page(self, page_id: int) -> list[dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT
                pdf_figures.id,
                pdf_figures.description,
                pdf_figures.mime_type,
                LENGTH(pdf_figures.data) AS data_bytes
            FROM pdf_figures
            JOIN page_to_figure ON page_to_figure.figure_id = pdf_figures.id
            WHERE page_to_figure.page_id = ?
            ORDER BY pdf_figures.id
            """,
            (page_id,),
        )
        return [dict(row) for row in rows]

    async def get_tables_for_page(self, page_id: int) -> list[dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT
                pdf_tables.id,
                pdf_tables.pdf_id,
                pdf_tables.page_number,
                pdf_tables.text,
                pdf_tables.description,
                pdf_tables.caption_above,
                pdf_tables.caption_below,
                pdf_tables.xmin,
                pdf_tables.ymin,
                LENGTH(pdf_tables.image) AS data_bytes,
                LENGTH(pdf_tables.text) AS text_length
            FROM pdf_tables
            JOIN page_to_table ON page_to_table.table_id = pdf_tables.id
            WHERE page_to_table.page_id = ?
            ORDER BY pdf_tables.id
            """,
            (page_id,),
        )
        return [dict(row) for row in rows]

    async def get_figure_blob(self, figure_id: int) -> tuple[bytes, str | None]:
        row = await self.fetch_one(
            "SELECT data, mime_type FROM pdf_figures WHERE id = ?",
            (figure_id,),
        )
        if row is None or row[0] is None:
            raise NotFoundError(f"Figure {figure_id} not found")
        return bytes(row[0]), row[1]

    async def get_table_image_blob(self, table_id: int) -> bytes:
        row = await self.fetch_one(
            "SELECT image FROM pdf_tables WHERE id = ?",
            (table_id,),
        )
        if row is None or row[0] is None:
            raise NotFoundError(f"Table image {table_id} not found")
        return bytes(row[0])

    async def get_table_summary(self, table_id: int) -> dict[str, Any]:
        row = await self.fetch_one(
            """
            SELECT
                id,
                pdf_id,
                page_number,
                description,
                caption_above,
                caption_below,
                LENGTH(image) AS data_bytes
            FROM pdf_tables
            WHERE id = ?
            """,
            (table_id,),
        )
        if row is None:
            raise NotFoundError(f"Table {table_id} not found")
        return dict(row)

    async def get_figure_summary(self, figure_id: int) -> dict[str, Any]:
        row = await self.fetch_one(
            """
            SELECT
                id,
                mime_type,
                description,
                LENGTH(data) AS data_bytes
            FROM pdf_figures
            WHERE id = ?
            """,
            (figure_id,),
        )
        if row is None:
            raise NotFoundError(f"Figure {figure_id} not found")
        return dict(row)

    async def get_schema(self, table: str | None = None) -> list[str]:
        if table:
            rows = await self.fetch_all(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            )
        else:
            rows = await self.fetch_all(
                "SELECT sql FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
            )
        statements = [row[0] for row in rows if row[0]]
        if not statements:
            raise NotFoundError(
                "No schema information found for the requested target"
            )
        return statements
