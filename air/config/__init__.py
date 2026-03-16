from dataclasses import dataclass, field
import logging
import os

logger = logging.getLogger(__name__)

if url := os.environ.get("OPENAI_BASE_URL"):
  os.environ.setdefault("ANTHROPIC_BASE_URL", url)

if key := os.environ.get("OPENAI_API_KEY") :
  os.environ.setdefault("ANTHROPIC_AUTH_TOKEN", key)

if model := os.environ.get("OPENAI_MODEL"):
  os.environ.setdefault("ANTHROPIC_MODEL", model)
  os.environ.setdefault("ANTHROPIC_REASONING_MODEL", model)
  os.environ.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", model)
  os.environ.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", model)
  os.environ.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", model)


def _mask(value: str, show: int = 4) -> str:
    """遮盖敏感值，仅显示末尾若干字符"""
    if not value:
        return "(未设置)"
    return f"***{value[-show:]}" if len(value) > show else "***"


@dataclass
class AppConfig:
    """统一应用配置，从环境变量加载"""

    # 工作目录（代码仓库路径，CI 环境由 CLAUDE_WORK_DIR 注入）
    work_dir: str = field(default_factory=lambda: os.getenv("CLAUDE_WORK_DIR", None))

    # GitLab
    gitlab_url: str = field(default_factory=lambda: os.getenv("GITLAB_URL", ""))
    gitlab_project_id: str = field(default_factory=lambda: os.getenv("CI_PROJECT_ID", ""))
    gitlab_job_token: str = field(default_factory=lambda: os.getenv("CI_JOB_TOKEN", ""))
    gitlab_private_token: str = field(default_factory=lambda: os.getenv("GITLAB_PRIVATE_TOKEN", ""))

    # Claude
    claude_max_turns: int = field(default_factory=lambda: int(os.getenv("CLAUDE_MAX_TURNS", "25")))

    # 钉钉
    dingtalk_webhook_url: str = field(default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_URL", ""))
    dingtalk_webhook_secret: str = field(default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_SECRET", ""))

    def __post_init__(self) -> None:
        logger.info(
            "配置加载完成：is_ci=%s, work_dir=%s, gitlab_url=%s, project_id=%s",
            self.is_ci,
            self.work_dir or "(未设置)",
            self.gitlab_url or "(未设置)",
            self.gitlab_project_id or "(未设置)",
        )
        logger.debug(
            "敏感配置摘要：job_token=%s, private_token=%s, dingtalk_webhook=%s, dingtalk_secret=%s",
            _mask(self.gitlab_job_token),
            _mask(self.gitlab_private_token),
            _mask(self.dingtalk_webhook_url),
            _mask(self.dingtalk_webhook_secret),
        )

    @property
    def is_ci(self) -> bool:
        """是否在 CI 环境（通过 CI_JOB_TOKEN 判断）"""
        return bool(self.gitlab_job_token)