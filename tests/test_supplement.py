"""生成式兜底测试——LLM 只决定安置位置，ref_id 由工程回填"""
from bid_copilot.models import OutlineNode, SourceRef, SourceType, RequirementItem
from bid_copilot.understanding.alignment.supplement import (
    supplement_tree, SupplementResult, SupplementDecision, SupplementDisposition,
)
from bid_copilot.understanding.alignment.merge import _collect_ref_ids


class _FakeLLM:
    """返回固定 SupplementResult 的 fake LLM"""
    def __init__(self, result):
        self._result = result
        self.called = False

    def complete(self, **kwargs):
        self.called = True
        return self._result


def _req(ref_id, desc, loc="22.3"):
    """构造一条商务游离要求——测试辅助"""
    return RequirementItem(ref_id=ref_id, description=desc, source_type=SourceType.BIZ_TERMS,
                           location=loc, suggested_title=desc[:8])


def test_supplement_child_of_backfills_refid():
    """child_of 新建子节点安置游离要求时，ref_id 必须被工程回填进新节点（覆盖率才认）"""
    base = [OutlineNode(id="1", title="其他商务文件", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="六", quote=None)], children=[])]
    floating = [_req("R12", "履约保证金有效期承诺")]
    # LLM 只决定：把 R12 作为 "1" 的子节点安置
    fake = _FakeLLM(SupplementResult(decisions=[
        SupplementDecision(ref_id="R12", disposition=SupplementDisposition.CHILD_OF,
                           node_id="1", new_title="履约保证金承诺")]))
    result = supplement_tree(base, floating=floating, llm=fake, model="gpt-5.4")

    assert "R12" in _collect_ref_ids(result)          # ref_id 被回填进树
    parent = next(n for n in result if n.id == "1")
    assert any(c.title == "履约保证金承诺" for c in parent.children)   # 新建了子节点


def test_supplement_multiple_same_parent_share_node_and_all_refids_kept():
    """多条同类游离要求共用一个新建子节点时，每条的 ref_id 都要回填，不能只留一条"""
    base = [OutlineNode(id="1", title="其他商务文件", level=1, sources=[], children=[])]
    floating = [_req("R12", "履约保证金A"), _req("R13", "履约保证金B"), _req("R14", "履约保证金C")]
    # 三条都判 child_of 到 "1"、同一标题 → 应合并为一个子节点，但三条 ref_id 都在
    fake = _FakeLLM(SupplementResult(decisions=[
        SupplementDecision(ref_id=r, disposition=SupplementDisposition.CHILD_OF,
                           node_id="1", new_title="履约保证金承诺")
        for r in ("R12", "R13", "R14")]))
    result = supplement_tree(base, floating=floating, llm=fake, model="gpt-5.4")

    mapped = _collect_ref_ids(result)
    assert {"R12", "R13", "R14"} <= mapped            # 三条 ref_id 全部回填（修复前只会留一条）
    parent = next(n for n in result if n.id == "1")
    assert len(parent.children) == 1                  # 同标题合并为一个子节点


def test_supplement_merged_into_existing_node():
    """merged_into：把游离要求挂到已有节点，ref_id 回填到该节点 source"""
    base = [OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]
    floating = [_req("R5", "投标有效期承诺")]
    fake = _FakeLLM(SupplementResult(decisions=[
        SupplementDecision(ref_id="R5", disposition=SupplementDisposition.MERGED_INTO, node_id="1")]))
    result = supplement_tree(base, floating=floating, llm=fake, model="gpt-5.4")
    assert "R5" in _collect_ref_ids(result)


def test_supplement_invalid_node_id_skipped_not_falsely_mapped():
    """LLM 给的 node_id 不存在时跳过，不误把 ref_id 标进树（宁可记未覆盖，不虚报已挂）"""
    base = [OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]
    floating = [_req("R9", "某游离要求")]
    fake = _FakeLLM(SupplementResult(decisions=[
        SupplementDecision(ref_id="R9", disposition=SupplementDisposition.CHILD_OF,
                           node_id="NOPE", new_title="X")]))
    result = supplement_tree(base, floating=floating, llm=fake, model="gpt-5.4")
    assert "R9" not in _collect_ref_ids(result)


def test_supplement_empty_floating_returns_tree_unchanged_without_llm():
    """无游离要求时不调用 LLM，原样返回树"""
    base = [OutlineNode(id="1", title="X", level=1, sources=[], children=[])]
    fake = _FakeLLM(SupplementResult())
    result = supplement_tree(base, floating=[], llm=fake, model="gpt-5.4")
    assert result is base and not fake.called
