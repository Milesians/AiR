from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewLine(BaseModel):
    """GitLab diff 中的一行位置"""

    model_config = ConfigDict(extra="forbid")

    old_line: int | None = Field(default=None, gt=0)
    new_line: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_line(self) -> "ReviewLine":
        if self.old_line is None and self.new_line is None:
            raise ValueError("old_line 和 new_line 至少需要提供一个")
        return self


class ReviewComment(BaseModel):
    """一条结构化审查评论；无位置时作为普通 MR 评论发送"""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)
    old_path: str | None = Field(default=None, min_length=1)
    new_path: str | None = Field(default=None, min_length=1)
    start_line: ReviewLine | None = None
    end_line: ReviewLine | None = None

    @model_validator(mode="after")
    def validate_position(self) -> "ReviewComment":
        has_path = self.old_path is not None or self.new_path is not None
        has_line = self.start_line is not None or self.end_line is not None

        if not has_path and not has_line:
            return self
        if self.old_path is None or self.new_path is None:
            raise ValueError("行内评论必须同时提供 old_path 和 new_path")
        if self.start_line is None:
            raise ValueError("行内评论必须提供 start_line")
        return self

    @property
    def is_inline(self) -> bool:
        return self.start_line is not None

    @property
    def is_multiline(self) -> bool:
        return self.end_line is not None and self.end_line != self.start_line


class ReviewResult(BaseModel):
    """审查结果

    `body` 会被直接作为钉钉通知正文透传。
    `comments` 是用于 GitLab MR 的结构化评论；为空时 GitLab 回退发送 `body`。
    `should_notify` 由 LLM 判断本次结果是否值得发送钉钉通知；MR 评论不受此字段影响。
    """

    model_config = ConfigDict(extra="forbid")

    body: str = ""
    comments: list[ReviewComment] = Field(default_factory=list)
    should_notify: bool = True
