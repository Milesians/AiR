import logging

from dotenv import load_dotenv

load_dotenv()

from air.config import AppConfig
from air.target import ReviewTarget
from air.agent import CodeReviewer
from air.channel import DingtalkChannel

logger = logging.getLogger(__name__)


async def main(target: ReviewTarget, config: AppConfig) -> None:
    logger.info("AiR 启动：%d 个 commit, after_sha=%s", len(target.commits), target.after_sha)

    reviewer = CodeReviewer(config)
    result = await reviewer.review(target)

    logger.info("审查结束，开始推送结果：issues=%d", len(result.issues))
    ok = DingtalkChannel(config).send(result)
    if ok:
        logger.info("结果推送完成")
    else:
        logger.warning("结果推送失败或未配置推送渠道")
