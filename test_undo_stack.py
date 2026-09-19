"""Regression tests for ui/undo_stack.py (Semantic YT Studio 2.0 — Phase 2)."""

from __future__ import annotations

import unittest

from ui.undo_stack import Command, UndoStack


class TestUndoStack(unittest.TestCase):
    def test_push_runs_do_by_default(self):
        state = {"x": 0}
        stack = UndoStack()
        stack.push(Command("inc", do=lambda: state.__setitem__("x", 1), undo=lambda: state.__setitem__("x", 0)))
        self.assertEqual(state["x"], 1)

    def test_push_with_run_false_does_not_reapply(self):
        state = {"x": 5}
        stack = UndoStack()
        stack.push(
            Command("noop", do=lambda: state.__setitem__("x", 999), undo=lambda: None),
            run=False,
        )
        self.assertEqual(state["x"], 5)

    def test_undo_reverses_last_command(self):
        state = {"x": 0}
        stack = UndoStack()
        stack.push(Command("inc", do=lambda: state.__setitem__("x", state["x"] + 1), undo=lambda: state.__setitem__("x", state["x"] - 1)))
        stack.undo()
        self.assertEqual(state["x"], 0)

    def test_redo_reapplies_undone_command(self):
        state = {"x": 0}
        stack = UndoStack()
        stack.push(Command("inc", do=lambda: state.__setitem__("x", state["x"] + 1), undo=lambda: state.__setitem__("x", state["x"] - 1)))
        stack.undo()
        stack.redo()
        self.assertEqual(state["x"], 1)

    def test_new_push_after_undo_clears_redo(self):
        stack = UndoStack()
        log = []
        stack.push(Command("a", do=lambda: log.append("a"), undo=lambda: log.remove("a")))
        stack.undo()
        stack.push(Command("b", do=lambda: log.append("b"), undo=lambda: log.remove("b")))
        self.assertFalse(stack.can_redo())
        self.assertEqual(log, ["b"])

    def test_can_undo_redo_flags(self):
        stack = UndoStack()
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())
        stack.push(Command("a", do=lambda: None, undo=lambda: None))
        self.assertTrue(stack.can_undo())
        stack.undo()
        self.assertTrue(stack.can_redo())

    def test_undo_on_empty_stack_returns_none(self):
        stack = UndoStack()
        self.assertIsNone(stack.undo())

    def test_redo_on_empty_stack_returns_none(self):
        stack = UndoStack()
        self.assertIsNone(stack.redo())

    def test_max_depth_evicts_oldest(self):
        stack = UndoStack(max_depth=2)
        log = []
        for i in range(3):
            stack.push(Command(str(i), do=lambda i=i: log.append(i), undo=lambda i=i: None))
        stack.undo()
        stack.undo()
        # Only the last 2 pushes should be undoable — the first push
        # ("0") should have been evicted, so a third undo is a no-op.
        self.assertIsNone(stack.undo())

    def test_on_change_callback_fires_on_push_undo_redo(self):
        stack = UndoStack()
        calls = []
        stack.bind_on_change(lambda: calls.append(1))
        stack.push(Command("a", do=lambda: None, undo=lambda: None))
        stack.undo()
        stack.redo()
        self.assertEqual(len(calls), 3)

    def test_on_change_exception_is_swallowed(self):
        stack = UndoStack()
        stack.bind_on_change(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        # Must not raise even though the callback blows up.
        stack.push(Command("a", do=lambda: None, undo=lambda: None))

    def test_clear_empties_both_stacks(self):
        stack = UndoStack()
        stack.push(Command("a", do=lambda: None, undo=lambda: None))
        stack.undo()
        stack.clear()
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())


if __name__ == "__main__":
    unittest.main()
