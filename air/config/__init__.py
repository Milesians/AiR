from dataclasses import dataclass, field
import logging
import os

logger = logging.getLogger(__name__)


# 处理环境变量
if url := os.environ.get("OPENAI_BASE_URL"):
  os.environ.setdefault("ANTHROPIC_BASE_URL", url)

if key := os.environ.get("OPENAI_API_KEY"):
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

  # 工作目录（代码仓库路径，命令行 > 环境变量）
  work_dir: str | None = field(default=None)

  # commit 数量上限，超过时降级为整体 diff 审查
  max_commits: int = field(
    default_factory=lambda: int(os.getenv("AIR_MAX_COMMITS", "10")))

  # Claude
  claude_cli_path: str | None = field(
    default_factory=lambda: os.getenv("CLAUDE_CLI_PATH"))
  claude_max_turns: int = field(
    default_factory=lambda: int(os.getenv("CLAUDE_MAX_TURNS", "30")))

  # 钉钉
  dingtalk_webhook_url: str = field(
    default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_URL", ""))
  dingtalk_webhook_secret: str = field(
    default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_SECRET", ""))

  def __post_init__(self) -> None:
    # 命令行未传入时，回退到环境变量
    if self.work_dir is None:
      self.work_dir = os.getenv("AIR_WORK_DIR")

    logger.info(
        "配置加载完成：work_dir=%s, max_commits=%d",
        self.work_dir or "(未设置)",
        self.max_commits,
    )
    logger.debug(
        "敏感配置摘要：dingtalk_webhook=%s, dingtalk_secret=%s",
        _mask(self.dingtalk_webhook_url),
        _mask(self.dingtalk_webhook_secret),
    )
