from pydantic import BaseModel


class ReviewIssue(BaseModel):
    """单个审查问题"""
    file_path: str
    line: int = 0
    severity: str  # error, warning, info
    message: str
    commiter: str


class ReviewResult(BaseModel):
    """审查结果"""
    summary: str = ""
    issues: list[ReviewIssue] = []