from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Sequence, TYPE_CHECKING

from .view import task_view

if TYPE_CHECKING:  # pragma: no cover
    from rich.live import Live


class TaskStack:
    def __init__(self, live: Live, title: str):
        self._live = live
        self._title = title
        self._items: list[Any] = []

    @contextmanager
    def step(self, label: Any):
        self.push(label)
        try:
            yield
        finally:
            self.pop()

    def push(self, label: Any) -> None:
        self._items.append(label)
        self._refresh()

    def pop(self) -> None:
        if self._items:
            self._items.pop()
            self._refresh()

    def update_current(self, label: Any) -> None:
        if self._items:
            self._items[-1] = label
        else:
            self._items.append(label)
        self._refresh()

    def snapshot(self) -> list[Any]:
        return list(self._items)

    def render(self, extra: Sequence[Any] | None = None) -> None:
        tasks = self.snapshot()
        if extra:
            tasks.extend(extra)
        self._live.update(task_view(self._title, tasks))

    def _refresh(self) -> None:
        self._live.update(task_view(self._title, self.snapshot()))
