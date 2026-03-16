import base64
import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import requests

from air.config import AppConfig
from air.data.review_result import ReviewResult
from .base import Channel

logger = logging.getLogger(__name__)


def _format_message(result: ReviewResult) -> str:
    lines = ["## Code Review 结果\n"]

    if result.summary:
        lines.append(f"{result.summary}\n")

    if result.issues:
        lines.append("### 问题列表\n")
        for issue in result.issues:
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "•")
            lines.append(f"{icon} **{issue.file_path}:{issue.line}**\n  {issue.message}\n")

    return "\n".join(lines)


def _sign_url(webhook_url: str, secret: str) -> str:
    """为钉钉 Webhook 添加加签参数"""
    timestamp = str(round(time.time() * 1000))
    sign_str = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode(), sign_str.encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    return f"{webhook_url}&{urlencode({'timestamp': timestamp, 'sign': sign})}"


class DingtalkChannel(Channel):
    """钉钉 Webhook 推送渠道"""

    def __init__(self, config: AppConfig):
        self.config = config

    def send(self, result: ReviewResult) -> bool:
        if not self.config.dingtalk_webhook_url:
            logger.warning("钉钉 Webhook URL 未配置，跳过发送")
            return False

        logger.info("准备发送钉钉通知：issues=%d, summary=%d字符", len(result.issues), len(result.summary))

        url = self.config.dingtalk_webhook_url
        if self.config.dingtalk_webhook_secret:
            logger.debug("使用签名模式构造钉钉请求 URL")
            url = _sign_url(url, self.config.dingtalk_webhook_secret)
        else:
            logger.debug("未配置签名密钥，使用原始 Webhook URL")

        content = _format_message(result)
        logger.debug("钉钉消息内容（前300字）：%s", content[:300])
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "Code Review 结果",
                "text": content
            }
        }

        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            logger.info("钉钉消息发送成功（HTTP %d）", resp.status_code)
        else:
            logger.error("钉钉消息发送失败：HTTP %d，响应=%s", resp.status_code, resp.text[:200])
        return resp.status_code == 200
