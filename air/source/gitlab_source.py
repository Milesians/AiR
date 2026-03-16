import logging
from dataclasses import dataclass
from typing import List

import gitlab

from air.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class DiffFile:
    """变更文件信息"""
    path: str
    old_path: str
    new_file: bool
    deleted_file: bool
    diff: str


class GitLabSource:
    """GitLab Commit Diff 数据源（备用，暂不调用）"""

    def __init__(self, config: AppConfig):
        self.config = config
        auth_mode = "private_token" if config.gitlab_private_token else "job_token"
        logger.info("连接 GitLab：url=%s, project_id=%s, 认证方式=%s", config.gitlab_url, config.gitlab_project_id, auth_mode)
        if config.gitlab_private_token:
            self._gl = gitlab.Gitlab(url=config.gitlab_url, private_token=config.gitlab_private_token)
        else:
            self._gl = gitlab.Gitlab(url=config.gitlab_url, job_token=config.gitlab_job_token)

    def get_commit_diff_files(self, commit_sha: str) -> List[DiffFile]:
        """获取单个 commit 的变更文件"""
        logger.info("获取 commit diff：sha=%s", commit_sha)
        project = self._gl.projects.get(self.config.gitlab_project_id)
        logger.debug("GitLab 项目信息：id=%s", self.config.gitlab_project_id)

        diffs = project.commits.get(commit_sha).diff()
        files = [
            DiffFile(
                path=item["new_path"],
                old_path=item["old_path"],
                new_file=item["new_file"],
                deleted_file=item["deleted_file"],
                diff=item["diff"],
            )
            for item in diffs
        ]
        logger.info("获取到 %d 个变更文件（commit=%s）", len(files), commit_sha)
        logger.debug("变更文件列表：%s", [(f.path, "new" if f.new_file else "deleted" if f.deleted_file else "modified") for f in files])
        return files

    def get_diff_file_paths(self, commit_sha: str) -> List[str]:
        """获取变更文件路径（排除删除文件）"""
        paths = [f.path for f in self.get_commit_diff_files(commit_sha) if not f.deleted_file]
        logger.debug("有效变更路径（排除删除）：%s", paths)
        return paths
