import unittest
import subprocess
import json
import sys
import os
from pathlib import Path

class FionaCliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env_dir = Path("tests/testing_env")
        self.env_dir.mkdir(parents=True, exist_ok=True)
        self.python = sys.executable
        self.cli_base = [self.python, "-m", "fiona.cli"]

    def _run_cmd(self, args):
        result = subprocess.run(
            self.cli_base + args,
            capture_output=True,
            text=True,
            check=False
        )
        return result

    def test_api_command_returns_valid_json(self):
        result = self._run_cmd(["api"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("hostname", data)
            self.assertIn("cpu_usage", data)
            self.assertIn("mouse_x", data)
        except json.JSONDecodeError:
            self.fail("fiona api did not return valid JSON")

    def test_fat_status_json_returns_valid_json(self):
        result = self._run_cmd(["fat", "status", "--json"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("mem", data)
            self.assertIn("os", data)
        except json.JSONDecodeError:
            self.fail("fiona fat status --json did not return valid JSON")

    def test_action_list_returns_valid_json(self):
        result = self._run_cmd(["action", "list"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("actions", data)
            self.assertIsInstance(data["actions"], list)
        except json.JSONDecodeError:
            self.fail("fiona action list did not return valid JSON")

    def test_macro_list_returns_valid_json(self):
        result = self._run_cmd(["macro", "list"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("macros", data)
        except json.JSONDecodeError:
            self.fail("fiona macro list did not return valid JSON")

    def test_recall_list_returns_valid_json(self):
        # Use a temporary recall path in testing_env
        recall_path = self.env_dir / "test_recall.json"
        result = self._run_cmd(["recall", "list", "--path", str(recall_path)])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("entries", data)
        except json.JSONDecodeError:
            self.fail("fiona recall list did not return valid JSON")

    def test_camcoms_paths_returns_paths(self):
        result = self._run_cmd(["camcoms", "paths"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("camcoms_dir", data)
            self.assertIn("host_private", data)
        except json.JSONDecodeError:
            self.fail("fiona camcoms paths did not return valid JSON")

    def test_seeondesk_status_returns_json(self):
        result = self._run_cmd(["seeondesk", "status"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("session_type", data)
            self.assertIn("active_window", data)
        except json.JSONDecodeError:
            self.fail("fiona seeondesk status did not return valid JSON")

    def test_agent_status_returns_json(self):
        result = self._run_cmd(["agent", "status"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("base_url", data)
            self.assertIn("available", data)
            # Should have either 'models' (if running) or 'available': False (if not)
            self.assertTrue("models" in data or data.get("available") is False)
        except json.JSONDecodeError:
            self.fail("fiona agent status did not return valid JSON")

    # ── Extended CLI integration tests ─────────────────────────────────

    def test_list_macros_returns_macros_dict(self):
        """macro subcommand returns a dict of macros."""
        result = self._run_cmd(["macro", "list"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("macros", data)
        except json.JSONDecodeError:
            self.fail("macro list did not return valid JSON")

    def test_discover_actions_returns_actions(self):
        """--discover-actions returns available actions."""
        result = self._run_cmd(["action", "list"])
        self.assertEqual(result.returncode, 0)
        try:
            data = json.loads(result.stdout)
            self.assertIn("actions", data)
            actions = data["actions"]
            self.assertIsInstance(actions, list)
            if actions:
                self.assertIn("name", actions[0])
                self.assertIn("description", actions[0])
        except json.JSONDecodeError:
            self.fail("action list did not return valid JSON")

    def test_voice_wake_test_graceful(self):
        """--voice wake-test returns gracefully (no crash) without hardware."""
        result = self._run_cmd(["voice", "wake-test"])
        # Should not crash — may return non-zero or zero, but must not
        # produce a traceback in stderr or stdout
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)
        # The command should complete without signal death
        self.assertGreaterEqual(result.returncode, 0)

    def test_tray_only_graceful(self):
        """--tray-only runs and exits gracefully (no crash when display missing)."""
        result = self._run_cmd(["--tray-only"])
        # When run headless, it should not crash with a traceback.
        # It may exit with an error if display/tray unavailable, but no traceback.
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)
        self.assertGreaterEqual(result.returncode, 0)

    def test_camcoms_fingerprint_returns_fingerprint(self):
        """camcoms fingerprint returns a fingerprint string (text output)."""
        result = self._run_cmd(["camcoms", "fingerprint"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Fingerprint:", result.stdout)
        self.assertIn("(no identity)", result.stdout)

    def test_camcoms_fingerprint_with_custom_identity(self):
        """camcoms fingerprint works with a temp identity file (--identity flag)."""
        import tempfile
        import json as _json
        from CamComs import CamComsIdentity
        identity = CamComsIdentity.generate("test_cli_device")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        ) as tmp:
            _json.dump(identity.to_private_dict(), tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            tmp_path = tmp.name

        try:
            result = self._run_cmd([
                "camcoms", "fingerprint",
                "--identity", tmp_path,
            ])
            self.assertEqual(result.returncode, 0)
            self.assertIn("Fingerprint:", result.stdout)
            self.assertNotIn("(no identity)", result.stdout)
        finally:
            os.unlink(tmp_path)

if __name__ == "__main__":
    unittest.main()
