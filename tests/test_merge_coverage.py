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
    """覆盖率纯工程统计：mapped = 非 floating；unmapped 列出 floating 的要求描述"""
    reqs = [
        RequirementItem(ref_id="R0", description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="X"),
        RequirementItem(ref_id="R1", description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="Y"),
        RequirementItem(ref_id="R2", description="质保2年", source_type=SourceType.SCORING,
                        location="评分5", suggested_title="Z"),
    ]
    decisions = [
        MergeDecision(ref_id="R0", disposition=Disposition.MERGED_INTO, node_id="1"),
        MergeDecision(ref_id="R1", disposition=Disposition.FLOATING, node_id=None),
        MergeDecision(ref_id="R2", disposition=Disposition.CHILD_OF, node_id="1"),
    ]
    cov = compute_coverage(reqs, decisions)
    assert cov.total_scoring_items == 2
    assert cov.mapped_scoring_items == 2   # 评分3 merged + 评分5 child
    assert cov.total_tech_items == 1
    assert cov.mapped_tech_items == 0      # 技术3.1 floating
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
    decisions = [
        MergeDecision(ref_id="R0", disposition=Disposition.MERGED_INTO, node_id="1"),
        MergeDecision(ref_id="R1", disposition=Disposition.CHILD_OF, node_id="1"),
        MergeDecision(ref_id="R2", disposition=Disposition.FLOATING, node_id=None),
    ]
    cov = compute_coverage(reqs, decisions)
    assert cov.total_scoring_items == 3    # 三条都计入，未因 location 相同折叠
    assert cov.mapped_scoring_items == 2   # R0+R1 已挂，R2 游离
    assert cov.unmapped == ["资格项C"]
