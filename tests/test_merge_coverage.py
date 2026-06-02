"""归并与覆盖率统计测试"""
from bid_copilot.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from bid_copilot.understanding.alignment.merge import (
    merge_requirements, Disposition, MergeDecision, compute_coverage,
    _NormalizeResult, _AttachResult, _NewChild, _DedupeResult, _collect_ref_ids,
)


class _FakeLLM:
    """按调用 schema 路由返回值的 scripted LLM——模拟两阶段 merge 的三类调用"""
    def __init__(self, normalize=None, attach_by_type=None, dedupe=None):
        # normalize: _NormalizeResult；attach_by_type: {SourceType: _AttachResult}；dedupe: _DedupeResult
        self._normalize = normalize
        self._attach_by_type = attach_by_type or {}
        self._dedupe = dedupe or _DedupeResult()
        self._attach_calls = 0

    def complete(self, **kwargs):
        schema = kwargs.get("schema")
        if schema is _NormalizeResult:
            return self._normalize
        if schema is _AttachResult:
            # 阶段B 按批调用——依调用顺序（scoring, tech_spec, biz_terms）返回
            order = [SourceType.SCORING, SourceType.TECH_SPEC, SourceType.BIZ_TERMS]
            t = order[self._attach_calls] if self._attach_calls < len(order) else None
            self._attach_calls += 1
            return self._attach_by_type.get(t, _AttachResult())
        if schema is _DedupeResult:
            return self._dedupe
        raise AssertionError(f"未预期的 schema: {schema}")


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


def test_merge_two_stage_backfills_refids_and_floating_excluded():
    """两阶段归并：merged_into 把 ref_id 回填进树、floating 不进树、decisions 数=要求数"""
    skeleton = [OutlineNode(id="1", title="资格审查资料", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="五", quote=None)], children=[])]
    reqs = [
        RequirementItem(ref_id="R0", description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="质量体系认证"),
        RequirementItem(ref_id="R1", description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="效率响应"),
    ]
    # 阶段A 规范化原样返回骨架（finalize_ids 会把 id 重整为 "1"）
    normalize = _NormalizeResult(tree=[OutlineNode(id="1", title="资格审查资料", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="五", quote=None)], children=[])])
    # 阶段B：评分批把 R0 挂到节点 "1"；技术批把 R1 标 floating
    attach = {
        SourceType.SCORING: _AttachResult(decisions=[
            MergeDecision(ref_id="R0", disposition=Disposition.MERGED_INTO, node_id="1")]),
        SourceType.TECH_SPEC: _AttachResult(decisions=[
            MergeDecision(ref_id="R1", disposition=Disposition.FLOATING, node_id=None)]),
    }
    fake = _FakeLLM(normalize=normalize, attach_by_type=attach)
    tree, decisions = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")

    assert len(decisions) == 2                       # 两条要求都有判定
    mapped = _collect_ref_ids(tree)
    assert "R0" in mapped                            # merged_into → ref_id 回填进树
    assert "R1" not in mapped                        # floating → 不进树


def test_merge_propagates_is_param_table_into_tree_source():
    """参数表聚合要求(is_param_table=true)挂进树时，标记须传导到节点 SourceRef，供前端标识"""
    skeleton = [OutlineNode(id="1", title="技术参数", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="技术", quote=None)], children=[])]
    # 含一条评分 + 一条参数表聚合技术要求（评分批占位，使 _FakeLLM 的按序路由对齐到 tech 批）
    reqs = [
        RequirementItem(ref_id="R0", description="评分项", source_type=SourceType.SCORING,
                        location="评1", suggested_title="X"),
        RequirementItem(ref_id="R1", description="对《组件规格表》全部参数统一应答（共约8项）",
                        source_type=SourceType.TECH_SPEC, location="表2", suggested_title="技术参数响应表",
                        is_param_table=True),
    ]
    normalize = _NormalizeResult(tree=[OutlineNode(id="1", title="技术参数", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="技术", quote=None)], children=[])])
    attach = {
        SourceType.SCORING: _AttachResult(decisions=[
            MergeDecision(ref_id="R0", disposition=Disposition.MERGED_INTO, node_id="1")]),
        SourceType.TECH_SPEC: _AttachResult(decisions=[
            MergeDecision(ref_id="R1", disposition=Disposition.MERGED_INTO, node_id="1")]),
    }
    fake = _FakeLLM(normalize=normalize, attach_by_type=attach)
    tree, _ = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")

    # R1（参数表聚合）回填后，节点应有一条 is_param_table=True 的 source
    def _has_param_flag(nodes):
        for n in nodes:
            if any(s.is_param_table for s in n.sources):
                return True
            if _has_param_flag(n.children):
                return True
        return False
    assert _has_param_flag(tree)


