import logging

import requests

from air.flows.code_review.result import ReviewResult
from air.shared.config import AppConfig

logger = logging.getLogger(__name__)


class GitLabChannel:
    """GitLab Merge Request 评论推送渠道"""

    def __init__(self, config: AppConfig):
        self.config = config

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

        url = (
            f"{self.config.gitlab_api_url}/projects/{self.config.gitlab_project_id}"
            f"/merge_requests/{self.config.gitlab_merge_request_iid}/notes"
        )
        body = (
            "## AiR Code Review\n\n"
            "> 本评论由 **AiR** 自动生成并发布。GitLab 显示的评论用户仅为 "
            "Access Token 所属账号，不代表该用户本人发布。\n\n"
            f"{result.body}"
        )
        logger.info(
            "准备发布 GitLab MR 评论：project_id=%s, merge_request_iid=%s, body=%d字符",
            self.config.gitlab_project_id,
            self.config.gitlab_merge_request_iid,
            len(body),
        )

        try:
            response = requests.post(
                url,
                json={"body": body},
                headers={"PRIVATE-TOKEN": self.config.gitlab_token},
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.error("GitLab MR 评论发送失败：%s", exc)
            return False

        if 200 <= response.status_code < 300:
            logger.info("GitLab MR 评论发送成功（HTTP %d）", response.status_code)
            return True

        logger.error(
            "GitLab MR 评论发送失败：HTTP %d，响应=%s",
            response.status_code,
            response.text[:200],
        )
        return False
