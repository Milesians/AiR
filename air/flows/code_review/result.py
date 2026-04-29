from pydantic import BaseModel, ConfigDict


class ReviewResult(BaseModel):
    """审查结果

    `body` 会被直接作为通知正文透传给下游渠道。
    """

    model_config = ConfigDict(extra="forbid")

    body: str = ""
