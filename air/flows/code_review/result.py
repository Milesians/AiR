from pydantic import BaseModel, ConfigDict


class ReviewResult(BaseModel):
    """审查结果

    `body` 会被直接作为通知正文透传给下游渠道。
    `should_notify` 由 LLM 判断本次结果是否值得发送通知。
    """

    model_config = ConfigDict(extra="forbid")

    body: str = ""
    should_notify: bool = True
