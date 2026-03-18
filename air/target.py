import logging
import subprocess
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)

# CI_COMMIT_BEFORE_SHA 为全零表示首次 push 或 force push
_ZERO_SHA = "0" * 40


@dataclass
class CommitInfo:
    """单个 commit 的元信息"""
    sha: str  # 完整 SHA
    short_sha: str  # 短 SHA（前 8 位）
    author: str  # 提交人
    date: str  # 提交时间（ISO 格式）
    subject: str  # 提交标题


@dataclass
class ReviewTarget:
    """审查目标：一次 push 中涉及的 commit 列表"""
    commits: list[str] = field(default_factory=list)  # commit SHA 列表（从旧到新）
    before_sha: str | None = None  # push 前的 SHA（用于整体 diff 范围）
    after_sha: str = ""  # push 后的 SHA
    commit_infos: list[CommitInfo] = field(default_factory=list)  # commit 详细信息

    @staticmethod
    def from_commit(sha: str, work_dir: str | None = None) -> "ReviewTarget":
        """从单个 commit 构建审查目标"""
        _git_safe_directory(work_dir)
        logger.info("从单个 commit 构建审查目标：%s", sha)
        infos = _git_commit_infos([sha], work_dir)
        return ReviewTarget(commits=[sha], after_sha=sha, commit_infos=infos)

    @staticmethod
    def from_gitlab_ci(work_dir: str | None = None) -> "ReviewTarget":
        """从 GitLab CI 环境变量构建审查目标

        使用 CI_COMMIT_BEFORE_SHA 和 CI_COMMIT_SHA 确定 push 范围，
        通过 git log 获取 commit 列表。
        """
        _git_safe_directory(work_dir)
        after_sha = os.getenv("CI_COMMIT_SHA", "")
        before_sha = os.getenv("CI_COMMIT_BEFORE_SHA", "")

        if not after_sha:
            raise ValueError("CI_COMMIT_SHA 环境变量未设置，无法自动检测 commit 范围")

        logger.info("CI 环境检测：before=%s, after=%s", before_sha or "(未设置)", after_sha)

        # 首次 push 或 force push：before_sha 为全零或未设置
        if not before_sha or before_sha == _ZERO_SHA:
            logger.info("首次 push 或 force push，降级为单 commit 审查")
            infos = _git_commit_infos([after_sha], work_dir)
            return ReviewTarget(commits=[after_sha], after_sha=after_sha, commit_infos=infos)

        # 正常 push：获取 commit 列表
        commits = _git_log_range(before_sha, after_sha, work_dir)
        if not commits:
            logger.warning("git log 未返回 commit，降级为单 commit 审查")
            infos = _git_commit_infos([after_sha], work_dir)
            return ReviewTarget(commits=[after_sha], before_sha=before_sha, after_sha=after_sha, commit_infos=infos)

        logger.info("检测到 %d 个 commit", len(commits))
        infos = _git_commit_infos(commits, work_dir)
        return ReviewTarget(commits=commits, before_sha=before_sha, after_sha=after_sha, commit_infos=infos)


def _git_safe_directory(work_dir: str | None = None) -> None:
    """将工作目录加入 git safe.directory，解决 CI 环境中目录所有者不一致的问题"""
    target_dir = work_dir or os.getcwd()
    cmd = ["git", "config", "--global", "--add", "safe.directory", target_dir]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.debug("已将 %s 加入 git safe.directory", target_dir)
    except subprocess.CalledProcessError as e:
        logger.warning("设置 safe.directory 失败：%s", e.stderr.strip())


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


def _git_commit_infos(shas: list[str], work_dir: str | None = None) -> list[CommitInfo]:
    """通过 git log 获取 commit 的详细信息（提交人、时间、标题）"""
    if not shas:
        return []
    # 分隔符不能包含 % 后跟字母，否则会被 git format 解析
    sep = "<|>"
    fmt = sep.join(["%H", "%h", "%an", "%ai", "%s"])
    cmd = ["git", "log", f"--format={fmt}", "--no-walk", *shas]
    logger.debug("执行命令：%s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir, check=True)
        infos = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(sep)
            if len(parts) >= 5:
                infos.append(CommitInfo(
                    sha=parts[0],
                    short_sha=parts[1],
                    author=parts[2],
                    date=parts[3],
                    subject=parts[4],
                ))
        # --no-walk 不保证顺序，按传入的 shas 顺序排列
        sha_order = {sha: i for i, sha in enumerate(shas)}
        infos.sort(key=lambda c: sha_order.get(c.sha, 0))
        return infos
    except subprocess.CalledProcessError as e:
        logger.error("获取 commit 信息失败：%s", e.stderr.strip())
        return []
