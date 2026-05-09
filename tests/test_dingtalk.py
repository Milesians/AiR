import unittest
from unittest.mock import Mock, patch

from air.flows.code_review.dingtalk import DingtalkChannel, _extract_title, _format_message
from air.flows.code_review.contacts import AtResult
from air.flows.code_review.result import ReviewResult
from air.flows.code_review.target import CommitInfo, ReviewTarget
from air.shared.config import AppConfig


class DingtalkMessageFormatTest(unittest.TestCase):
    def test_extracts_title_from_agent_body(self) -> None:
        title = _extract_title("## 结论\n\nLGTM")

        self.assertEqual(title, "结论")

    def test_keeps_commit_prefix_and_agent_body(self) -> None:
        target = ReviewTarget(
            commits=["abc123456789"],
            after_sha="abc123456789",
            commit_infos=[
                CommitInfo(
                    sha="abc123456789",
                    short_sha="abc12345",
                    author="张三",
                    email="zhangsan@example.com",
                    date="2026-04-10 10:00:00 +0800",
                    subject="放宽 review 正文格式",
                )
            ],
        )
        result = ReviewResult(
            body="## 结论\n\n需要关注 1 个问题。\n\n### 建议\n\n- 将正文改为直接透传。"
        )
        at = AtResult(commit_phones={"abc123456789": ["13800138000"]})

        message = _format_message(result, target, "group/AiR", at)

        self.assertIn("### 项目", message)
        self.assertIn("`group/AiR`", message)
        self.assertIn("### 涉及提交", message)
        self.assertIn(
            "- `abc12345` 放宽 review 正文格式 — 张三（2026-04-10 10:00:00 +0800） @13800138000",
            message,
        )
        self.assertIn(result.body, message)
        self.assertNotIn("### 问题列表", message)

    def test_appends_fallback_maintainer_mention(self) -> None:
        target = ReviewTarget(after_sha="abc123456789")
        result = ReviewResult(body="LGTM")
        at = AtResult(fallback_phones=["13900139000"])

        message = _format_message(result, target, "group/AiR", at)

        self.assertEqual(message, "### 项目\n\n`group/AiR`\n\nLGTM\n\n> 请相关维护者关注 @13900139000")

    def test_skips_dingtalk_send_when_llm_says_not_worth_notifying(self) -> None:
        channel = DingtalkChannel(
            AppConfig(dingtalk_webhook_url="https://example.com/webhook")
        )
        target = ReviewTarget(after_sha="abc123456789")
        result = ReviewResult(body="LGTM", should_notify=False)

        with patch("air.flows.code_review.dingtalk.requests.post") as post:
            ok = channel.send(result, target)

        self.assertFalse(ok)
        post.assert_not_called()

    def test_sends_dingtalk_when_llm_says_notification_is_needed(self) -> None:
        channel = DingtalkChannel(
            AppConfig(dingtalk_webhook_url="https://example.com/webhook")
        )
        target = ReviewTarget(after_sha="abc123456789")
        result = ReviewResult(body="发现 1 个问题", should_notify=True)
        response = Mock(status_code=200)

        with patch("air.flows.code_review.dingtalk.requests.post", return_value=response) as post:
            ok = channel.send(result, target)

        self.assertTrue(ok)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
