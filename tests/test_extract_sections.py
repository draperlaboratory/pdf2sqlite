from __future__ import annotations

from pdf2sqlite.extract_sections import extract_toc_and_sections


class DummyConsole:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message: str) -> None:
        self.messages.append(message)


class DummyLive:
    def __init__(self) -> None:
        self.console = DummyConsole()


class FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class FakeReader:
    def __init__(self, texts: list[str]) -> None:
        self.pages = [FakePage(text) for text in texts]
        self.outline: list[object] = []


def test_extract_sections_uses_page_fallback_when_outline_missing():
    live = DummyLive()
    reader = FakeReader([
        "First page contents",
        "",
        "Third page contents",
    ])

    result = extract_toc_and_sections(reader, live)

    assert result["has_toc"] is False
    assert set(result["sections"].keys()) == {"page_1", "page_3"}
    assert (
        result["sections"]["page_1"]["text"].strip() == "First page contents"
    )
    assert (
        result["sections"]["page_3"]["text"].strip() == "Third page contents"
    )
    assert any(
        "Using page-based sections" in message
        for message in live.console.messages
    )
