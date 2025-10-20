from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

from .config import ServerConfig
from .db import Database
from .resources import ResourceService, register_resources
from .tools import ToolSuite

_SERVER_NAME = "pdf2sqlite-mcp"
_INSTRUCTIONS = (
    "Use list_pdfs to discover documents, list_pdf_pages to enumerate pages, "
    "and list_page_assets to locate figures and tables. Fetch binaries via the "
    "pdf2sqlite:// resource URIs, using get_image or get_pdf when inline "
    "delivery is required."
)


def build_server(config: ServerConfig, **fastmcp_kwargs) -> FastMCP:
    server = FastMCP(
        name=_SERVER_NAME,
        instructions=_INSTRUCTIONS,
        website_url="https://github.com/draperlaboratory/pdf2sqlite",
        icons=[Icon(src="https://www.svgrepo.com/show/530449/database.svg")],
        **fastmcp_kwargs,
    )

    database = Database(config.database_path)
    resources = ResourceService(database=database, config=config)

    register_resources(server, resources)

    tools = ToolSuite(
        server=server,
        database=database,
        resources=resources,
        config=config,
    )
    tools.register()

    return server
