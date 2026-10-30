"""CI runs the tests with unittest, which finds no test_ functions written for pytest. `adopt(globals())` at the end of such a file
turns each module-level test_ function into a TestCase method, and a `monkeypatch` argument (setattr on an object or a dotted name)
is supplied, undone after the test."""
import inspect
import unittest
from unittest import mock


class _Monkey:
    def __init__(self):
        self._patches = []

    def setattr(self, target, value_or_name, value=None, raising=True):
        if isinstance(target, str):
            p = mock.patch(target, value_or_name)
        else:
            p = mock.patch.object(target, value_or_name, value)
        p.start()
        self._patches.append(p)

    def undo(self):
        for p in reversed(self._patches):
            p.stop()


def adopt(ns: dict, name: str = "AsUnittest") -> None:
    cls = type(name, (unittest.TestCase,), {})
    for n, f in list(ns.items()):
        if not (n.startswith("test_") and inspect.isfunction(f)):
            continue
        wants_mp = "monkeypatch" in inspect.signature(f).parameters

        def run(self, f=f, wants_mp=wants_mp):
            mp = _Monkey()
            try:
                f(mp) if wants_mp else f()
            finally:
                mp.undo()
        setattr(cls, n, run)
    ns[name] = cls
