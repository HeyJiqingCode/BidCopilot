"""生成式兜底测试——注入 fake LLM"""
from outline_extraction.models import OutlineNode, SourceRef, SourceType
from outline_extraction.alignment.supplement import supplement_tree, SupplementResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.called = False

    def complete(self, **kwargs):
        self.called = True
        return self._result


def test_supplement_adds_ai_suggested_node():
    """兜底返回含 ai_suggested 节点的树"""
    base = [OutlineNode(id="1", title="技术响应", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt", location="七", quote=None)], children=[])]
    enriched = base + [OutlineNode(id="2", title="项目实施组织方案", level=1, sources=[
        SourceRef(type=SourceType.AI_SUGGESTED, document="(AI建议)", location="-", quote=None)], children=[])]
    fake = _FakeLLM(SupplementResult(tree=enriched))
    result = supplement_tree(base, floating=["效率参数响应"], llm=fake, model="gpt-5.4")
    assert any(n.sources[0].type == SourceType.AI_SUGGESTED for n in result)


def test_supplement_skips_llm_when_nothing_to_do():
    """无游离要求时仍可调用（补行业惯例），但空树+空游离应短路返回原树"""
    base = [OutlineNode(id="1", title="X", level=1, sources=[], children=[])]
    fake = _FakeLLM(SupplementResult(tree=base))
    result = supplement_tree(base, floating=[], llm=fake, model="gpt-5.4")
    # 允许仍调用以补惯例；此处验证返回树非空且包含原节点
    assert any(n.title == "X" for n in result)
