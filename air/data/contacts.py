import json
import logging
import re

from dataclasses import dataclass, field
from air.target import CommitInfo

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    """联系人信息"""
    name: str  # 显示名称
    email: str
    phone: str
    regex: str  # 匹配提交信息/提交人/提交人邮箱的正则
    role: str  # maintainer / developer


@dataclass
class AtResult:
    """@mention 解析结果"""
    # 每个 commit SHA 对应匹配到的手机号列表
    commit_phones: dict[str, list[str]] = field(default_factory=dict)
    # 未匹配时 fallback 到 maintainer 的手机号列表
    fallback_phones: list[str] = field(default_factory=list)

    @property
    def all_phones(self) -> list[str]:
        """所有需要 @mention 的手机号（去重），用于 at.atMobiles"""
        phones: set[str] = set()
        for pl in self.commit_phones.values():
            phones.update(pl)
        phones.update(self.fallback_phones)
        return list(phones)


def parse_contacts(raw: str) -> list[Contact]:
    """从 JSON 字符串解析联系人列表"""
    data = json.loads(raw)
    users = data.get("users", [])
    return [
        Contact(
            name=u.get("name", ""),
            email=u.get("email", ""),
            phone=u.get("phone", ""),
            regex=u.get("regex", ""),
            role=u.get("role", ""),
        )
        for u in users
    ]


def resolve_at(contacts: list[Contact], commit_infos: list[CommitInfo]) -> AtResult:
    """根据提交信息匹配联系人，返回 @mention 结果

    匹配逻辑：
    - 遍历每个 commit，用联系人的 regex 匹配提交标题、提交人、提交人邮箱
    - 匹配到则记录到 commit_phones（commit SHA -> 手机号列表）
    - 如果所有 commit 都没有匹配到任何人，fallback_phones 填充所有 maintainer 手机号
    """
    result = AtResult()
    any_matched = False

    for ci in commit_infos:
        phones: list[str] = []
        for contact in contacts:
            if not contact.regex or not contact.phone:
                continue
            try:
                pattern = re.compile(contact.regex)
            except re.error:
                logger.warning("联系人正则表达式无效：%s", contact.regex)
                continue
            if pattern.search(ci.subject) or pattern.search(ci.author) or pattern.search(ci.email):
                if contact.phone not in phones:
                    phones.append(contact.phone)
        if phones:
            result.commit_phones[ci.sha] = phones
            any_matched = True

    if not any_matched:
        result.fallback_phones = [c.phone for c in contacts if c.role == "maintainer" and c.phone]

    return result