def test_merge_preserves_normalized_concise_title_and_quote():
    """阶段A 规范化产出的简洁标题（原文整句留在 quote）必须原样进入最终树——工程不得覆盖 LLM 的标题选择"""
    # 原始骨架：标题是整句要求描述（模拟原文把一句话当条目名）
    skeleton = [OutlineNode(id="1", title="按招标文件要求或者投标人认为有必要提供的其他商务文件", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="（6）按招标文件要求…其他商务文件",
                  quote="（6）按招标文件要求或者投标人认为有必要提供的其他商务文件")], children=[])]
    # 阶段A 归纳出简洁标题"其他商务文件"，原文整句保留在 quote
    normalize = _NormalizeResult(tree=[OutlineNode(id="1", title="其他商务文件", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="（6）按招标文件要求…其他商务文件",
                  quote="（6）按招标文件要求或者投标人认为有必要提供的其他商务文件")], children=[])])
    fake = _FakeLLM(normalize=normalize)             # 无要求挂载，attach 各批返回空
    tree, _ = merge_requirements(skeleton, [], llm=fake, model="gpt-5.4")

    assert tree[0].title == "其他商务文件"             # 简洁标题被保留，未被工程改回整句
    quotes = [s.quote for s in tree[0].sources]
    assert any(q and "其他商务文件" in q and len(q) > 12 for q in quotes)  # 原文整句仍在 quote，可溯源


def test_merge_two_stage_child_of_creates_node_and_dedupes():
    """两阶段：child_of 新建子节点；跨批同义新子节点被阶段C 去重合并"""
    skeleton = [OutlineNode(id="1", title="技术投标文件", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="技术", quote=None)], children=[])]
    reqs = [
        RequirementItem(ref_id="R0", description="项目管理机构", source_type=SourceType.SCORING,
                        location="评分1", suggested_title="项目管理机构"),
        RequirementItem(ref_id="R1", description="项目组织机构", source_type=SourceType.TECH_SPEC,
                        location="技术1", suggested_title="项目组织机构"),
    ]
    normalize = _NormalizeResult(tree=[OutlineNode(id="1", title="技术投标文件", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="技术", quote=None)], children=[])])
    # 评分批与技术批各自在节点 "1" 下新增一个语义相近的子节点
    attach = {
        SourceType.SCORING: _AttachResult(
            decisions=[MergeDecision(ref_id="R0", disposition=Disposition.CHILD_OF, node_id="1")],
            new_children=[_NewChild(parent_id="1", title="项目管理机构", source_type=SourceType.SCORING, ref_id="R0")]),
        SourceType.TECH_SPEC: _AttachResult(
            decisions=[MergeDecision(ref_id="R1", disposition=Disposition.CHILD_OF, node_id="1")],
            new_children=[_NewChild(parent_id="1", title="项目组织机构", source_type=SourceType.TECH_SPEC, ref_id="R1")]),
    }
    # 阶段C：把两个新子节点合并为一个（keep 第一个，并入第二个）
    from bid_copilot.understanding.alignment.merge import _DedupeGroup
    dedupe = _DedupeResult(groups=[_DedupeGroup(keep_id="_new1", merge_ids=["_new2"], title="项目管理机构")])
    fake = _FakeLLM(normalize=normalize, attach_by_type=attach, dedupe=dedupe)

    tree, decisions = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")

    mapped = _collect_ref_ids(tree)
    assert "R0" in mapped and "R1" in mapped         # 两条都挂进了树
    # 去重后，节点 "技术投标文件" 下只应有 1 个子节点（两个同义新节点合一）
    tech = next(n for n in tree if n.title == "技术投标文件")
    assert len(tech.children) == 1


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
