import argparse
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from air.flows.code_review.reviewer import CodeReviewer
from air.flows.code_review.dingtalk import DingtalkChannel
from air.shared.config import AppConfig
from air.flows.code_review.target import ReviewTarget

logger = logging.getLogger(__name__)


def setup_logging(debug: bool) -> None:
    """初始化日志配置"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        prog="air",
        description="AiR - AI Code Reviewer，在 CI/CD 流水线中自动审查代码",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        default=False,
        help="开启 Debug 日志模式",
    )

    parser.add_argument(
        "--work-dir",
        "-w",
        metavar="PATH",
        help="工作目录，优先级高于环境变量 AIR_WORK_DIR",
    )

    parser.add_argument(
        "--commit",
        "-c",
        metavar="SHA",
        help="指定单个 commit SHA（不指定则从 CI 环境变量自动检测）",
    )

    return parser.parse_args()


async def run(target: ReviewTarget, config: AppConfig) -> None:
    """主流程：审查 → 推送"""
    logger.info("AiR 启动：%d 个 commit, after_sha=%s", len(target.commits), target.after_sha)

    reviewer = CodeReviewer(config)
    result = await reviewer.review(target)

    logger.info("审查结束，开始推送结果：body=%d字符", len(result.body))
    ok = DingtalkChannel(config).send(result, target)
    if ok:
        logger.info("结果推送完成")
    else:
        logger.warning("结果推送失败或未配置推送渠道")


def main() -> None:
    args = parse_args()
    setup_logging(args.debug)

    config = AppConfig(work_dir=args.work_dir)

    if args.commit:
        target = ReviewTarget.from_commit(args.commit, work_dir=config.work_dir)
    else:
        target = ReviewTarget.from_ci_env(work_dir=config.work_dir)

    asyncio.run(run(target, config))


if __name__ == "__main__":
    main()
