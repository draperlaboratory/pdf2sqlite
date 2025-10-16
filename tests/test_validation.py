from __future__ import annotations

from argparse import Namespace

import pytest

from pdf2sqlite import validation


def test_validate_pdf_accepts_valid_pdf(tmp_path):
    pdf_path = tmp_path / "valid.pdf"
    pdf_path.write_bytes(b"%PDF-sample")

    validation.validate_pdf(str(pdf_path))


def test_validate_pdf_rejects_invalid_pdf(tmp_path):
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_bytes(b"%PDX")

    with pytest.raises(SystemExit) as excinfo:
        validation.validate_pdf(str(pdf_path))

    assert "isn't a valid PDF" in str(excinfo.value)


def test_validate_database_accepts_valid_sqlite(tmp_path):
    db_path = tmp_path / "valid.sqlite"
    db_path.write_bytes(b"SQLite format 3\0")

    validation.validate_database(str(db_path))


def test_validate_database_rejects_invalid_sqlite(tmp_path):
    db_path = tmp_path / "invalid.sqlite"
    db_path.write_bytes(b"NotSQL")

    with pytest.raises(SystemExit) as excinfo:
        validation.validate_database(str(db_path))

    assert "isn't a valid SQLite database" in str(excinfo.value)


def test_validate_llms_allows_supported_models(monkeypatch):
    args = Namespace(
        vision_model="vision-model",
        summarizer="summarizer-model",
        abstracter="abstracter-model",
    )

    monkeypatch.setattr(
        validation.litellm.utils,
        "supports_vision",
        lambda _: True,
    )
    monkeypatch.setattr(
        validation.litellm.utils,
        "supports_pdf_input",
        lambda _: True,
    )

    validation.validate_llms(args)


def test_validate_llms_rejects_unsupported_vision_model(monkeypatch):
    args = Namespace(
        vision_model="vision-model",
        summarizer=None,
        abstracter=None,
    )

    monkeypatch.setattr(
        validation.litellm.utils,
        "supports_vision",
        lambda _: False,
    )

    with pytest.raises(SystemExit) as excinfo:
        validation.validate_llms(args)

    assert "doesn't support image inputs" in str(excinfo.value)
