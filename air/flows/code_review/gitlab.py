import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from air.flows.code_review.result import ReviewComment, ReviewLine, ReviewResult
from air.shared.config import AppConfig

logger = logging.getLogger(__name__)

_HUNK_RE = re.compile(
    r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@"
)
_AI_NOTICE = (
    "> 本评论由 **AiR** 自动生成并发布。GitLab 显示的评论用户仅为 "
    "Access Token 所属账号，不代表该用户本人发布。"
)


@dataclass(frozen=True)
class _DiffRefs:
    version_id: str | int
    base_sha: str
    start_sha: str
    head_sha: str


@dataclass(frozen=True)
class _DiffLine:
    old_line: int | None
    new_line: int | None
    line_type: str
    hunk: int
    index: int
    line_code: str


def _parse_diff_lines(diff: str, file_path: str) -> list[_DiffLine]:
    """解析 GitLab unified diff，保留生成 line_code 所需的双侧游标。"""
    file_hash = hashlib.sha1(file_path.encode()).hexdigest()
    lines: list[_DiffLine] = []
    old_position = 0
    new_position = 0
    hunk = 0
    in_hunk = False

    for raw_line in diff.splitlines():
        if match := _HUNK_RE.match(raw_line):
            old_position = int(match.group("old"))
            new_position = int(match.group("new"))
            hunk += 1
            in_hunk = True
            continue

        if not in_hunk or raw_line.startswith("\\"):
            continue

        prefix = raw_line[:1]
        line_old_position = old_position
        line_new_position = new_position
        if prefix == "+":
            old_line = None
            new_line = new_position
            line_type = "new"
            new_position += 1
        elif prefix == "-":
            old_line = old_position
            new_line = None
            line_type = "old"
            old_position += 1
        elif prefix == " ":
            old_line = old_position
            new_line = new_position
            line_type = "old"
            old_position += 1
            new_position += 1
        else:
            continue

        lines.append(_DiffLine(
            old_line=old_line,
            new_line=new_line,
            line_type=line_type,
            hunk=hunk,
            index=len(lines),
            line_code=f"{file_hash}_{line_old_position}_{line_new_position}",
        ))

    return lines


def _find_diff_line(lines: list[_DiffLine], target: ReviewLine) -> _DiffLine | None:
    return next((
        line for line in lines
        if line.old_line == target.old_line and line.new_line == target.new_line
    ), None)


def _line_payload(line: _DiffLine) -> dict[str, object]:
    payload: dict[str, object] = {
        "line_code": line.line_code,
        "type": line.line_type,
    }
    if line.old_line is not None:
        payload["old_line"] = line.old_line
    if line.new_line is not None:
        payload["new_line"] = line.new_line
    return payload


def _build_line_range(
    comment: ReviewComment,
    diffs: list[dict[str, Any]],
) -> dict[str, dict[str, object]] | None:
    """验证多行范围并构造 GitLab line_range。"""
    if not comment.is_multiline or comment.start_line is None or comment.end_line is None:
        return None

    diff_file = next((
        item for item in diffs
        if item.get("old_path") == comment.old_path
        and item.get("new_path") == comment.new_path
    ), None)
    if not diff_file or diff_file.get("collapsed") or diff_file.get("too_large"):
        return None

    raw_diff = diff_file.get("diff")
    if not isinstance(raw_diff, str) or not raw_diff:
        return None

    lines = _parse_diff_lines(raw_diff, comment.new_path or "")
    start = _find_diff_line(lines, comment.start_line)
    end = _find_diff_line(lines, comment.end_line)
    if start is None or end is None:
        return None
    if start.hunk != end.hunk or start.index >= end.index:
        return None

    return {
        "start": _line_payload(start),
        "end": _line_payload(end),
    }


def _review_line_payload(line: ReviewLine) -> dict[str, int]:
    payload: dict[str, int] = {}
    if line.old_line is not None:
        payload["old_line"] = line.old_line
    if line.new_line is not None:
        payload["new_line"] = line.new_line
    return payload


def _format_note(body: str) -> str:
    return f"## AiR Code Review\n\n{_AI_NOTICE}\n\n{body}"


def _format_discussion(body: str) -> str:
    return f"{_AI_NOTICE}\n\n{body}"


def _format_review_line(line: ReviewLine) -> str:
    parts: list[str] = []
    if line.old_line is not None:
        parts.append(f"旧文件第 {line.old_line} 行")
    if line.new_line is not None:
        parts.append(f"新文件第 {line.new_line} 行")
    return " / ".join(parts)


def _format_fallback(comment: ReviewComment) -> str:
    if comment.start_line is None:
        return comment.body

    if comment.old_path == comment.new_path:
        path = f"`{comment.new_path}`"
    else:
        path = f"`{comment.old_path}` -> `{comment.new_path}`"

    location = _format_review_line(comment.start_line)
    if comment.is_multiline and comment.end_line is not None:
        location = f"{location} 至 {_format_review_line(comment.end_line)}"

    return (
        f"{comment.body}\n\n"
        f"> GitLab 行内定位失败，已降级为普通评论。原定位：{path}，{location}。"
    )


