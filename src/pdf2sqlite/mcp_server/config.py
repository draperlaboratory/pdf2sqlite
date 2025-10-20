from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

DEFAULT_MAX_BLOB_BYTES = 10 * 1024 * 1024
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(slots=True)
class ServerConfig:
    database_path: Path
    max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES
    default_limit: int = DEFAULT_LIMIT
    max_limit: int = MAX_LIMIT

    @classmethod
    def from_cli(
        cls,
        database: str | None,
        max_blob_bytes: int | None = None,
        default_limit: int | None = None,
        max_limit: int | None = None,
    ) -> "ServerConfig":
        db_path = database or os.getenv("PDF2SQLITE_MCP_DATABASE")
        if not db_path:
            raise ValueError(
                "A database path must be provided via --database or the "
                "PDF2SQLITE_MCP_DATABASE environment variable"
            )

        resolved = Path(db_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Database not found: {resolved}")

        blob_limit = max_blob_bytes or int(
            os.getenv("PDF2SQLITE_MCP_MAX_BLOB_BYTES", DEFAULT_MAX_BLOB_BYTES)
        )
        if blob_limit <= 0:
            raise ValueError("max blob size must be a positive integer")

        default_lim = default_limit or int(
            os.getenv("PDF2SQLITE_MCP_DEFAULT_LIMIT", DEFAULT_LIMIT)
        )
        max_lim = max_limit or int(os.getenv("PDF2SQLITE_MCP_MAX_LIMIT", MAX_LIMIT))

        if default_lim <= 0:
            raise ValueError("default limit must be positive")
        if max_lim <= 0:
            raise ValueError("max limit must be positive")
        if default_lim > max_lim:
            raise ValueError("default limit cannot exceed max limit")

        return cls(
            database_path=resolved,
            max_blob_bytes=blob_limit,
            default_limit=default_lim,
            max_limit=max_lim,
        )

    def clamp_limit(self, value: int | None) -> int:
        target = value or self.default_limit
        if target <= 0:
            raise ValueError("limit must be positive")
        if target > self.max_limit:
            raise ValueError(
                f"limit {target} exceeds configured max of {self.max_limit}"
            )
        return target
