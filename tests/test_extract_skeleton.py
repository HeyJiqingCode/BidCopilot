"""显式骨架抽取测试——注入 fake LLM 返回 OutlineNode 树"""
from bid_copilot.models import OutlineNode, SourceRef, SourceType
from bid_copilot.understanding.extract_skeleton import extract_skeleton, SkeletonResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.last_kwargs = None

    def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._result


def test_extract_skeleton_returns_tree():
    """骨架抽取返回带 SKELETON 来源的节点树"""
    nodes = [OutlineNode(
        id="1", title="投标函", level=1,
        sources=[SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)],
        children=[],
    )]
    fake = _FakeLLM(SkeletonResult(nodes=nodes))
    result = extract_skeleton("一、投标函\n二、资格审查资料", document="fmt.docx",
                              llm=fake, model="gpt-5.4")
    assert result[0].title == "投标函"
    assert result[0].sources[0].type == SourceType.SKELETON
    assert "投标函" in fake.last_kwargs["input_content"]
