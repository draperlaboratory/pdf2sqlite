from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdf2sqlite.mcp_server.config import ServerConfig


def test_from_cli_reads_env_when_database_missing(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    db.write_bytes(b"SQLite format 3\0")
    monkeypatch.setenv("PDF2SQLITE_MCP_DATABASE", str(db))

    cfg = ServerConfig.from_cli(database=None)

    assert cfg.database_path == db.resolve()


def test_from_cli_validates_limits(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    db.write_bytes(b"SQLite format 3\0")

    # positive defaults
    cfg = ServerConfig.from_cli(str(db), default_limit=10, max_limit=20)
    assert cfg.clamp_limit(None) == 10

    # default limit > max limit is rejected
    with pytest.raises(ValueError):
        ServerConfig.from_cli(str(db), default_limit=30, max_limit=20)

    # zero means default; values over max are rejected
    assert cfg.clamp_limit(0) == 10
    with pytest.raises(ValueError):
        cfg.clamp_limit(9999)


def test_from_cli_env_overrides(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    db.write_bytes(b"SQLite format 3\0")

    monkeypatch.setenv("PDF2SQLITE_MCP_MAX_BLOB_BYTES", "1024")
    monkeypatch.setenv("PDF2SQLITE_MCP_DEFAULT_LIMIT", "5")
    monkeypatch.setenv("PDF2SQLITE_MCP_MAX_LIMIT", "6")

    cfg = ServerConfig.from_cli(str(db))

    assert cfg.max_blob_bytes == 1024
    assert cfg.default_limit == 5
    assert cfg.max_limit == 6


def test_from_cli_rejects_missing_database(monkeypatch):
    monkeypatch.delenv("PDF2SQLITE_MCP_DATABASE", raising=False)
    with pytest.raises(ValueError):
        ServerConfig.from_cli(database=None)
