"""Prompt 模板加载器"""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """加载指定名称的 prompt 模板"""
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
