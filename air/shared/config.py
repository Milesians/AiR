from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shlex
import shutil

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}


def _mask(value: str, show: int = 4) -> str:
  """遮盖敏感值，显示前后若干字符"""
  if not value:
    return "(未设置)"
  if len(value) <= show * 2:
    return "***"
  return f"{value[:show]}***{value[-show:]}"


def _env_bool(key: str, default: bool) -> bool:
  """从环境变量解析布尔值"""
  raw = os.getenv(key, "").strip()
  if not raw:
    return default

  value = raw.lower()
  if value in _TRUE_VALUES:
    return True
  if value in _FALSE_VALUES:
    return False

  logger.warning("环境变量 %s=%s 不是有效布尔值，使用默认值 %s", key, raw, default)
  return default


def _env_args(key: str, default: list[str]) -> list[str]:
  """按 shell 参数规则解析环境变量"""
  raw = os.getenv(key, "").strip()
  if not raw:
    return default
  return shlex.split(raw)


def _env_url(key: str) -> str:
  """读取 URL 环境变量，并容错清理常见 .env 误写"""
  value = os.getenv(key, "").strip()
  if not value:
    return ""

  for _ in range(2):
    value = value.strip().strip(",").strip().strip("\"'")
  return value.rstrip("/")


def _resolve_project_name(work_dir: str | None) -> str:
  """解析项目名称。

  优先级：
  1. AIR_PROJECT_NAME
  2. CI_PROJECT_PATH
  3. CI_PROJECT_NAME
  4. 工作目录名
  """
  for key in ("AIR_PROJECT_NAME", "CI_PROJECT_PATH", "CI_PROJECT_NAME"):
    if value := os.getenv(key, "").strip():
      return value

  if work_dir:
    return Path(work_dir).resolve().name

  return "未知项目"


def _resolve_claude_cli_path() -> str:
  """解析 Claude CLI 路径：环境变量 > PATH 查找 > 默认路径"""
  if path := os.getenv("CLAUDE_CLI_PATH"):
    return path
  return shutil.which("claude") or "/usr/local/bin/claude"


def _resolve_jira_mcp_enabled() -> bool:
  """解析是否启用 Jira MCP。

  显式配置优先；未配置时，如果发现 Jira URL 和认证信息则自动启用。
  """
  if os.getenv("AIR_JIRA_MCP_ENABLED", "").strip():
    return _env_bool("AIR_JIRA_MCP_ENABLED", False)

  has_url = bool(os.getenv("JIRA_URL", "").strip())
  has_pat = bool(os.getenv("JIRA_PERSONAL_TOKEN", "").strip())
  has_api_token = bool(
      os.getenv("JIRA_USERNAME", "").strip()
      and os.getenv("JIRA_API_TOKEN", "").strip())
  return has_url and (has_pat or has_api_token)


def _bootstrap_anthropic_env() -> None:
  """将 OPENAI_* 环境变量映射为 Claude SDK 需要的 ANTHROPIC_*。

  仅在未显式设置 ANTHROPIC_* 时填充，原值始终优先。
  """
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


@dataclass
class AppConfig:
  """统一应用配置，从环境变量加载"""

  # 工作目录（代码仓库路径，命令行 > 环境变量）
  work_dir: str | None = field(default=None)

  # commit 数量上限，超过时降级为整体 diff 审查
  max_commits: int = field(
    default_factory=lambda: int(os.getenv("AIR_MAX_COMMITS", "10")))

  # Claude CLI 路径，None 时在 __post_init__ 中按 env > which > 默认路径解析
  claude_cli_path: str | None = field(default=None)
  claude_max_turns: int = field(
    default_factory=lambda: int(os.getenv("CLAUDE_MAX_TURNS", "30")))

  # Jira MCP。默认只读；当 JIRA_URL + 认证信息存在时自动启用。
  jira_mcp_enabled: bool = field(default_factory=_resolve_jira_mcp_enabled)
  jira_mcp_command: str = field(
    default_factory=lambda: os.getenv("AIR_JIRA_MCP_COMMAND", "uv"))
  jira_mcp_args: list[str] = field(
    default_factory=lambda: _env_args(
      "AIR_JIRA_MCP_ARGS", ["tool", "run", "mcp-atlassian"]))
  jira_mcp_read_only: bool = field(
    default_factory=lambda: _env_bool("AIR_JIRA_MCP_READ_ONLY", True))
  jira_mcp_toolsets: str = field(
    default_factory=lambda: os.getenv("AIR_JIRA_MCP_TOOLSETS", "default"))
  jira_url: str = field(default_factory=lambda: _env_url("JIRA_URL"))
  jira_personal_token: str = field(
    default_factory=lambda: os.getenv("JIRA_PERSONAL_TOKEN", ""))
  jira_username: str = field(default_factory=lambda: os.getenv("JIRA_USERNAME", ""))
  jira_api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))
  jira_ssl_verify: str = field(default_factory=lambda: os.getenv("JIRA_SSL_VERIFY", ""))
  jira_projects_filter: str = field(
    default_factory=lambda: os.getenv("JIRA_PROJECTS_FILTER", ""))

  # 钉钉
  dingtalk_webhook_url: str = field(
    default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_URL", ""))
  dingtalk_webhook_secret: str = field(
    default_factory=lambda: os.getenv("DINGTALK_WEBHOOK_SECRET", ""))

  # 联系人配置（JSON 字符串）
  contacts_json: str = field(
    default_factory=lambda: os.getenv("AIR_CONTACTS", ""))
  project_name: str = field(default="")

  def __post_init__(self) -> None:
    # 在读取/使用任何 ANTHROPIC_* 前完成兼容映射
    _bootstrap_anthropic_env()

    # 命令行未传入时，回退到环境变量
    if self.work_dir is None:
      self.work_dir = os.getenv("AIR_WORK_DIR")
    if not self.project_name:
      self.project_name = _resolve_project_name(self.work_dir)
    if not self.claude_cli_path:
      self.claude_cli_path = _resolve_claude_cli_path()

    logger.info(
        "配置加载完成：work_dir=%s, project_name=%s, max_commits=%d",
        self.work_dir or "(未设置)",
        self.project_name,
        self.max_commits,
    )
    logger.info(
        "Claude 配置：model=%s, base_url=%s, auth_token=%s, cli_path=%s, max_turns=%d",
        os.getenv("ANTHROPIC_MODEL", "(未设置)"),
        os.getenv("ANTHROPIC_BASE_URL", "(未设置)"),
        _mask(os.getenv("ANTHROPIC_AUTH_TOKEN", "")),
        self.claude_cli_path,
        self.claude_max_turns,
    )
    logger.info(
        "Jira MCP 配置：enabled=%s, url=%s, command=%s %s, read_only=%s, token=%s",
        self.jira_mcp_enabled,
        self.jira_url or "(未设置)",
        self.jira_mcp_command,
        " ".join(self.jira_mcp_args),
        self.jira_mcp_read_only,
        _mask(self.jira_personal_token or self.jira_api_token),
    )
    logger.info(
        "钉钉配置：webhook=%s, secret=%s",
        _mask(self.dingtalk_webhook_url),
        _mask(self.dingtalk_webhook_secret),
    )

  @property
  def jira_mcp_configured(self) -> bool:
    """Jira MCP 是否具备实际启动所需配置"""
    has_auth = bool(self.jira_personal_token) or bool(
      self.jira_username and self.jira_api_token)
    return self.jira_mcp_enabled and bool(self.jira_url) and has_auth
