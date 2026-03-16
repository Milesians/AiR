import logging

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, \
    ThinkingConfigDisabled
from claude_agent_sdk._errors import ProcessError, MessageParseError
from claude_agent_sdk.types import SystemPromptPreset

from air.config import AppConfig
from air.data import ReviewResult
from air.target import ReviewTarget

logger = logging.getLogger(__name__)


class CodeReviewer:
    """Claude Code 代码审查器"""

    def __init__(self, config: AppConfig):
        self.config = config
        logger.debug("CodeReviewer 初始化，work_dir=%s", self.config.work_dir or "(未设置)")

    async def review_in_ci(self, target: ReviewTarget) -> ReviewResult:
        """CI 模式：Claude 用 git 命令获取变更后审查"""
        logger.info("开始 CI 模式审查：%s=%s", target.kind, target.ref)
        prompt = (
            f"你是一个代码审查员。当前处于 CI 环境，git 仓库已 checkout。\n"
            f"请使用 git 命令（如 git diff-tree / git show）获取 commit {target.ref} 的变更内容，"
            f"通过各种工具获取所需的上下文，然后对变更代码进行审查，以 JSON 格式返回审查结论。"
        )
        logger.debug("CI 模式 prompt（前200字）：%s", prompt[:200])
        return await self._query(prompt)

    async def review_in_local(self, target: ReviewTarget) -> ReviewResult:
        """本地模式：由程序拉取 GitLab diff，再交给 Claude 审查"""
        logger.info("开始本地模式审查：%s=%s", target.kind, target.ref)
        from air.source.gitlab_source import GitLabSource

        source = GitLabSource(self.config)
        diff_files = source.get_commit_diff_files(target.ref)

        if not diff_files:
            logger.info("未发现变更文件，跳过审查")
            return ReviewResult(summary="未发现变更内容，跳过审查。")

        active_files = [f for f in diff_files if not f.deleted_file]
        logger.info("获取到 %d 个变更文件，其中 %d 个有效（排除删除）", len(diff_files), len(active_files))
        logger.debug("有效变更文件列表：%s", [f.path for f in active_files])

        diff_text = "\n\n".join(
            f"### {f.path}\n```diff\n{f.diff}\n```"
            for f in active_files
        )
        prompt = (
            f"你是一个代码审查员。以下是 commit {target.ref} 的变更内容：\n\n"
            f"{diff_text}\n\n"
            f"请对以上变更代码进行审查，以 JSON 格式返回审查结论。"
        )
        logger.debug("本地模式 prompt 长度：%d 字符", len(prompt))
        return await self._query(prompt)

    async def _query(self, prompt: str) -> ReviewResult:
        """公共 query 逻辑"""
        result: ReviewResult | None = None
        message_count = 0

        logger.info("向 Claude Agent 发起审查请求...")
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    system_prompt=SystemPromptPreset(type="preset", preset="claude_code"),
                    allowed_tools=["*"],
                    permission_mode="bypassPermissions",
                    setting_sources=["user"],
                    cwd=self.config.work_dir,
                    max_turns=self.config.claude_max_turns,
                    # 禁用 extended thinking，避免代理不兼容 signature 字段
                    thinking=ThinkingConfigDisabled(type = "disabled"),
                    stderr=lambda line: logger.error("[claude stderr] %s", line),
                    output_format={
                        "type": "json_schema",
                        "schema": ReviewResult.model_json_schema(),
                    },
                ),
            ):
                message_count += 1

                logger.debug(
                    "收到消息 #%d，类型=%s，内容=%s",
                    message_count,
                    type(message).__name__,
                    getattr(message, "content", None),
                )

                if isinstance(message, ResultMessage):
                    logger.info(
                        "ResultMessage: subtype=%s, structured_output=%s",
                        message.subtype,
                        message.structured_output,
                    )
                    if message.subtype == "error_max_structured_output_retries":
                        logger.error("Claude 无法生成结构化审查结果（超过重试次数）")
                        result = ReviewResult(summary="审查失败：无法生成结构化结果。")
                    elif message.structured_output:
                        result = ReviewResult.model_validate(message.structured_output)
                        logger.info(
                            "审查完成：发现 %d 个问题，摘要长度=%d 字符",
                            len(result.issues),
                            len(result.summary),
                        )
                        logger.debug(
                            "问题明细：%s",
                            [(i.severity, i.file_path, i.line) for i in result.issues],
                        )
                    else:
                        logger.warning("ResultMessage 无 structured_output，原始消息：%s", message)
                else:
                    logger.info("非 ResultMessage 消息，完整内容：%s", message)
        except ProcessError as e:
            logger.error("Claude CLI 进程异常退出：%s", e)
            raise
        except MessageParseError as e:
            logger.error("Claude 响应解析失败（可能是版本不兼容）：%s", e)
            raise
        except Exception as e:
            # 捕获所有其他异常，包括 API 错误（401/403/502等）
            logger.error(
                "审查过程中发生错误：type=%s, message=%s, attrs=%s",
                type(e).__name__,
                e,
                {k: getattr(e, k, None) for k in ["status_code", "code", "body", "response"]},
                exc_info=True,
            )
            raise

        logger.info("Claude Agent 响应结束，共收到 %d 条消息", message_count)

        if result is None:
            logger.warning("未收到结构化审查结果，返回默认结果")
        return result or ReviewResult(summary="审查完成，但未收到结构化结果。")