"""Tests for the ActionRegistry and ActionHandler base."""

from __future__ import annotations

import unittest
from typing import Any

from fiona.actions import ActionHandler, ActionRegistry


class _EchoHandler(ActionHandler):
    """Test handler that returns params as JSON."""

    @property
    def name(self) -> str:
        return "echo"

    def execute(self, params: dict[str, Any]) -> str:
        import json
        return json.dumps(params, sort_keys=True)


class _GreetHandler(ActionHandler):
    """Test handler that greets."""

    @property
    def name(self) -> str:
        return "greet"

    def execute(self, params: dict[str, Any]) -> str:
        name = params.get("name", "world")
        return f"Hello, {name}!"


class TestActionHandler(unittest.TestCase):
    """ActionHandler ABC contract."""

    def test_name_property(self) -> None:
        handler = _EchoHandler()
        self.assertEqual(handler.name, "echo")

    def test_execute(self) -> None:
        handler = _EchoHandler()
        result = handler.execute({"key": "value"})
        self.assertIn('"key"', result)

    def test_default_to_tool_spec(self) -> None:
        handler = _EchoHandler()
        spec = handler.to_tool_spec()
        self.assertEqual(spec["function"]["name"], "echo")
        self.assertIn("parameters", spec["function"])


class TestActionRegistry(unittest.TestCase):
    """ActionRegistry registration, lookup, and default loading."""

    def setUp(self) -> None:
        self.registry = ActionRegistry()

    def test_register_and_lookup(self) -> None:
        handler = _GreetHandler()
        self.registry.register("greet", handler)
        self.assertIs(self.registry.lookup("greet"), handler)

    def test_lookup_missing(self) -> None:
        self.assertIsNone(self.registry.lookup("nonexistent"))

    def test_run(self) -> None:
        self.registry.register("greet", _GreetHandler())
        result = self.registry.run("greet", {"name": "Fiona"})
        self.assertEqual(result, "Hello, Fiona!")

    def test_run_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.run("nonexistent", {})

    def test_contains(self) -> None:
        self.registry.register("greet", _GreetHandler())
        self.assertIn("greet", self.registry)
        self.assertNotIn("missing", self.registry)

    def test_len(self) -> None:
        # Includes any defaults loaded (api_search, api_info, api_categories)
        before = len(self.registry)
        self.registry.register("greet", _GreetHandler())
        self.assertEqual(len(self.registry), before + 1)

    def test_list_actions(self) -> None:
        self.registry.register("echo", _EchoHandler())
        specs = self.registry.list_actions()
        names = [s["function"]["name"] for s in specs]
        self.assertIn("echo", names)

    def test_double_register_overwrites(self) -> None:
        self.registry.register("greet", _GreetHandler())
        self.registry.register("greet", _EchoHandler())
        self.assertIsInstance(self.registry.lookup("greet"), _EchoHandler)

    def test_thread_safety(self) -> None:
        """Register from multiple threads — should not lose entries."""
        import threading

        errors: list[Exception] = []

        def register_some() -> None:
            try:
                for i in range(20):
                    h = _EchoHandler()
                    self.registry.register(f"t{i}", h)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_some) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        # At least 20 handlers from one of the threads survived
        handler_count = sum(
            1 for k in self.registry._handlers if k.startswith("t")
        )
        self.assertGreaterEqual(handler_count, 20)


if __name__ == "__main__":
    unittest.main()
