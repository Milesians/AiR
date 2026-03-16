import logging

from dotenv import load_dotenv

load_dotenv()

from air.config import AppConfig
from air.target import ReviewTarget
from air.agent import CodeReviewer
from air.channel import DingtalkChannel

logger = logging.getLogger(__name__)


async def main(target: ReviewTarget) -> None:
    logger.info("AiR 启动：kind=%s, ref=%s", target.kind, target.ref)

    config = AppConfig()
    reviewer = CodeReviewer(config)

    if config.is_ci:
        logger.info("运行模式：CI（通过 git 命令获取变更）")
        result = await reviewer.review_in_ci(target)
    else:
        logger.info("运行模式：本地（通过 GitLab API 获取变更）")
        result = await reviewer.review_in_local(target)

    logger.info("审查结束，开始推送结果：issues=%d", len(result.issues))
    ok = DingtalkChannel(config).send(result)
    if ok:
        logger.info("结果推送完成")
    else:
        logger.warning("结果推送失败或未配置推送渠道")
