from __future__ import annotations

import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from fiona.cli import main


class FionaCliHelpTests(unittest.TestCase):
    def _run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = 0
        with patch.object(sys, "argv", ["fiona", *args]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                main()
            except SystemExit as exc:
                code = int(exc.code or 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_top_level_help_shows_fiona_grid(self) -> None:
        code, stdout, stderr = self._run_cli("--help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Fiona umbrella CLI", stdout)
        self.assertIn("fiona quiktieper ...", stdout)
        self.assertIn("seeondesk", stdout)
        self.assertIn("dataclient", stdout)
        self.assertIn("action", stdout)
        self.assertIn("voice", stdout)
        self.assertIn("macro", stdout)
        self.assertIn("recall", stdout)
        self.assertIn("fat", stdout)
        self.assertIn("cli", stdout)
        self.assertIn("phiconnect", stdout)

    def test_seeondesk_help_shows_awareness_commands(self) -> None:
        code, stdout, stderr = self._run_cli("seeondesk", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona seeondesk", stdout)
        self.assertIn("active", stdout)
        self.assertIn("status", stdout)

    def test_dataclient_help_shows_miner_commands(self) -> None:
        code, stdout, stderr = self._run_cli("dataclient", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona dataclient", stdout)
        self.assertIn("mine", stdout)
        self.assertIn("deep", stdout)
        self.assertIn("convert", stdout)
        self.assertIn("view", stdout)
        self.assertIn("gui", stdout)

    def test_fat_help_shows_terminal_assistance_commands(self) -> None:
        code, stdout, stderr = self._run_cli("fat", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona fat", stdout)
        self.assertIn("status", stdout)
        self.assertIn("layout", stdout)
        self.assertIn("run", stdout)

    def test_action_help_shows_router_commands(self) -> None:
        code, stdout, stderr = self._run_cli("action", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona action", stdout)
        self.assertIn("list", stdout)
        self.assertIn("run", stdout)
        self.assertIn("history", stdout)

    def test_voice_help_shows_translation_commands(self) -> None:
        code, stdout, stderr = self._run_cli("voice", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona voice", stdout)
        self.assertIn("parse", stdout)
        self.assertIn("run", stdout)

    def test_macro_help_shows_macro_commands(self) -> None:
        code, stdout, stderr = self._run_cli("macro", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona macro", stdout)
        self.assertIn("list", stdout)
        self.assertIn("save", stdout)
        self.assertIn("run", stdout)

    def test_recall_help_shows_remembrance_commands(self) -> None:
        code, stdout, stderr = self._run_cli("recall", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona recall", stdout)
        self.assertIn("list", stdout)
        self.assertIn("search", stdout)
        self.assertIn("remember", stdout)

    def test_cli_help_shows_terminal_command_center(self) -> None:
        code, stdout, stderr = self._run_cli("cli", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona cli", stdout)
        self.assertIn("--preview", stdout)

    def test_help_word_maps_to_top_level_help(self) -> None:
        code, stdout, _stderr = self._run_cli("help")

        self.assertEqual(code, 0)
        self.assertIn("Command groups:", stdout)

    def test_layer_help_word_maps_to_layer_help(self) -> None:
        code, stdout, stderr = self._run_cli("host", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("usage: fiona host", stdout)
        self.assertIn("install-service", stdout)

    def test_quiktieper_help_stays_under_quiktieper(self) -> None:
        code, stdout, stderr = self._run_cli("quiktieper", "help")

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Launch apps and focused-app shortcuts", stdout)
        self.assertIn("normalize-app-cmds", stdout)


if __name__ == "__main__":
    unittest.main()
