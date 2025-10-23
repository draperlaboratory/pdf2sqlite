from __future__ import annotations

from pathlib import Path

import pytest

from pdf2sqlite.mcp_server.db import Database


TEST_DB = Path("tests/test.db").resolve()


@pytest.mark.skipif(not TEST_DB.exists(), reason="tests/test.db missing")
def test_db_pdf_counts_pages_and_blobs():
    db = Database(TEST_DB)

    pdfs = asyncio_run(db.get_pdf_counts(10, 0))
    assert isinstance(pdfs, list)
    assert pdfs, "expected at least one pdf in tests/test.db"

    first_pdf_id = int(pdfs[0]["id"])  # type: ignore[index]

    pages = asyncio_run(db.get_pdf_pages(first_pdf_id, 1, 0))
    assert pages, "expected at least one page for first pdf"

    page = pages[0]
    page_id = int(page["id"])  # type: ignore[index]
    page_num = int(page["page_number"])  # type: ignore[index]

    blob = asyncio_run(db.get_page_blob(first_pdf_id, page_num))
    assert isinstance(blob, (bytes, bytearray))
    assert blob.startswith(b"%PDF"), "page blob should be a PDF"

    blob2 = asyncio_run(db.get_page_blob_by_id(page_id))
    assert blob2.startswith(b"%PDF")


@pytest.mark.skipif(not TEST_DB.exists(), reason="tests/test.db missing")
def test_db_schema_nonempty():
    db = Database(TEST_DB)

    stmts = asyncio_run(db.get_schema())
    assert any("CREATE TABLE" in s for s in stmts)
    assert any("pdfs" in s for s in stmts)


@pytest.mark.skipif(not TEST_DB.exists(), reason="tests/test.db missing")
def test_db_page_assets_optional():
    db = Database(TEST_DB)

    pdfs = asyncio_run(db.get_pdf_counts(1, 0))
    if not pdfs:
        pytest.skip("no pdfs present in test db")
    pdf_id = int(pdfs[0]["id"])  # type: ignore[index]

    pages = asyncio_run(db.get_pdf_pages(pdf_id, 1, 0))
    if not pages:
        pytest.skip("no pages present in test db")
    page_id = int(pages[0]["id"])  # type: ignore[index]

    figures = asyncio_run(db.get_figures_for_page(page_id))
    tables = asyncio_run(db.get_tables_for_page(page_id))

    assert isinstance(figures, list)
    assert isinstance(tables, list)

    if figures:
        fid = int(figures[0]["id"])  # type: ignore[index]
        blob, mime = asyncio_run(db.get_figure_blob(fid))
        assert isinstance(blob, (bytes, bytearray))
        assert mime is None or isinstance(mime, str)

    if tables:
        tid = int(tables[0]["id"])  # type: ignore[index]
        img = asyncio_run(db.get_table_image_blob(tid))
        assert isinstance(img, (bytes, bytearray))


# helpers
import asyncio


def asyncio_run(awaitable):
    return asyncio.get_event_loop().run_until_complete(awaitable)
