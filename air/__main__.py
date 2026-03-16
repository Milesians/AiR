import argparse
import asyncio
import logging

from air.air import main
from air.target import ReviewTarget


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

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--commit", "-c", metavar="SHA", help="指定 commit SHA")
    group.add_argument("--mr", "-m", metavar="IID", help="指定 MR IID（预留）")

    return parser.parse_args()


def main_sync() -> None:
    args = parse_args()
    setup_logging(args.debug)

    target = ReviewTarget("commit", args.commit) if args.commit else ReviewTarget("mr", args.mr)
    asyncio.run(main(target))


if __name__ == "__main__":
    main_sync()
