import logging
import subprocess
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)

# CI_COMMIT_BEFORE_SHA 为全零表示首次 push 或 force push
_ZERO_SHA = "0" * 40


@dataclass
class ReviewTarget:
    """审查目标：一次 push 中涉及的 commit 列表"""
    commits: list[str] = field(default_factory=list)  # commit SHA 列表（从旧到新）
    before_sha: str | None = None  # push 前的 SHA（用于整体 diff 范围）
    after_sha: str = ""  # push 后的 SHA

    @staticmethod
    def from_commit(sha: str) -> "ReviewTarget":
        """从单个 commit 构建审查目标"""
        logger.info("从单个 commit 构建审查目标：%s", sha)
        return ReviewTarget(commits=[sha], after_sha=sha)

    @staticmethod
    def from_gitlab_ci(work_dir: str | None = None) -> "ReviewTarget":
        """从 GitLab CI 环境变量构建审查目标

        使用 CI_COMMIT_BEFORE_SHA 和 CI_COMMIT_SHA 确定 push 范围，
        通过 git log 获取 commit 列表。
        """
        after_sha = os.getenv("CI_COMMIT_SHA", "")
        before_sha = os.getenv("CI_COMMIT_BEFORE_SHA", "")

        if not after_sha:
            raise ValueError("CI_COMMIT_SHA 环境变量未设置，无法自动检测 commit 范围")

        logger.info("CI 环境检测：before=%s, after=%s", before_sha or "(未设置)", after_sha)

        # 首次 push 或 force push：before_sha 为全零或未设置
        if not before_sha or before_sha == _ZERO_SHA:
            logger.info("首次 push 或 force push，降级为单 commit 审查")
            return ReviewTarget(commits=[after_sha], after_sha=after_sha)

        # 正常 push：获取 commit 列表
        commits = _git_log_range(before_sha, after_sha, work_dir)
        if not commits:
            logger.warning("git log 未返回 commit，降级为单 commit 审查")
            return ReviewTarget(commits=[after_sha], before_sha=before_sha, after_sha=after_sha)

        logger.info("检测到 %d 个 commit", len(commits))
        return ReviewTarget(commits=commits, before_sha=before_sha, after_sha=after_sha)


def _git_log_range(before_sha: str, after_sha: str, work_dir: str | None = None) -> list[str]:
    """通过 git log 获取两个 SHA 之间的 commit 列表（从旧到新）"""
    cmd = ["git", "log", "--format=%H", "--reverse", f"{before_sha}..{after_sha}"]
    logger.debug("执行命令：%s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir, check=True)
        commits = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        return commits
    except subprocess.CalledProcessError as e:
        logger.error("git log 失败：%s", e.stderr.strip())
        return []
