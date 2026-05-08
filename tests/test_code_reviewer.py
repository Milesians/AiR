import os
import unittest
from typing import cast
from unittest.mock import patch

from air.flows.code_review.reviewer import CodeReviewer, _parse_result_message
from air.flows.code_review.result import ReviewResult
from air.flows.code_review.target import CommitInfo, ReviewTarget
from air.shared.config import AppConfig
from claude_agent_sdk import ResultMessage
from claude_agent_sdk.types import McpStdioServerConfig


def _result_message(**kwargs) -> ResultMessage:
    defaults = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 0,
        "is_error": False,
        "num_turns": 1,
        "session_id": "test-session",
    }
    defaults.update(kwargs)
    return ResultMessage(**defaults)


class ParseResultMessageTest(unittest.TestCase):
    def test_uses_plain_result_when_structured_output_missing(self) -> None:
        result = _parse_result_message(_result_message(result="## 结论\n\nLGTM"))

        self.assertEqual(result.body, "## 结论\n\nLGTM")

    def test_reports_error_result_details(self) -> None:
        result = _parse_result_message(
            _result_message(
                subtype="error_during_execution",
                is_error=True,
                errors=["Command failed with exit code 1"],
            )
        )

        self.assertEqual(result.body, "审查失败：Command failed with exit code 1")


class CodeReviewerQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_drains_messages_after_result_message(self) -> None:
        drained = False

        async def fake_query(*, prompt, options):
            nonlocal drained
            yield _result_message(structured_output={"body": "LGTM"})
            drained = True

        reviewer = CodeReviewer(AppConfig())

        with (
            patch("air.flows.code_review.reviewer.query", fake_query),
            patch.object(reviewer, "_build_options", return_value=None),
        ):
            result = await reviewer._query("prompt")

        self.assertEqual(result.body, "LGTM")
        self.assertTrue(drained)

    async def test_adds_jira_instruction_to_prompt_when_enabled(self) -> None:
        captured: dict[str, str] = {}

        async def fake_query(prompt: str) -> ReviewResult:
            captured["prompt"] = prompt
            return ReviewResult(body="LGTM")

        target = ReviewTarget(
            commits=["abc123"],
            after_sha="abc123",
            commit_infos=[
                CommitInfo(
                    sha="abc123",
                    short_sha="abc123",
                    author="张三",
                    email="zhangsan@example.com",
                    date="2026-04-10 10:00:00 +0800",
                    subject="AMA-123 修复订单同步",
                )
            ],
        )
        reviewer = CodeReviewer(AppConfig(
            jira_mcp_enabled=True,
            jira_url="http://jira.example.com",
            jira_personal_token="secret-token",
        ))

        with patch.object(reviewer, "_query", fake_query):
            result = await reviewer.review(target)

        self.assertEqual(result.body, "LGTM")
        self.assertIn("Jira 工单上下文", captured["prompt"])
        self.assertIn("AMA-123", captured["prompt"])

    async def test_does_not_add_jira_instruction_without_env_config(self) -> None:
        captured: dict[str, str] = {}

        async def fake_query(prompt: str) -> ReviewResult:
            captured["prompt"] = prompt
            return ReviewResult(body="LGTM")

        target = ReviewTarget(commits=["abc123"], after_sha="abc123")

        with patch.dict(os.environ, {}, clear=True):
            reviewer = CodeReviewer(AppConfig())
            with patch.object(reviewer, "_query", fake_query):
                result = await reviewer.review(target)

        self.assertEqual(result.body, "LGTM")
        self.assertNotIn("Jira 工单上下文", captured["prompt"])


class CodeReviewerMcpTest(unittest.TestCase):
    def test_builds_read_only_jira_mcp_server(self) -> None:
        config = AppConfig(
            jira_mcp_enabled=True,
            jira_url="http://jira.example.com",
            jira_personal_token="secret-token",
        )
        reviewer = CodeReviewer(config)

        servers = reviewer._build_mcp_servers()

        self.assertIn("mcp-atlassian", servers)
        server = cast(McpStdioServerConfig, servers["mcp-atlassian"])
        env = server.get("env")
        if env is None:
            self.fail("Jira MCP server 应包含 env 配置")

        self.assertEqual(server["command"], "uv")
        self.assertEqual(server.get("args"), ["tool", "run", "mcp-atlassian"])
        self.assertEqual(env["JIRA_URL"], "http://jira.example.com")
        self.assertEqual(env["JIRA_PERSONAL_TOKEN"], "secret-token")
        self.assertEqual(env["READ_ONLY_MODE"], "true")
        self.assertEqual(env["TOOLSETS"], "default")


if __name__ == "__main__":
    unittest.main()
