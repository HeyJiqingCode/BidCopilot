"""归并与覆盖率统计测试"""
from outline_extraction.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from outline_extraction.alignment.merge import merge_requirements, MergeResult, Disposition, MergeDecision, compute_coverage


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def complete(self, **kwargs):
        return self._result


def _node(node_id, title, ref_ids, src_type=SourceType.SCORING, children=None):
    """构造带 ref_ids 来源的树节点——测试辅助

    参数:
        node_id: 节点 id
        title: 标题
        ref_ids: 该节点来源覆盖的要求 ref_id 列表
        src_type: 来源类型
        children: 子节点
    返回:
        OutlineNode
    """
    return OutlineNode(
        id=node_id, title=title, level=1,
        sources=[SourceRef(type=src_type, document="d", location="loc", quote=None, ref_ids=ref_ids)],
        children=children or [],
    )


def test_merge_returns_tree_and_decisions():
    """归并返回树 + 每条要求的判定"""
    skeleton = [OutlineNode(id="1", title="资格审查资料", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="五", quote=None)], children=[])]
    reqs = [
        RequirementItem(ref_id="R0", description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="质量体系认证"),
        RequirementItem(ref_id="R1", description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="效率响应"),
    ]
    fake = _FakeLLM(MergeResult(
        tree=skeleton,
        decisions=[
            MergeDecision(ref_id="R0", disposition=Disposition.MERGED_INTO, node_id="1"),
            MergeDecision(ref_id="R1", disposition=Disposition.FLOATING, node_id=None),
        ],
    ))
    tree, decisions = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")
    assert len(decisions) == 2


def test_compute_coverage_counts_mapped_vs_total():
    """覆盖率从树推导：ref_id 出现在树某节点 sources.ref_ids 中即 mapped"""
    reqs = [
        RequirementItem(ref_id="R0", description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="X"),
        RequirementItem(ref_id="R1", description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="Y"),
        RequirementItem(ref_id="R2", description="质保2年", source_type=SourceType.SCORING,
                        location="评分5", suggested_title="Z"),
    ]
    # 树中只挂了 R0、R2（评分），R1（技术）未出现 → 技术未覆盖
    tree = [_node("1", "资格", ["R0", "R2"], src_type=SourceType.SCORING)]
    cov = compute_coverage(reqs, tree)
    assert cov.total_scoring_items == 2
    assert cov.mapped_scoring_items == 2   # R0 + R2 都在树中
    assert cov.total_tech_items == 1
    assert cov.mapped_tech_items == 0      # R1 不在树中
    assert "效率98.5%" in cov.unmapped


def test_compute_coverage_duplicate_location_not_collapsed():
    """同一 location 的多条要求，凭唯一 ref_id 各自独立计数（防 location 折叠回归）"""
    reqs = [
        RequirementItem(ref_id="R0", description="资格项A", source_type=SourceType.SCORING,
                        location="四、评审 1.1 资格审查", suggested_title="A"),
        RequirementItem(ref_id="R1", description="资格项B", source_type=SourceType.SCORING,
                        location="四、评审 1.1 资格审查", suggested_title="B"),
        RequirementItem(ref_id="R2", description="资格项C", source_type=SourceType.SCORING,
                        location="四、评审 1.1 资格审查", suggested_title="C"),
    ]
    # 树中挂了 R0、R1，未挂 R2
    tree = [_node("1", "资格审查", ["R0", "R1"], src_type=SourceType.SCORING)]
    cov = compute_coverage(reqs, tree)
    assert cov.total_scoring_items == 3    # 三条都计入，未因 location 相同折叠
    assert cov.mapped_scoring_items == 2   # R0+R1 已挂，R2 未挂
    assert cov.unmapped == ["资格项C"]


def test_compute_coverage_counts_biz_items():
    """商务要求独立成栏统计"""
    reqs = [
        RequirementItem(ref_id="R0", description="付款条件响应", source_type=SourceType.BIZ_TERMS,
                        location="商务2.1", suggested_title="付款条件"),
        RequirementItem(ref_id="R1", description="交货期响应", source_type=SourceType.BIZ_TERMS,
                        location="商务2.2", suggested_title="交货期"),
    ]
    # 树中只挂了 R0
    tree = [_node("1", "商务响应", ["R0"], src_type=SourceType.BIZ_TERMS)]
    cov = compute_coverage(reqs, tree)
    assert cov.total_biz_items == 2
    assert cov.mapped_biz_items == 1       # 仅 R0 在树中
    assert "交货期响应" in cov.unmapped


def test_compute_coverage_trusts_tree_not_decisions():
    """核心回归：覆盖率只认树，不信 LLM 自报

    即使语义上某要求"该挂"，只要其 ref_id 未真正出现在最终树的 sources.ref_ids 中，
    就如实记为 unmapped——堵死"LLM 在 decisions 里嘴上标 mapped 但树里查无此物"的虚高漏洞。
    """
    reqs = [
        RequirementItem(ref_id="R0", description="评分项必含", source_type=SourceType.SCORING,
                        location="评分1", suggested_title="必含项"),
    ]
    # 树非空，但没有任何节点的 sources.ref_ids 包含 R0（模拟 LLM 没真把来源落到树上）
    tree = [OutlineNode(id="1", title="某章节", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="一", quote=None, ref_ids=[])],
        children=[])]
    cov = compute_coverage(reqs, tree)
    assert cov.total_scoring_items == 1
    assert cov.mapped_scoring_items == 0   # 树中无 R0 → 不信自报，记未覆盖
    assert cov.unmapped == ["评分项必含"]


def test_compute_coverage_collects_ref_ids_from_nested_children():
    """ref_ids 收集需递归遍历子节点——挂在深层子节点的要求也算 mapped"""
    reqs = [
        RequirementItem(ref_id="R0", description="深层要求", source_type=SourceType.TECH_SPEC,
                        location="技术9", suggested_title="深层"),
    ]
    child = _node("1.1", "子节点", ["R0"], src_type=SourceType.TECH_SPEC)
    parent = OutlineNode(id="1", title="父节点", level=1, sources=[], children=[child])
    cov = compute_coverage(reqs, [parent])
    assert cov.mapped_tech_items == 1      # R0 挂在子节点 → 仍算覆盖
    assert cov.unmapped == []
