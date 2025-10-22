from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = ROOT / ".venv" / "lib" / "python3.13" / "site-packages"
if SITE_PACKAGES.exists():
    sys.path.append(str(SITE_PACKAGES))

pytest.importorskip("mcp.server.fastmcp")

from pdf2sqlite.mcp_server.config import ServerConfig
from pdf2sqlite.mcp_server.server import build_server


def test_server_builds_with_resource_templates() -> None:
    db_path = Path("docs.db").resolve()
    if not db_path.exists():
        pytest.skip("docs.db fixture missing")

    config = ServerConfig(database_path=db_path)

    build_server(config)
