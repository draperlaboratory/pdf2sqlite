from __future__ import annotations

import pytest

from pdf2sqlite.mcp_server.tools import _pdf_summary_block
from pdf2sqlite.mcp_server.uri import PdfResource


def test_pdf_summary_block_for_full_pdf():
    block = _pdf_summary_block(
        "pdf2sqlite://pdf/1",
        1234,
        PdfResource(1),
    )
    assert "PDF 1" in block.text
    assert "Bytes: 1234" in block.text


def test_pdf_summary_block_for_single_page():
    block = _pdf_summary_block(
        "pdf2sqlite://pdf/2/page/5",
        77,
        PdfResource(2, 5),
    )
    assert "PDF 2 page 5" in block.text
    assert "Bytes: 77" in block.text
