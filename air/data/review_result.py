from pydantic import BaseModel


class ReviewIssue(BaseModel):
    """单个审查问题"""
    file_path: str
    start_line: int = 0
    end_line: int = 0
    severity: str  # error, warning, info
    message: str
    original_code: str = ""  # 问题代码片段
    suggested_code: str = ""  # 建议修改后的代码片段

class ReviewResult(BaseModel):
    """审查结果"""
    summary: str = ""
    issues: list[ReviewIssue] = []