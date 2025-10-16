from __future__ import annotations

from pdf2sqlite.task_stack import TaskStack
from pdf2sqlite.view import task_view


class DummyLive:
    def __init__(self) -> None:
        self.updates: list[object] = []

    def update(self, value: object) -> None:
        self.updates.append(value)


def test_task_stack_push_pop_updates_live():
    live = DummyLive()
    stack = TaskStack(live, "Document")

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
    stack = TaskStack(live, "Doc")

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
