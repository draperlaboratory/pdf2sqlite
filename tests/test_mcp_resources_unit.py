from __future__ import annotations

from pathlib import Path

import pytest

from pdf2sqlite.mcp_server.config import ServerConfig
from pdf2sqlite.mcp_server.db import Database
from pdf2sqlite.mcp_server.resources import (
    ResourceService,
    ResourceTooLargeError,
    build_page_payload,
)
from mcp.server.fastmcp.utilities.types import Image as MCPImage
from pdf2sqlite.mcp_server.uri import PdfResource


TEST_DB = Path("tests/test.db").resolve()


@pytest.mark.skipif(not TEST_DB.exists(), reason="tests/test.db missing")
def test_resource_service_pdf_blobs_and_limits():
    # tiny limit to force overflow on any real PDF blob
    cfg = ServerConfig(
        database_path=TEST_DB,
        max_blob_bytes=1,
        default_limit=10,
        max_limit=10,
    )
    db = Database(TEST_DB)
    svc = ResourceService(database=db, config=cfg)

    # pick first pdf id
    pdfs = asyncio_run(db.get_pdf_counts(1, 0))
    if not pdfs:
        pytest.skip("no pdfs present in test db")
    pdf_id = int(pdfs[0]["id"])  # type: ignore[index]

    # page blob should exceed limit and raise
    page = asyncio_run(db.get_pdf_pages(pdf_id, 1, 0))[0]
    page_num = int(page["page_number"])  # type: ignore[index]

    with pytest.raises(ResourceTooLargeError):
        asyncio_run(svc.load_pdf_blob(PdfResource(pdf_id, page_num)))

    # bump limit so full-pdf works and returns a valid PDF
    cfg.max_blob_bytes = 10_000_000
    data = asyncio_run(svc.load_pdf_blob(PdfResource(pdf_id)))
    assert data.startswith(b"%PDF")

    embed = asyncio_run(svc.make_embedded_pdf(
        f"pdf2sqlite://pdf/{pdf_id}", data
    ))
    assert embed.resource.mimeType == "application/pdf"
    assert embed.resource.meta["size"] == len(data)

    # as_image returns an MCP Image object
    img = svc.as_image(b"x", "image/png")
    assert isinstance(img, MCPImage)


def test_build_page_payload_validates_fields():
    # missing required id
    with pytest.raises(ValueError):
        build_page_payload({"pdf_id": 1, "page_number": 1})
    # non-int page number
    with pytest.raises(ValueError):
        build_page_payload({"id": 1, "pdf_id": 1, "page_number": "x"})


# helpers
import asyncio


def asyncio_run(awaitable):
    return asyncio.get_event_loop().run_until_complete(awaitable)
