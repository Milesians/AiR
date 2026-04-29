import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from air.shared.config import _resolve_project_name


class AppConfigTest(unittest.TestCase):
    def test_prefers_ci_project_path(self) -> None:
        with patch.dict(
            os.environ,
            {"CI_PROJECT_PATH": "group/demo-service", "CI_PROJECT_NAME": "demo-service"},
            clear=False,
        ):
            self.assertEqual(_resolve_project_name("/tmp/ignored"), "group/demo-service")

    def test_falls_back_to_work_dir_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="air-review-") as temp_dir:
            expected = Path(temp_dir).resolve().name
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(_resolve_project_name(temp_dir), expected)


if __name__ == "__main__":
    unittest.main()
