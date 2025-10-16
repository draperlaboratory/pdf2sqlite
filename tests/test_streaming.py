from __future__ import annotations

from collections.abc import Iterable

from pdf2sqlite.streaming import accumulate_streaming_text


class DummyDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class DummyChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = DummyDelta(content)


class DummyChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [DummyChoice(content)]


def iter_chunks(contents: Iterable[str | None]) -> Iterable[DummyChunk]:
    for value in contents:
        yield DummyChunk(value)


def test_accumulate_streaming_text_collects_chunks() -> None:
    updates: list[str] = []

    def on_update(current: str) -> None:
        updates.append(current)

    result = accumulate_streaming_text(
        iter_chunks(["Hello", " ", "world"]),
        on_update,
    )

    assert result == "Hello world"
    assert updates == ["Hello", "Hello ", "Hello world"]


def test_accumulate_streaming_text_ignores_missing_content() -> None:
    updates: list[str] = []

    def on_update(current: str) -> None:
        updates.append(current)

    result = accumulate_streaming_text(
        iter_chunks(["alpha", None, "beta"]),
        on_update,
    )

    assert result == "alphabeta"
    assert updates == ["alpha", "alpha", "alphabeta"]


def test_accumulate_streaming_text_handles_bad_chunks() -> None:
    updates: list[str] = []

    def on_update(current: str) -> None:
        updates.append(current)

    class BadChunk:
        pass

    chunk_sequence = [DummyChunk("fine"), BadChunk(), DummyChunk("!")]

    result = accumulate_streaming_text(chunk_sequence, on_update)

    assert result == "fine!"
    assert updates == ["fine", "fine", "fine!"]
