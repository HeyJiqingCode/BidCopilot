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
        RequirementItem(description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="质量体系认证"),
        RequirementItem(description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="效率响应"),
    ]
    fake = _FakeLLM(MergeResult(
        tree=skeleton,
        decisions=[
            MergeDecision(requirement_location="评分3", disposition=Disposition.MERGED_INTO, node_id="1"),
            MergeDecision(requirement_location="技术3.1", disposition=Disposition.FLOATING, node_id=None),
        ],
    ))
    tree, decisions = merge_requirements(skeleton, reqs, llm=fake, model="gpt-5.4")
    assert len(decisions) == 2


def test_compute_coverage_counts_mapped_vs_total():
    """覆盖率纯工程统计：mapped = 非 floating；unmapped 列出 floating 的要求描述"""
    reqs = [
        RequirementItem(description="ISO9001", source_type=SourceType.SCORING,
                        location="评分3", suggested_title="X"),
        RequirementItem(description="效率98.5%", source_type=SourceType.TECH_SPEC,
                        location="技术3.1", suggested_title="Y"),
        RequirementItem(description="质保2年", source_type=SourceType.SCORING,
                        location="评分5", suggested_title="Z"),
    ]
    decisions = [
        MergeDecision(requirement_location="评分3", disposition=Disposition.MERGED_INTO, node_id="1"),
        MergeDecision(requirement_location="技术3.1", disposition=Disposition.FLOATING, node_id=None),
        MergeDecision(requirement_location="评分5", disposition=Disposition.CHILD_OF, node_id="1"),
    ]
    cov = compute_coverage(reqs, decisions)
    assert cov.total_scoring_items == 2
    assert cov.mapped_scoring_items == 2   # 评分3 merged + 评分5 child
    assert cov.total_tech_items == 1
    assert cov.mapped_tech_items == 0      # 技术3.1 floating
    assert "效率98.5%" in cov.unmapped
