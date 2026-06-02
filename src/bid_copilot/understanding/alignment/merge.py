"""归并挂载 + 覆盖率统计——LLM 语义归并，工程统计覆盖率"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from bid_copilot.models import (
    OutlineNode, RequirementItem, CoverageReport, SourceType,
)

_PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "merge.txt"


class Disposition(str, Enum):
    """要求条目的归属方式"""
    MERGED_INTO = "merged_into"   # 合并进已有节点
    CHILD_OF = "child_of"         # 作为子节点新增
    FLOATING = "floating"         # 无归宿，游离


class MergeDecision(BaseModel):
    """单条要求的归属判定"""
    ref_id: str                           # 对应要求的 ref_id（稳定唯一关联键）
    disposition: Disposition
    node_id: Optional[str] = None         # 归属节点 id（floating 时为空）


class MergeResult(BaseModel):
    """归并结果——LLM 结构化输出"""
    tree: list[OutlineNode] = Field(default_factory=list)
    decisions: list[MergeDecision] = Field(default_factory=list)


def merge_requirements(skeleton: list[OutlineNode], requirements: list[RequirementItem],
                       llm, model: str, effort: str = "high") -> tuple[list[OutlineNode], list[MergeDecision]]:
    """把要求条目语义归并进骨架树

    参数:
        skeleton: 显式骨架顶层节点
        requirements: 要求条目列表
        llm: LLMClient
        model: 模型名（main）
        effort: 推理强度（low/medium/high），默认 high
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
        effort=effort, verbosity="low", schema=MergeResult,
    )
    return result.tree, result.decisions


def _collect_ref_ids(nodes: list[OutlineNode]) -> set[str]:
    """递归遍历大纲树，收集所有节点 sources 中标注的要求 ref_id——内部辅助

    参数:
        nodes: 顶层节点列表
    返回:
        树中所有 sources[].ref_ids 的并集
    """
    collected: set[str] = set()
    for node in nodes:
        for src in node.sources:
            collected.update(src.ref_ids)
        collected.update(_collect_ref_ids(node.children))
    return collected


def compute_coverage(requirements: list[RequirementItem],
                     tree: list[OutlineNode]) -> CoverageReport:
    """从最终树推导覆盖率——绑定真实产物，不信 LLM 自报

    一条要求只有当其 ref_id 真实出现在最终树某节点的 sources.ref_ids 中，才算 mapped；
    否则如实记为 unmapped。这堵死了"LLM 在 decisions 里标 mapped 但树里查无此物"的虚高漏洞。

    参数:
        requirements: 全部要求条目（带稳定 ref_id）
        tree: 最终大纲树顶层节点
    返回:
        CoverageReport（评分/技术/商务三类各自统计 total/mapped，列出未挂载描述）
    """
    mapped_ref_ids = _collect_ref_ids(tree)
    total_scoring = mapped_scoring = total_tech = mapped_tech = total_biz = mapped_biz = 0
    unmapped: list[str] = []
    for req in requirements:
        is_mapped = req.ref_id in mapped_ref_ids
        if req.source_type == SourceType.SCORING:
            total_scoring += 1
            if is_mapped:
                mapped_scoring += 1
        elif req.source_type == SourceType.TECH_SPEC:
            total_tech += 1
            if is_mapped:
                mapped_tech += 1
        elif req.source_type == SourceType.BIZ_TERMS:
            total_biz += 1
            if is_mapped:
                mapped_biz += 1
        if not is_mapped:
            unmapped.append(req.description)
    return CoverageReport(
        total_scoring_items=total_scoring, mapped_scoring_items=mapped_scoring,
        total_tech_items=total_tech, mapped_tech_items=mapped_tech,
        total_biz_items=total_biz, mapped_biz_items=mapped_biz, unmapped=unmapped,
    )
