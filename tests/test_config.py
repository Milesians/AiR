import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from air.shared.config import AppConfig, _resolve_project_name


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

    def test_auto_enables_jira_mcp_for_server_pat(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": "http://jira.example.com",
                "JIRA_PERSONAL_TOKEN": "secret-token",
            },
            clear=True,
        ):
            config = AppConfig()

        self.assertTrue(config.jira_mcp_enabled)
        self.assertEqual(config.jira_mcp_command, "uv")
        self.assertEqual(config.jira_mcp_args, ["tool", "run", "mcp-atlassian"])

    def test_can_disable_jira_mcp_explicitly(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AIR_JIRA_MCP_ENABLED": "false",
                "JIRA_URL": "http://jira.example.com",
                "JIRA_PERSONAL_TOKEN": "secret-token",
            },
            clear=True,
        ):
            config = AppConfig()

        self.assertFalse(config.jira_mcp_enabled)

    def test_parses_custom_jira_mcp_args(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AIR_JIRA_MCP_ENABLED": "true",
                "AIR_JIRA_MCP_COMMAND": "uvx",
                "AIR_JIRA_MCP_ARGS": "--python=3.13 mcp-atlassian",
            },
            clear=True,
        ):
            config = AppConfig()

        self.assertEqual(config.jira_mcp_command, "uvx")
        self.assertEqual(config.jira_mcp_args, ["--python=3.13", "mcp-atlassian"])

    def test_cleans_mistyped_jira_url(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JIRA_URL": 'http://jira.example.com:8080",',
                "JIRA_PERSONAL_TOKEN": "secret-token",
            },
            clear=True,
        ):
            config = AppConfig()

        self.assertEqual(config.jira_url, "http://jira.example.com:8080")


if __name__ == "__main__":
    unittest.main()
