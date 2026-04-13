import logging

from air.config import AppConfig
from air.data import ReviewResult
from air.prompts import load_prompt
from air.target import ReviewTarget
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, \
    ThinkingConfigDisabled
from claude_agent_sdk._errors import ProcessError, MessageParseError
from claude_agent_sdk.types import SystemPromptPreset

logger = logging.getLogger(__name__)


def _parse_result_message(message: ResultMessage) -> ReviewResult:
    """解析 ResultMessage 为 ReviewResult"""
    if message.subtype == "error_max_structured_output_retries":
        logger.error("Claude 无法生成结构化结果（超过重试次数）")
        return ReviewResult(body="审查失败：无法生成结构化结果。")

    if not message.structured_output:
        logger.warning("ResultMessage 无 structured_output")
        return ReviewResult(body="审查完成，但结果为空。")

    result = ReviewResult.model_validate(message.structured_output)
    logger.info("审查完成：正文 %d 字符", len(result.body))
    return result


class CodeReviewer:
    """Claude Code 代码审查器"""

    def __init__(self, config: AppConfig):
        self.config: AppConfig = config
        logger.debug("CodeReviewer 初始化，work_dir=%s", self.config.work_dir or "(未设置)")

    async def review(self, target: ReviewTarget) -> ReviewResult:
        """统一审查入口：根据 commit 数量选择审查策略"""
        commit_count = len(target.commits)
        logger.info("开始审查：%d 个 commit", commit_count)

        if commit_count > self.config.max_commits:
            # 降级为整体 diff 审查
            logger.info("commit 数量（%d）超过上限（%d），降级为整体 diff 审查",
                        commit_count, self.config.max_commits)
            prompt = load_prompt("review_diff").format(
                before_sha=target.before_sha,
                after_sha=target.after_sha,
            )
        else:
            # 正常：传 commit 列表，Claude 自行 git 查看
            commits_str = "\n".join(f"- {sha}" for sha in target.commits)
            prompt = load_prompt("review_commits").format(
                commit_count=commit_count,
                commits=commits_str,
            )

        return await self._query(prompt)

    async def _query(self, prompt: str) -> ReviewResult:
        """公共 query 逻辑"""
        result: ReviewResult | None = None

        try:
            async for message in query(prompt=prompt,
                                       options=self._build_options()):
                logger.info("收到[%s]消息：\n %s", type(message).__name__,
                            message)

                if not isinstance(message, ResultMessage):
                    continue

                usage = message.usage or {}
                logger.info("Usage 原始数据：%s", usage)
                logger.info(
                    "审查统计：cost=$%.4f, turns=%d, duration=%dms (api=%dms)",
                    message.total_cost_usd or 0,
                    message.num_turns,
                    message.duration_ms,
                    message.duration_api_ms,
                )

                result = _parse_result_message(message)

            if result is None:
                return ReviewResult(body="审查完成，但未收到结果。")

            return result
        except (ProcessError, MessageParseError) as e:
            logger.error("Claude 调用失败：%s", e)
            raise
        except Exception as e:
            logger.error("审查异常：%s - %s", type(e).__name__, e, exc_info=True)
            raise


    def _build_options(self) -> ClaudeAgentOptions:
        """构建 Claude Agent 配置"""
        return ClaudeAgentOptions(
            cli_path=self.config.claude_cli_path,
            system_prompt=SystemPromptPreset(type="preset", preset="claude_code"),
            allowed_tools=["*"],
            permission_mode="bypassPermissions",
            setting_sources=["user"],
            cwd=self.config.work_dir,
            max_turns=self.config.claude_max_turns,
            thinking=ThinkingConfigDisabled(type="disabled"),
            stderr=lambda line: logger.error("[claude stderr] %s", line),
            output_format={
                "type": "json_schema",
                "schema": ReviewResult.model_json_schema(),
            },
            env={
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DO_NOT_TRACK": "1",
            },
        )
