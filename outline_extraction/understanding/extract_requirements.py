"""要求条目抽取——把评分/技术章节逐条抽成 RequirementItem"""
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import RequirementItem

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "extract_requirements.txt"


class RequirementsResult(BaseModel):
    """单章节抽取结果"""
    items: list[RequirementItem] = Field(default_factory=list)


def extract_requirements(section_texts: list[str], llm, model: str) -> list[RequirementItem]:
    """从评分/技术/商务章节抽取要求条目

    参数:
        section_texts: 关键章节文本列表（评分/技术/商务）
        llm: LLMClient
        model: 模型名（main）
    返回:
        合并后的 RequirementItem 列表
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    all_items: list[RequirementItem] = []
    for text in section_texts:
        result = llm.complete(
            model=model, instructions=instructions, input_content=text,
            effort="medium", verbosity="low", schema=RequirementsResult,
        )
        all_items.extend(result.items)
    return all_items
