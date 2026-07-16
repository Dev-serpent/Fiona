from __future__ import annotations

import unittest

from EyeControl import EyeTrackerConfig, dependency_status


class EyeControlTests(unittest.TestCase):
    def test_dependency_status_is_safe_without_camera(self) -> None:
        status = dependency_status()

        self.assertIn("ready", status)
        self.assertTrue(status["requires_camera"])
        self.assertIn("cv2", status["dependencies"])
        self.assertIn("mediapipe", status["dependencies"])


if __name__ == "__main__":
    unittest.main()
