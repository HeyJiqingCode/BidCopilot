"""归并挂载 + 覆盖率统计——两阶段 LLM 归并（规范化→分批挂载→工程合并→子节点去重），工程统计覆盖率

为什么两阶段：原先一次性把整棵骨架 + 全部要求塞进单次 LLM 调用、要求输出完整归并树，
超大标的（数百条要求）会让输出 JSON 极长 → 极慢/超时/被截断。改为：
A 规范化骨架（去重、定型 id）→ B 按来源类型分批、只输出小决策表（可并行）→ 工程回填 → C 子节点去重。
对外签名与返回 (tree, decisions) 不变，pipeline / compute_coverage 无需改动。
"""
import json
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from bid_copilot.models import (
    OutlineNode, RequirementItem, CoverageReport, SourceType, SourceRef,
)
from bid_copilot.understanding.output.tree import finalize_ids

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "llm" / "prompts"
_NORMALIZE_PROMPT = _PROMPTS_DIR / "merge_normalize.txt"
_ATTACH_PROMPT = _PROMPTS_DIR / "merge_attach.txt"
_DEDUPE_PROMPT = _PROMPTS_DIR / "merge_dedupe_children.txt"

# 阶段B 分批的来源类型顺序（评分/技术/商务）
_ATTACH_TYPES = [SourceType.SCORING, SourceType.TECH_SPEC, SourceType.BIZ_TERMS]
_TYPE_DOC = {
    SourceType.SCORING: "评标办法",
    SourceType.TECH_SPEC: "技术规范",
    SourceType.BIZ_TERMS: "商务条款",
}


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
    """归并结果——保留以兼容旧用法/测试（tree + decisions）"""
    tree: list[OutlineNode] = Field(default_factory=list)
    decisions: list[MergeDecision] = Field(default_factory=list)


class _NormalizeResult(BaseModel):
    """阶段A 输出——规范化后的骨架树"""
    tree: list[OutlineNode] = Field(default_factory=list)


class _NewChild(BaseModel):
    """阶段B 登记的新增子节点"""
    parent_id: str
    title: str
    source_type: SourceType
    ref_id: str


class _AttachResult(BaseModel):
    """阶段B 单批输出——只含判定与新增子节点，不含整棵树"""
    decisions: list[MergeDecision] = Field(default_factory=list)
    new_children: list[_NewChild] = Field(default_factory=list)


class _DedupeGroup(BaseModel):
    """阶段C 子节点合并分组"""
    keep_id: str
    merge_ids: list[str] = Field(default_factory=list)
    title: str = ""


class _DedupeResult(BaseModel):
    """阶段C 输出——子节点去重分组"""
    groups: list[_DedupeGroup] = Field(default_factory=list)


def _index_nodes(nodes: list[OutlineNode]) -> dict[str, OutlineNode]:
    """递归建立 id→节点 的索引——内部辅助

    参数:
        nodes: 顶层节点列表
    返回:
        {node_id: OutlineNode} 全树索引
    """
    idx: dict[str, OutlineNode] = {}
    for n in nodes:
        idx[n.id] = n
        idx.update(_index_nodes(n.children))
    return idx


def _normalize_skeleton(skeleton: list[OutlineNode], llm, model: str, effort: str) -> list[OutlineNode]:
    """阶段A：对骨架去重规范化，并打上稳定 id——内部辅助

    参数:
        skeleton: 原始骨架顶层节点（可能含重复）
        llm: LLMClient
        model: 模型名
        effort: 推理强度
    返回:
        规范化且已 finalize_ids 的骨架树
    """
    instructions = _NORMALIZE_PROMPT.read_text(encoding="utf-8")
    content = json.dumps([n.model_dump() for n in skeleton], ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort=effort, verbosity="low", schema=_NormalizeResult,
    )
    canonical = result.tree or skeleton          # LLM 异常返回空时退回原骨架，不致丢失
    _dedupe_sources(canonical)                   # 合并节点内重复来源（如多份 skeleton），避免 [skeleton,skeleton] 冗余
    return finalize_ids(canonical)               # 打稳定 id，供阶段B 引用


