import unittest
from unittest.mock import patch

from air.flows.code_review.reviewer import CodeReviewer, _parse_result_message
from air.shared.config import AppConfig
from claude_agent_sdk import ResultMessage


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
    async def test_stops_after_result_message(self) -> None:
        async def fake_query(*, prompt, options):
            yield _result_message(structured_output={"body": "LGTM"})
            raise AssertionError("ResultMessage 后不应继续读取")

        reviewer = CodeReviewer(AppConfig())

        with (
            patch("air.flows.code_review.reviewer.query", fake_query),
            patch.object(reviewer, "_build_options", return_value=None),
        ):
            result = await reviewer._query("prompt")

        self.assertEqual(result.body, "LGTM")


if __name__ == "__main__":
    unittest.main()
