import unittest
from unittest.mock import AsyncMock, patch

from air.flows.code_review.cli import run
from air.flows.code_review.result import ReviewResult
from air.flows.code_review.target import ReviewTarget
from air.shared.config import AppConfig


class RunTest(unittest.IsolatedAsyncioTestCase):
    async def test_posts_lgtm_to_gitlab_without_sending_dingtalk(self) -> None:
        config = AppConfig(gitlab_merge_request_iid="34")
        target = ReviewTarget(after_sha="abc123")

        with (
            patch("air.flows.code_review.cli.CodeReviewer") as reviewer_class,
            patch("air.flows.code_review.cli.GitLabChannel") as gitlab_class,
            patch("air.flows.code_review.cli.DingtalkChannel") as dingtalk_class,
        ):
            reviewer_class.return_value.review = AsyncMock(
                return_value=ReviewResult(body="LGTM", should_notify=False)
            )
            gitlab_class.return_value.send.return_value = True

            await run(target, config)

        gitlab_class.return_value.send.assert_called_once()
        dingtalk_class.return_value.send.assert_not_called()

    async def test_sends_result_to_gitlab_and_dingtalk(self) -> None:
        config = AppConfig(gitlab_merge_request_iid="34")
        target = ReviewTarget(after_sha="abc123")

        with (
            patch("air.flows.code_review.cli.CodeReviewer") as reviewer_class,
            patch("air.flows.code_review.cli.GitLabChannel") as gitlab_class,
            patch("air.flows.code_review.cli.DingtalkChannel") as dingtalk_class,
        ):
            result = ReviewResult(body="发现 1 个问题", should_notify=True)
            reviewer_class.return_value.review = AsyncMock(return_value=result)
            gitlab_class.return_value.send.return_value = False
            dingtalk_class.return_value.send.return_value = True

            await run(target, config)

        gitlab_class.return_value.send.assert_called_once_with(result)
        dingtalk_class.return_value.send.assert_called_once_with(result, target)


if __name__ == "__main__":
    unittest.main()