class GitLabChannel:
    """GitLab Merge Request 评论推送渠道"""

    def __init__(self, config: AppConfig):
        self.config = config

    @property
    def _merge_request_url(self) -> str:
        return (
            f"{self.config.gitlab_api_url}/projects/{self.config.gitlab_project_id}"
            f"/merge_requests/{self.config.gitlab_merge_request_iid}"
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.config.gitlab_token}

    def send(self, result: ReviewResult) -> bool:
        if not self.config.gitlab_merge_request_iid:
            logger.info("当前不是 Merge Request Pipeline，跳过 GitLab 评论")
            return False

        if not all((
            self.config.gitlab_api_url,
            self.config.gitlab_token,
            self.config.gitlab_project_id,
        )):
            logger.warning("GitLab MR 评论配置不完整，跳过发送")
            return False

        if not result.comments:
            return self._post_note(result.body)

        general_comments = [comment.body for comment in result.comments if not comment.is_inline]
        inline_comments = [comment for comment in result.comments if comment.is_inline]
        fallback_comments: list[str] = []

        if inline_comments:
            refs = self._get_latest_diff_refs()
            if refs is None:
                fallback_comments.extend(_format_fallback(comment) for comment in inline_comments)
            else:
                diffs: list[dict[str, Any]] | None = None
                if any(comment.is_multiline for comment in inline_comments):
                    diffs = self._get_version_diffs(refs.version_id)

                for comment in inline_comments:
                    position = self._build_position(comment, refs, diffs)
                    if position is None or not self._post_discussion(comment.body, position):
                        fallback_comments.append(_format_fallback(comment))

        note_sections = [*general_comments, *fallback_comments]
        if note_sections:
            return self._post_note("\n\n---\n\n".join(note_sections))

        return True

    def _build_position(
        self,
        comment: ReviewComment,
        refs: _DiffRefs,
        diffs: list[dict[str, Any]] | None,
    ) -> dict[str, object] | None:
        if comment.start_line is None:
            return None

        anchor = comment.end_line if comment.is_multiline else comment.start_line
        if anchor is None:
            return None

        position: dict[str, object] = {
            "position_type": "text",
            "base_sha": refs.base_sha,
            "start_sha": refs.start_sha,
            "head_sha": refs.head_sha,
            "old_path": comment.old_path,
            "new_path": comment.new_path,
            **_review_line_payload(anchor),
        }

        if comment.is_multiline:
            if diffs is None:
                logger.warning("GitLab MR diff 内容不可用，多行评论降级")
                return None
            line_range = _build_line_range(comment, diffs)
            if line_range is None:
                logger.warning(
                    "GitLab 多行评论定位无效，准备降级：old_path=%s, new_path=%s",
                    comment.old_path,
                    comment.new_path,
                )
                return None
            position["line_range"] = line_range

        return position

    def _get_latest_diff_refs(self) -> _DiffRefs | None:
        payload = self._get_json(f"{self._merge_request_url}/versions", "MR diff version")
        if payload is None:
            return None
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            logger.error("GitLab MR diff version 响应格式无效")
            return None

        latest = payload[0]
        version_id = latest.get("id")
        base_sha = latest.get("base_commit_sha")
        start_sha = latest.get("start_commit_sha")
        head_sha = latest.get("head_commit_sha")
        if (
            not isinstance(version_id, (str, int))
            or not isinstance(base_sha, str)
            or not isinstance(start_sha, str)
            or not isinstance(head_sha, str)
            or not all((base_sha, start_sha, head_sha))
        ):
            logger.error("GitLab MR diff version 缺少必要字段")
            return None

        return _DiffRefs(version_id, base_sha, start_sha, head_sha)

    def _get_version_diffs(self, version_id: str | int) -> list[dict[str, Any]] | None:
        payload = self._get_json(
            f"{self._merge_request_url}/versions/{version_id}",
            "MR diff 内容",
        )
        if payload is None:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("diffs"), list):
            logger.error("GitLab MR diff 内容响应格式无效")
            return None
        return [item for item in payload["diffs"] if isinstance(item, dict)]

    def _get_json(self, url: str, description: str) -> object | None:
        try:
            response = requests.get(url, headers=self._headers, timeout=30)
        except requests.RequestException as exc:
            logger.error("GitLab %s获取失败：%s", description, exc)
            return None

        if not 200 <= response.status_code < 300:
            logger.error(
                "GitLab %s获取失败：HTTP %d，响应=%s",
                description,
                response.status_code,
                str(response.text)[:200],
            )
            return None

        try:
            return response.json()
        except ValueError:
            logger.error("GitLab %s响应不是有效 JSON", description)
            return None

    def _post_discussion(self, body: str, position: dict[str, object]) -> bool:
        logger.info(
            "准备发布 GitLab MR 行内评论：old_path=%s, new_path=%s",
            position.get("old_path"),
            position.get("new_path"),
        )
        return self._post_json(
            f"{self._merge_request_url}/discussions",
            {"body": _format_discussion(body), "position": position},
            "MR 行内评论",
        )

    def _post_note(self, body: str) -> bool:
        formatted_body = _format_note(body)
        logger.info("准备发布 GitLab MR 普通评论：body=%d字符", len(formatted_body))
        return self._post_json(
            f"{self._merge_request_url}/notes",
            {"body": formatted_body},
            "MR 普通评论",
        )

    def _post_json(self, url: str, payload: dict[str, Any], description: str) -> bool:
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.error("GitLab %s发送失败：%s", description, exc)
            return False

        if 200 <= response.status_code < 300:
            logger.info("GitLab %s发送成功（HTTP %d）", description, response.status_code)
            return True

        logger.error(
            "GitLab %s发送失败：HTTP %d，响应=%s",
            description,
            response.status_code,
            str(response.text)[:200],
        )
        return False
