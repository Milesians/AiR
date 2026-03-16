from abc import ABC, abstractmethod

from air.data.review_result import ReviewResult


class Channel(ABC):
    """结果推送渠道抽象基类"""

    @abstractmethod
    def send(self, result: ReviewResult) -> bool:
        """发送审查结果，成功返回 True"""