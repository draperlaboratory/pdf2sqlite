from __future__ import annotations

import argparse
import sys

from .config import ServerConfig
from .server import build_server

_TRANSPORTS = {"stdio", "sse", "streamable-http"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdf2sqlite-mcp",
        description="Expose pdf2sqlite databases over the Model Context Protocol",
    )
    parser.add_argument(
        "-d",
        "--database",
        help="Path to the sqlite database produced by pdf2sqlite",
    )
    parser.add_argument(
        "--max-blob-bytes",
        type=int,
        help="Maximum blob size the server will return (bytes)",
    )
    parser.add_argument(
        "--default-limit",
        type=int,
        help="Default limit for listing queries",
    )
    parser.add_argument(
        "--max-limit",
        type=int,
        help="Maximum limit for listing queries",
    )
    parser.add_argument(
        "--transport",
        choices=sorted(_TRANSPORTS),
        default="stdio",
        help="Transport to use when running the server",
    )
    parser.add_argument(
        "--host",
        help="Host name for SSE or HTTP transports",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port for SSE or HTTP transports",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    try:
        config = ServerConfig.from_cli(
            database=args.database,
            max_blob_bytes=args.max_blob_bytes,
            default_limit=args.default_limit,
            max_limit=args.max_limit,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    fastmcp_kwargs: dict[str, object] = {}
    if args.host:
        fastmcp_kwargs["host"] = args.host
    if args.port:
        fastmcp_kwargs["port"] = args.port

    server = build_server(config, **fastmcp_kwargs)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
