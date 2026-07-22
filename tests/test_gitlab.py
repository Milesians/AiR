import hashlib
import unittest
from unittest.mock import Mock, patch

import requests

from air.flows.code_review.gitlab import (
    GitLabChannel,
    _build_line_range,
    _parse_diff_lines,
)
from air.flows.code_review.result import ReviewComment, ReviewLine, ReviewResult
from air.shared.config import AppConfig

API_URL = "https://gitlab.example.com/api/v4"
MR_URL = f"{API_URL}/projects/12/merge_requests/34"
HEADERS = {"PRIVATE-TOKEN": "secret-token"}


def _config(gitlab_token: str = "secret-token") -> AppConfig:
    return AppConfig(
        gitlab_api_url=API_URL,
        gitlab_token=gitlab_token,
        gitlab_project_id="12",
        gitlab_merge_request_iid="34",
    )


def _response(status_code: int, payload=None, text: str = "") -> Mock:
    response = Mock(status_code=status_code, text=text)
    if payload is not None:
        response.json.return_value = payload
    return response


def _versions_response() -> Mock:
    return _response(200, [{
        "id": 7,
        "base_commit_sha": "base-sha",
        "start_commit_sha": "start-sha",
        "head_commit_sha": "head-sha",
    }])


class DiffParserTest(unittest.TestCase):
    def test_parses_added_removed_context_and_multiple_hunks(self) -> None:
        file_hash = hashlib.sha1(b"app.py").hexdigest()
        lines = _parse_diff_lines(
            """@@ -10,3 +10,4 @@
 unchanged
-removed
+added one
+added two
 unchanged again
@@ -30 +31 @@
-old tail
+new tail""",
            "app.py",
        )

        self.assertEqual(
            [
                (line.old_line, line.new_line, line.hunk, line.line_code)
                for line in lines
            ],
            [
                (10, 10, 1, f"{file_hash}_10_10"),
                (11, None, 1, f"{file_hash}_11_11"),
                (None, 11, 1, f"{file_hash}_12_11"),
                (None, 12, 1, f"{file_hash}_12_12"),
                (12, 13, 1, f"{file_hash}_12_13"),
                (30, None, 2, f"{file_hash}_30_31"),
                (None, 31, 2, f"{file_hash}_31_31"),
            ],
        )

    def test_rejects_reversed_cross_file_and_unavailable_ranges(self) -> None:
        raw_diff = """@@ -1,2 +1,2 @@
 first
 second"""
        reversed_comment = ReviewComment(
            body="逆序范围",
            old_path="app.py",
            new_path="app.py",
            start_line=ReviewLine(old_line=2, new_line=2),
            end_line=ReviewLine(old_line=1, new_line=1),
        )
        missing_file_comment = reversed_comment.model_copy(update={
            "old_path": "missing.py",
            "new_path": "missing.py",
        })

        self.assertIsNone(_build_line_range(reversed_comment, [{
            "old_path": "app.py",
            "new_path": "app.py",
            "diff": raw_diff,
        }]))
        self.assertIsNone(_build_line_range(missing_file_comment, [{
            "old_path": "app.py",
            "new_path": "app.py",
            "diff": raw_diff,
        }]))
        self.assertIsNone(_build_line_range(reversed_comment, [{
            "old_path": "app.py",
            "new_path": "app.py",
            "diff": raw_diff,
            "too_large": True,
        }]))


