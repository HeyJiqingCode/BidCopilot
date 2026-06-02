"""生成式兜底——安置未挂进树的游离要求（LLM 只决定放哪，ref_id 由工程回填）

为什么工程回填 ref_id：旧版让 LLM 自由重写整棵树并自己填 ref_id，LLM 常把多条
同类要求归并到一个节点却只给其中一条标 ref_id、其余漏填，导致这些要求虽"语义上挂上了"
但 ref_id 不在树里 → 覆盖率（认 ref_id）判其未覆盖 → 漏项。改为与 merge 同构：
LLM 只输出每条游离要求的安置判定（挂到已有节点 / 新建子节点），ref_id 一律由
工程代码 _append_ref 落到 source，保证安置的要求必带 ref_id，覆盖率如实反映。
"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from bid_copilot.models import OutlineNode, RequirementItem
from bid_copilot.understanding.alignment.merge import _index_nodes, _append_ref

_PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "supplement.txt"


class SupplementDisposition(str, Enum):
    """游离要求的安置方式"""
    MERGED_INTO = "merged_into"   # 挂到已有节点
    CHILD_OF = "child_of"         # 在某父节点下新建子节点安置


class SupplementDecision(BaseModel):
    """单条游离要求的安置判定（LLM 输出，ref_id 关联回要求）"""
    ref_id: str                                   # 对应游离要求的 ref_id
    disposition: SupplementDisposition
    node_id: str                                  # merged_into：目标节点 id；child_of：父节点 id
    new_title: str = ""                           # child_of 时新建子节点的标题


class SupplementResult(BaseModel):
    """生成式兜底输出——只含安置判定，不含整棵树（ref_id 由工程回填）"""
    decisions: list[SupplementDecision] = Field(default_factory=list)


def supplement_tree(tree: list[OutlineNode], floating: list[RequirementItem],
                    llm, model: str, effort: str = "high") -> list[OutlineNode]:
    """把游离要求安置进大纲树——LLM 决定位置，工程回填 ref_id

    参数:
        tree: 当前归并后的树顶层节点（原地补充安置节点，不删除已有节点）
        floating: 未挂进树的游离要求（带稳定 ref_id）
        llm: LLMClient
        model: 模型名
        effort: 推理强度（low/medium/high），默认 high
    返回:
        安置了游离要求的大纲树（顶层节点列表）
    """
    if not floating:
        return tree                                # 无游离要求，原样返回（pipeline 已短路，这里再兜一层）

    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "tree": [n.model_dump() for n in tree],
        "floating_requirements": [
            {"ref_id": r.ref_id, "description": r.description,
             "source_type": r.source_type.value, "location": r.location}
            for r in floating
        ],
    }
    content = json.dumps(payload, ensure_ascii=False)
    result = llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort=effort, verbosity="low", schema=SupplementResult,
    )

    # 工程回填：按判定把每条游离要求的 ref_id 落到目标/新建节点的 source（不靠 LLM 填）
    node_index = _index_nodes(tree)
    req_by_ref = {r.ref_id: r for r in floating}
    child_key_to_node: dict[tuple, OutlineNode] = {}      # (parent_id, title) → 新建子节点，去重共用
    _seq = 0
    for d in result.decisions:
        req = req_by_ref.get(d.ref_id)
        if req is None:
            continue                                      # LLM 臆造的 ref_id，跳过
        if d.disposition == SupplementDisposition.CHILD_OF:
            parent = node_index.get(d.node_id)
            if parent is None:
                continue                                  # 父 id 不存在，跳过（该要求仍记未覆盖，不误报已挂）
            title = (d.new_title or req.description[:20]).strip()
            key = (d.node_id, title)
            node = child_key_to_node.get(key)
            if node is None:
                _seq += 1
                node = OutlineNode(id=f"_sup{_seq}", title=title,
                                   level=parent.level + 1, sources=[], children=[])
                child_key_to_node[key] = node
                parent.children.append(node)
                node_index[node.id] = node
            _append_ref(node, req)
        else:                                             # merged_into
            target = node_index.get(d.node_id)
            _append_ref(target, req)                       # target 为空时 _append_ref 内部跳过
    return tree
