from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def accumulate_streaming_text(
    chunks: Iterable[Any],
    on_update: Callable[[str], None],
) -> str:
    """Accumulate streamed completion chunks and surface incremental text."""

    text = ""
    for chunk in chunks:
        try:
            content_piece = chunk.choices[0].delta.content or ""
        except (AttributeError, IndexError, KeyError, TypeError):
            content_piece = ""
        text += content_piece
        on_update(text)
    return text
