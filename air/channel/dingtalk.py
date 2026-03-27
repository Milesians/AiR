import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import requests

from air.config import AppConfig
from air.data.contacts import AtResult, parse_contacts, resolve_at
from air.data.review_result import ReviewResult
from air.target import ReviewTarget
from .base import Channel

logger = logging.getLogger(__name__)


def _format_message(result: ReviewResult, target: ReviewTarget, at: AtResult | None = None) -> str:
    lines = ["## Code Review 结果\n"]

    # 涉及的提交信息
    if target.commit_infos:
        lines.append("### 涉及提交\n")
        for ci in target.commit_infos:
            line = f"- `{ci.short_sha}` {ci.subject} — {ci.author}（{ci.date}）"
            # 在提交人后面追加 @手机号
            if at and ci.sha in at.commit_phones:
                at_text = " ".join(f"@{phone}" for phone in at.commit_phones[ci.sha])
                line = f"{line} {at_text}"
            lines.append(f"{line}\n")
        lines.append("")

    if result.summary:
        lines.append(f"{result.summary}\n")

    if result.issues:
        lines.append("### 问题列表\n")
        for issue in result.issues:
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "•")
            # 行号：支持范围显示
            if issue.end_line and issue.end_line != issue.start_line:
                location = f"{issue.file_path}:{issue.start_line}-{issue.end_line}"
            else:
                location = f"{issue.file_path}:{issue.start_line}"
            lines.append(f"{icon} **{location}**\n\n{issue.message}\n")
            if issue.original_code:
                lines.append(f"**问题代码：**\n\n{issue.original_code}\n")
            if issue.suggested_code:
                lines.append(f"**建议修改：**\n\n{issue.suggested_code}\n")

    # 没有匹配到提交人时，在末尾 @ maintainer
    if at and at.fallback_phones:
        at_text = " ".join(f"@{phone}" for phone in at.fallback_phones)
        lines.append(f"\n> 请相关维护者关注 {at_text}\n")

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

    def send(self, result: ReviewResult, target: ReviewTarget) -> bool:
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

        # 解析联系人，构建 @mention
        at_result: AtResult | None = None
        if self.config.contacts_json:
            try:
                contacts = parse_contacts(self.config.contacts_json)
                at_result = resolve_at(contacts, target.commit_infos)
                if at_result.all_phones:
                    logger.info("钉钉 @mention 手机号：%s", at_result.all_phones)
            except json.JSONDecodeError:
                logger.warning("AIR_CONTACTS 环境变量 JSON 格式无效，跳过 @mention")
        else:
            logger.warning("AIR_CONTACTS 未配置，跳过 @mention")

        content = _format_message(result, target, at_result)
        logger.debug("钉钉消息完整内容：\n%s", content)

        at_phones = at_result.all_phones if at_result else []
        payload: dict = {
            "msgtype": "markdown",
            "markdown": {
                "title": "Code Review 结果",
                "text": content
            },
            "at": {
                "atMobiles": at_phones,
                "isAtAll": False
            }
        }

        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info("钉钉消息发送成功（HTTP %d）", resp.status_code)
        else:
            logger.error("钉钉消息发送失败：HTTP %d，响应=%s", resp.status_code, resp.text[:200])
        return resp.status_code == 200