class GitLabChannelTest(unittest.TestCase):
    def test_skips_non_merge_request_pipeline(self) -> None:
        channel = GitLabChannel(AppConfig(gitlab_merge_request_iid=""))

        with patch("air.flows.code_review.gitlab.requests.post") as post:
            ok = channel.send(ReviewResult(body="LGTM", should_notify=False))

        self.assertFalse(ok)
        post.assert_not_called()

    def test_skips_when_token_is_missing(self) -> None:
        channel = GitLabChannel(_config(gitlab_token=""))

        with patch("air.flows.code_review.gitlab.requests.post") as post:
            ok = channel.send(ReviewResult(body="发现 1 个问题"))

        self.assertFalse(ok)
        post.assert_not_called()

    def test_posts_legacy_body_to_merge_request_notes_api(self) -> None:
        channel = GitLabChannel(_config())

        with patch(
            "air.flows.code_review.gitlab.requests.post",
            return_value=_response(201),
        ) as post:
            ok = channel.send(ReviewResult(body="LGTM", should_notify=False))

        self.assertTrue(ok)
        post.assert_called_once_with(
            f"{MR_URL}/notes",
            json={
                "body": (
                    "## AiR Code Review\n\n"
                    "> 本评论由 **AiR** 自动生成并发布。GitLab 显示的评论用户仅为 "
                    "Access Token 所属账号，不代表该用户本人发布。\n\n"
                    "LGTM"
                )
            },
            headers=HEADERS,
            timeout=30,
        )

    def test_aggregates_general_comments_into_one_note(self) -> None:
        result = ReviewResult(body="完整钉钉正文", comments=[
            ReviewComment(body="整体命名不统一"),
            ReviewComment(body="模块边界不清晰"),
        ])

        with (
            patch("air.flows.code_review.gitlab.requests.get") as get,
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        get.assert_not_called()
        posted_body = post.call_args.kwargs["json"]["body"]
        self.assertIn("整体命名不统一\n\n---\n\n模块边界不清晰", posted_body)
        self.assertNotIn(result.body, posted_body)

    def test_posts_added_line_as_diff_discussion(self) -> None:
        result = ReviewResult(body="发现问题", comments=[ReviewComment(
            body="这里缺少输入校验",
            old_path="app.py",
            new_path="app.py",
            start_line=ReviewLine(new_line=18),
        )])

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                return_value=_versions_response(),
            ) as get,
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        get.assert_called_once_with(f"{MR_URL}/versions", headers=HEADERS, timeout=30)
        post.assert_called_once_with(
            f"{MR_URL}/discussions",
            json={
                "body": (
                    "> 本评论由 **AiR** 自动生成并发布。GitLab 显示的评论用户仅为 "
                    "Access Token 所属账号，不代表该用户本人发布。\n\n"
                    "这里缺少输入校验"
                ),
                "position": {
                    "position_type": "text",
                    "base_sha": "base-sha",
                    "start_sha": "start-sha",
                    "head_sha": "head-sha",
                    "old_path": "app.py",
                    "new_path": "app.py",
                    "new_line": 18,
                },
            },
            headers=HEADERS,
            timeout=30,
        )

    def test_maps_removed_and_context_lines_to_gitlab_position(self) -> None:
        result = ReviewResult(body="发现问题", comments=[
            ReviewComment(
                body="删除这一行会破坏兼容性",
                old_path="app.py",
                new_path="app.py",
                start_line=ReviewLine(old_line=7),
            ),
            ReviewComment(
                body="上下文位置的问题",
                old_path="app.py",
                new_path="app.py",
                start_line=ReviewLine(old_line=9, new_line=10),
            ),
        ])

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                return_value=_versions_response(),
            ),
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        positions = [item.kwargs["json"]["position"] for item in post.call_args_list]
        self.assertEqual(positions[0]["old_line"], 7)
        self.assertNotIn("new_line", positions[0])
        self.assertEqual(positions[1]["old_line"], 9)
        self.assertEqual(positions[1]["new_line"], 10)

    def test_posts_multiline_range_with_gitlab_line_codes(self) -> None:
        result = ReviewResult(body="发现问题", comments=[ReviewComment(
            body="这一段状态转换不完整",
            old_path="old.py",
            new_path="new.py",
            start_line=ReviewLine(old_line=11),
            end_line=ReviewLine(new_line=12),
        )])
        raw_diff = """@@ -10,3 +10,4 @@
 unchanged
-removed
+added one
+added two
 unchanged again"""
        file_hash = hashlib.sha1(b"new.py").hexdigest()

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                side_effect=[
                    _versions_response(),
                    _response(200, {"diffs": [{
                        "old_path": "old.py",
                        "new_path": "new.py",
                        "diff": raw_diff,
                        "collapsed": False,
                        "too_large": False,
                    }]}),
                ],
            ) as get,
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        self.assertEqual(get.call_count, 2)
        position = post.call_args.kwargs["json"]["position"]
        self.assertEqual(position["old_path"], "old.py")
        self.assertEqual(position["new_path"], "new.py")
        self.assertEqual(position["new_line"], 12)
        self.assertNotIn("old_line", position)
        self.assertEqual(position["line_range"], {
            "start": {
                "line_code": f"{file_hash}_11_11",
                "type": "old",
                "old_line": 11,
            },
            "end": {
                "line_code": f"{file_hash}_12_12",
                "type": "new",
                "new_line": 12,
            },
        })

    def test_downgrades_cross_hunk_range_to_note(self) -> None:
        result = ReviewResult(body="发现问题", comments=[ReviewComment(
            body="跨 hunk 问题",
            old_path="app.py",
            new_path="app.py",
            start_line=ReviewLine(old_line=1, new_line=1),
            end_line=ReviewLine(old_line=20, new_line=20),
        )])
        raw_diff = """@@ -1 +1 @@
 first
@@ -20 +20 @@
 second"""

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                side_effect=[
                    _versions_response(),
                    _response(200, {"diffs": [{
                        "old_path": "app.py",
                        "new_path": "app.py",
                        "diff": raw_diff,
                    }]}),
                ],
            ),
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], f"{MR_URL}/notes")
        body = post.call_args.kwargs["json"]["body"]
        self.assertIn("GitLab 行内定位失败，已降级为普通评论", body)
        self.assertIn("旧文件第 1 行 / 新文件第 1 行 至 旧文件第 20 行 / 新文件第 20 行", body)

    def test_downgrades_rejected_discussion_without_reposting_successes(self) -> None:
        result = ReviewResult(body="发现问题", comments=[
            ReviewComment(body="整体问题"),
            ReviewComment(
                body="成功的问题",
                old_path="a.py",
                new_path="a.py",
                start_line=ReviewLine(new_line=2),
            ),
            ReviewComment(
                body="过期的问题",
                old_path="b.py",
                new_path="b.py",
                start_line=ReviewLine(new_line=3),
            ),
        ])

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                return_value=_versions_response(),
            ),
            patch(
                "air.flows.code_review.gitlab.requests.post",
                side_effect=[_response(201), _response(400, text="line not found"), _response(201)],
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        self.assertEqual(
            [posted.args[0] for posted in post.call_args_list],
            [f"{MR_URL}/discussions", f"{MR_URL}/discussions", f"{MR_URL}/notes"],
        )
        fallback_body = post.call_args_list[2].kwargs["json"]["body"]
        self.assertIn("整体问题", fallback_body)
        self.assertIn("过期的问题", fallback_body)
        self.assertNotIn("成功的问题", fallback_body)

    def test_downgrades_when_diff_version_request_fails(self) -> None:
        result = ReviewResult(body="发现问题", comments=[ReviewComment(
            body="需要保留的问题",
            old_path="app.py",
            new_path="app.py",
            start_line=ReviewLine(new_line=2),
        )])

        with (
            patch(
                "air.flows.code_review.gitlab.requests.get",
                return_value=_response(500, text="server error"),
            ),
            patch(
                "air.flows.code_review.gitlab.requests.post",
                return_value=_response(201),
            ) as post,
        ):
            ok = GitLabChannel(_config()).send(result)

        self.assertTrue(ok)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], f"{MR_URL}/notes")
        self.assertIn("需要保留的问题", post.call_args.kwargs["json"]["body"])

    def test_returns_false_when_note_request_fails(self) -> None:
        with patch(
            "air.flows.code_review.gitlab.requests.post",
            side_effect=requests.RequestException("network error"),
        ):
            ok = GitLabChannel(_config()).send(ReviewResult(body="发现 1 个问题"))

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
