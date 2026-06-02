"""要求条目抽取——把评分/技术章节逐条抽成 RequirementItem"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pydantic import BaseModel, Field
from bid_copilot.models import RequirementItem

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "extract_requirements.txt"


class RequirementsResult(BaseModel):
    """单章节抽取结果"""
    items: list[RequirementItem] = Field(default_factory=list)


def extract_requirements(section_texts: list[str], llm, model: str, effort: str = "medium",
                         max_concurrency: int = 5) -> list[RequirementItem]:
    """从评分/技术/商务章节抽取要求条目（多章节并行调用）

    参数:
        section_texts: 关键章节文本列表（评分/技术/商务）
        llm: LLMClient
        model: 模型名（main）
        effort: 推理强度（low/medium/high），默认 medium
        max_concurrency: 并行上限，默认 5
    返回:
        合并后的 RequirementItem 列表（顺序与输入章节一致）
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    # 跳过空白章节：无内容可抽，且空 input 会被 API 拒绝
    texts = [t for t in section_texts if t.strip()]
    if not texts:
        return []

    def _one(text: str) -> list[RequirementItem]:
        """抽取单个章节的要求——内部辅助（供并行调用）"""
        result = llm.complete(
            model=model, instructions=instructions, input_content=text,
            effort=effort, verbosity="low", schema=RequirementsResult,
        )
        return result.items

    all_items: list[RequirementItem] = []
    # pool.map 保序：结果按输入章节顺序合并，与原串行行为一致
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as pool:
        for items in pool.map(_one, texts):
            all_items.extend(items)
    return all_items
