from __future__ import annotations

from typing import cast
from rich.live import Live
from pdf2sqlite.task_stack import TaskStack
from pdf2sqlite.view import fresh_view, task_view


class DummyLive:
    def __init__(self) -> None:
        self.updates: list[object] = []

    def update(self, value: object) -> None:
        self.updates.append(value)


def test_task_stack_push_pop_updates_live():
    live = DummyLive()
    stack = TaskStack(cast(Live,live), "Document")

    assert stack.snapshot() == []

    stack.push("task-1")
    assert stack.snapshot() == ["task-1"]

    stack.update_current("task-1b")
    assert stack.snapshot() == ["task-1b"]

    stack.pop()
    assert stack.snapshot() == []

    assert len(live.updates) == 3


def test_task_stack_step_context_manager():
    live = DummyLive()
    stack = TaskStack(cast(Live, live), "Doc")

    with stack.step("outer"):
        assert stack.snapshot() == ["outer"]
        with stack.step("inner"):
            assert stack.snapshot() == ["outer", "inner"]
        assert stack.snapshot() == ["outer"]

    assert stack.snapshot() == []


def test_task_view_does_not_share_default_task_list():
    first_tree = task_view("Doc", ["task"])
    second_tree = task_view("Doc")

    assert len(first_tree.children) == 1
    assert len(second_tree.children) == 0


def test_update_current_populates_empty_stack():
    live = DummyLive()
    stack = TaskStack(cast(Live, live), "Doc")

    stack.update_current("task")
    assert stack.snapshot() == ["task"]


def test_fresh_view_returns_empty_tree():
    tree = fresh_view()

    assert tree.label == ""
    assert not tree.children
