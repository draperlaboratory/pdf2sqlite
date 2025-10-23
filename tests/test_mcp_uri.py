from __future__ import annotations

import pytest

from pdf2sqlite.mcp_server.uri import (
    PdfResource,
    FigureResource,
    TableImageResource,
    build_pdf_uri,
    build_pdf_page_uri,
    build_figure_uri,
    build_table_image_uri,
    parse_resource_uri,
)


def test_parse_pdf_uri_full_document():
    uri = "pdf2sqlite://pdf/123"
    desc = parse_resource_uri(uri)
    assert isinstance(desc, PdfResource)
    assert desc.pdf_id == 123
    assert desc.page_number is None
    assert build_pdf_uri(123) == uri


def test_parse_pdf_uri_single_page():
    uri = "pdf2sqlite://pdf/456/page/7"
    desc = parse_resource_uri(uri)
    assert isinstance(desc, PdfResource)
    assert desc.pdf_id == 456
    assert desc.page_number == 7
    assert build_pdf_page_uri(456, 7) == uri


def test_parse_figure_uri():
    uri = "pdf2sqlite://figure/999"
    desc = parse_resource_uri(uri)
    assert isinstance(desc, FigureResource)
    assert desc.figure_id == 999
    assert build_figure_uri(999) == uri


def test_parse_table_image_uri():
    uri = "pdf2sqlite://table-image/42"
    desc = parse_resource_uri(uri)
    assert isinstance(desc, TableImageResource)
    assert desc.table_id == 42
    assert build_table_image_uri(42) == uri


def test_parse_uri_rejects_bad_scheme():
    with pytest.raises(ValueError):
        parse_resource_uri("http://pdf/1")


def test_parse_uri_rejects_missing_target():
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://")


def test_parse_uri_rejects_malformed_pdf_paths():
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://pdf/")
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://pdf/123/page/")
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://pdf/123/x/1")


def test_parse_uri_rejects_non_int_identifiers():
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://pdf/abc")
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://pdf/1/page/two")
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://figure/notanint")
    with pytest.raises(ValueError):
        parse_resource_uri("pdf2sqlite://table-image/notanint")
