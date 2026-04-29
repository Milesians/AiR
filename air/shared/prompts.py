"""Code review Prompt 模板加载器"""
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "flows" / "code_review" / "prompts"


def load_prompt(name: str) -> str:
    """按名称加载 code review prompt 模板"""
    path = _PROMPT_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt 模板不存在：{name}")
