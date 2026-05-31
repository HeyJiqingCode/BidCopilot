"""显式骨架抽取——把"投标文件格式"章节忠实抽成 OutlineNode 树"""
from pathlib import Path
from pydantic import BaseModel, Field
from outline_extraction.models import OutlineNode

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "extract_skeleton.txt"


class SkeletonResult(BaseModel):
    """骨架抽取结果——顶层节点列表"""
    nodes: list[OutlineNode] = Field(default_factory=list)


def extract_skeleton(section_text: str, document: str, llm, model: str) -> list[OutlineNode]:
    """从投标文件格式章节抽取显式骨架

    参数:
        section_text: "投标文件格式/组成"章节全文
        document: 来源文件名
        llm: LLMClient
        model: 模型名（main）
    返回:
        OutlineNode 顶层列表（来源已标 SKELETON）
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    content = f"来源文件名：{document}\n章节全文：\n{section_text}"
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="medium", verbosity="low", schema=SkeletonResult,
    )
    return result.nodes
