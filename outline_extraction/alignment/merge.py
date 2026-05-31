"""归并挂载 + 覆盖率统计——LLM 语义归并，工程统计覆盖率"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from outline_extraction.models import (
    OutlineNode, RequirementItem, CoverageReport, SourceType,
)

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "merge.txt"


class Disposition(str, Enum):
    """要求条目的归属方式"""
    MERGED_INTO = "merged_into"   # 合并进已有节点
    CHILD_OF = "child_of"         # 作为子节点新增
    FLOATING = "floating"         # 无归宿，游离


class MergeDecision(BaseModel):
    """单条要求的归属判定"""
    requirement_location: str             # 对应要求的 location（关联键）
    disposition: Disposition
    node_id: Optional[str] = None         # 归属节点 id（floating 时为空）


class MergeResult(BaseModel):
    """归并结果——LLM 结构化输出"""
    tree: list[OutlineNode] = Field(default_factory=list)
    decisions: list[MergeDecision] = Field(default_factory=list)


def merge_requirements(skeleton: list[OutlineNode], requirements: list[RequirementItem],
                       llm, model: str) -> tuple[list[OutlineNode], list[MergeDecision]]:
    """把要求条目语义归并进骨架树

    参数:
        skeleton: 显式骨架顶层节点
        requirements: 要求条目列表
        llm: LLMClient
        model: 模型名（main）
    返回:
        (归并后的树, 归属判定列表)
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "skeleton": [n.model_dump() for n in skeleton],
        "requirements": [r.model_dump() for r in requirements],
    }
    content = json.dumps(payload, ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="high", verbosity="low", schema=MergeResult,
    )
    return result.tree, result.decisions


def compute_coverage(requirements: list[RequirementItem],
                     decisions: list[MergeDecision]) -> CoverageReport:
    """纯工程统计覆盖率——不依赖 LLM 自报

    参数:
        requirements: 全部要求条目
        decisions: LLM 给出的归属判定
    返回:
        CoverageReport（按来源类型统计 total/mapped，列出未挂载描述）
    """
    # location → disposition 映射
    disp_by_loc: dict[str, Disposition] = {d.requirement_location: d.disposition for d in decisions}
    total_scoring = mapped_scoring = total_tech = mapped_tech = 0
    unmapped: list[str] = []
    for req in requirements:
        disp = disp_by_loc.get(req.location, Disposition.FLOATING)
        is_mapped = disp in (Disposition.MERGED_INTO, Disposition.CHILD_OF)
        if req.source_type == SourceType.SCORING:
            total_scoring += 1
            if is_mapped:
                mapped_scoring += 1
        elif req.source_type == SourceType.TECH_SPEC:
            total_tech += 1
            if is_mapped:
                mapped_tech += 1
        if not is_mapped:
            unmapped.append(req.description)
    return CoverageReport(
        total_scoring_items=total_scoring, mapped_scoring_items=mapped_scoring,
        total_tech_items=total_tech, mapped_tech_items=mapped_tech, unmapped=unmapped,
    )