def _dedupe_sources(nodes: list[OutlineNode]) -> None:
    """递归合并每个节点内重复的来源——内部辅助；同 (type, location) 视为同一来源，ref_ids 取并集

    参数:
        nodes: 顶层节点列表（原地修改）
    返回: 无
    """
    for n in nodes:
        merged: dict[tuple, SourceRef] = {}
        for src in n.sources:
            key = (src.type, src.location)
            if key in merged:
                for rid in src.ref_ids:
                    if rid not in merged[key].ref_ids:
                        merged[key].ref_ids.append(rid)
            else:
                merged[key] = src
        n.sources = list(merged.values())
        _dedupe_sources(n.children)


def _attach_batch(canonical: list[OutlineNode], reqs: list[RequirementItem],
                  llm, model: str, effort: str) -> _AttachResult:
    """阶段B：把一批要求挂到已定型的规范树上，只产出判定——内部辅助

    参数:
        canonical: 已定型规范树（只读参考）
        reqs: 该批要求（同一 source_type）
        llm: LLMClient
        model: 模型名
        effort: 推理强度
    返回:
        _AttachResult（decisions + new_children）
    """
    if not reqs:
        return _AttachResult()
    instructions = _ATTACH_PROMPT.read_text(encoding="utf-8")
    payload = {
        "canonical_tree": [n.model_dump() for n in canonical],
        "requirements": [r.model_dump() for r in reqs],
    }
    content = json.dumps(payload, ensure_ascii=False)
    return llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort=effort, verbosity="low", schema=_AttachResult,
    )


def _dedupe_children(new_nodes: list[OutlineNode], parent_of: dict[str, str],
                     llm, model: str, effort: str) -> _DedupeResult:
    """阶段C：对本轮新增子节点做语义去重——内部辅助

    参数:
        new_nodes: 本轮新增的子节点列表
        parent_of: {子节点 id: 父节点 id}
        llm: LLMClient
        model: 模型名
        effort: 推理强度
    返回:
        _DedupeResult（合并分组）；无新增节点时返回空
    """
    if len(new_nodes) < 2:
        return _DedupeResult()
    instructions = _DEDUPE_PROMPT.read_text(encoding="utf-8")
    listing = [{"id": n.id, "parent_id": parent_of.get(n.id, ""), "title": n.title} for n in new_nodes]
    content = json.dumps(listing, ensure_ascii=False)
    return llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort=effort, verbosity="low", schema=_DedupeResult,
    )


