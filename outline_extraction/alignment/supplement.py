"""生成式兜底——安置游离要求 + 补充行业惯例章节（标 ai_suggested）"""
import json
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import OutlineNode

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "supplement.txt"


class SupplementResult(BaseModel):
    """兜底结果——补全后的大纲树"""
    tree: list[OutlineNode] = Field(default_factory=list)


def supplement_tree(tree: list[OutlineNode], floating: list[str], llm, model: str) -> list[OutlineNode]:
    """生成式补全大纲树

    参数:
        tree: 当前归并后的树
        floating: 游离要求的描述列表
        llm: LLMClient
        model: 模型名（main）
    返回:
        补全后的大纲树
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "tree": [n.model_dump() for n in tree],
        "floating_requirements": floating,
    }
    content = json.dumps(payload, ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="high", verbosity="low", schema=SupplementResult,
    )
    return result.tree
