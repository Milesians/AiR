import unittest
from unittest.mock import Mock, patch

import requests

from air.flows.code_review.gitlab import GitLabChannel
from air.flows.code_review.result import ReviewResult
from air.shared.config import AppConfig


class GitLabChannelTest(unittest.TestCase):
    def test_skips_non_merge_request_pipeline(self) -> None:
        channel = GitLabChannel(AppConfig(gitlab_merge_request_iid=""))

        with patch("air.flows.code_review.gitlab.requests.post") as post:
            ok = channel.send(ReviewResult(body="LGTM", should_notify=False))

        self.assertFalse(ok)
        post.assert_not_called()

    def test_skips_when_token_is_missing(self) -> None:
        channel = GitLabChannel(AppConfig(
            gitlab_api_url="https://gitlab.example.com/api/v4",
            gitlab_project_id="12",
            gitlab_merge_request_iid="34",
        ))

        with patch("air.flows.code_review.gitlab.requests.post") as post:
            ok = channel.send(ReviewResult(body="发现 1 个问题"))

        self.assertFalse(ok)
        post.assert_not_called()

    def test_posts_review_body_to_merge_request_notes_api(self) -> None:
        channel = GitLabChannel(AppConfig(
            gitlab_api_url="https://gitlab.example.com/api/v4",
            gitlab_token="secret-token",
            gitlab_project_id="12",
            gitlab_merge_request_iid="34",
        ))
        response = Mock(status_code=201)

        with patch(
            "air.flows.code_review.gitlab.requests.post",
            return_value=response,
        ) as post:
            ok = channel.send(ReviewResult(body="LGTM", should_notify=False))

        self.assertTrue(ok)
        post.assert_called_once_with(
            "https://gitlab.example.com/api/v4/projects/12/merge_requests/34/notes",
            json={
                "body": (
                    "## AiR Code Review\n\n"
                    "> 本评论由 **AiR** 自动生成并发布。GitLab 显示的评论用户仅为 "
                    "Access Token 所属账号，不代表该用户本人发布。\n\n"
                    "LGTM"
                )
            },
            headers={"PRIVATE-TOKEN": "secret-token"},
            timeout=30,
        )

    def test_returns_false_when_request_fails(self) -> None:
        channel = GitLabChannel(AppConfig(
            gitlab_api_url="https://gitlab.example.com/api/v4",
            gitlab_token="secret-token",
            gitlab_project_id="12",
            gitlab_merge_request_iid="34",
        ))

        with patch(
            "air.flows.code_review.gitlab.requests.post",
            side_effect=requests.RequestException("network error"),
        ):
            ok = channel.send(ReviewResult(body="发现 1 个问题"))

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