def merge_requirements(skeleton: list[OutlineNode], requirements: list[RequirementItem],
                       llm, model: str, effort: str = "high",
                       max_concurrency: int = 5) -> tuple[list[OutlineNode], list[MergeDecision]]:
    """把要求条目语义归并进骨架树——两阶段编排（规范化→分批挂载→工程合并→子节点去重）

    参数:
        skeleton: 显式骨架顶层节点
        requirements: 要求条目列表
        llm: LLMClient
        model: 模型名（main）
        effort: 推理强度（low/medium/high），默认 high
        max_concurrency: 阶段B 分批并发上限，默认 5
    返回:
        (归并后的树, 归属判定列表)
    """
    # 阶段A：骨架去重规范化 + 定型 id
    canonical = _normalize_skeleton(skeleton, llm, model, effort)
    node_index = _index_nodes(canonical)

    # 阶段B：按来源类型分批，并行挂载（每批只产出判定，不重建树）
    batches: list[list[RequirementItem]] = [
        [r for r in requirements if r.source_type == t] for t in _ATTACH_TYPES
    ]
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as pool:
        attach_results = list(pool.map(
            lambda reqs: _attach_batch(canonical, reqs, llm, model, effort), batches
        ))

    # 工程合并：汇总判定 + 回填 ref_ids + 新建 child 节点（纯代码，不靠 LLM）
    decisions: list[MergeDecision] = []
    for res in attach_results:
        decisions.extend(res.decisions)
    req_by_ref = {r.ref_id: r for r in requirements}
    new_nodes: list[OutlineNode] = []
    parent_of: dict[str, str] = {}            # 新子节点 id → 父 id
    _new_seq = 0

    # 先处理新增子节点（child_of），按 (parent_id, title) 去重共用
    child_key_to_node: dict[tuple, OutlineNode] = {}
    for res in attach_results:
        for nc in res.new_children:
            parent = node_index.get(nc.parent_id)
            if parent is None:
                continue                       # 父 id 不存在（LLM 臆造）则跳过，对应要求会因 ref_id 不入树而记未覆盖
            key = (nc.parent_id, nc.title.strip())
            node = child_key_to_node.get(key)
            if node is None:
                _new_seq += 1
                node = OutlineNode(
                    id=f"_new{_new_seq}", title=nc.title.strip(),
                    level=parent.level + 1, sources=[], children=[],
                )
                child_key_to_node[key] = node
                parent.children.append(node)
                node_index[node.id] = node
                new_nodes.append(node)
                parent_of[node.id] = nc.parent_id
            _append_ref(node, req_by_ref.get(nc.ref_id))

    # 再处理 merged_into：把 ref_id 回填到目标节点
    for d in decisions:
        if d.disposition == Disposition.MERGED_INTO and d.node_id:
            target = node_index.get(d.node_id)
            _append_ref(target, req_by_ref.get(d.ref_id))

    # 阶段C：跨批新增子节点语义去重
    if len(new_nodes) >= 2:
        dedupe = _dedupe_children(new_nodes, parent_of, llm, model, effort)
        _apply_dedupe(canonical, dedupe, node_index)

    # 重整最终 id（消除 _newN 临时 id）
    canonical = finalize_ids(canonical)
    return canonical, decisions


def _append_ref(node: Optional[OutlineNode], req: Optional[RequirementItem]) -> None:
    """把一条要求作为来源追加到节点（含 ref_id 回填）——内部辅助；node/req 为空则跳过"""
    if node is None or req is None:
        return
    # 同类型来源若已存在则复用，把 ref_id 并入；否则新建一条 SourceRef
    for src in node.sources:
        if src.type == req.source_type and src.location == req.location:
            if req.ref_id not in src.ref_ids:
                src.ref_ids.append(req.ref_id)
            return
    node.sources.append(SourceRef(
        type=req.source_type, document=_TYPE_DOC.get(req.source_type, ""),
        location=req.location, quote=req.description, ref_ids=[req.ref_id],
    ))


def _apply_dedupe(nodes: list[OutlineNode], dedupe: "_DedupeResult",
                  node_index: dict[str, OutlineNode]) -> None:
    """把阶段C 的子节点合并分组应用到树：被并节点的来源/子节点并入保留节点后删除——内部辅助

    参数:
        nodes: 树顶层节点（原地修改）
        dedupe: 阶段C 分组结果
        node_index: id→节点 索引
    返回: 无
    """
    to_remove: set[str] = set()
    for g in dedupe.groups:
        keep = node_index.get(g.keep_id)
        if keep is None or not g.merge_ids:
            if keep is not None and g.title.strip():
                keep.title = g.title.strip()
            continue
        if g.title.strip():
            keep.title = g.title.strip()
        for mid in g.merge_ids:
            victim = node_index.get(mid)
            if victim is None or victim is keep:
                continue
            keep.sources.extend(victim.sources)
            keep.children.extend(victim.children)
            to_remove.add(mid)
    if to_remove:
        _prune(nodes, to_remove)


def _prune(nodes: list[OutlineNode], remove_ids: set[str]) -> None:
    """递归删除 id 在 remove_ids 中的节点——内部辅助；原地修改 children 列表"""
    nodes[:] = [n for n in nodes if n.id not in remove_ids]
    for n in nodes:
        _prune(n.children, remove_ids)


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
