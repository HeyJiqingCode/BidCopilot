"""树排序与 id 重整测试"""
from outline_extraction.models import OutlineNode, SourceRef, SourceType
from outline_extraction.output.tree import finalize_ids


def _node(title, level, children=None):
    return OutlineNode(id="x", title=title, level=level, sources=[], children=children or [])


def test_finalize_assigns_path_ids():
    """路径式 id：顶层 1,2；子层 1.1,1.2"""
    nodes = [
        _node("A", 1, [_node("A1", 2), _node("A2", 2)]),
        _node("B", 1),
    ]
    result = finalize_ids(nodes)
    assert result[0].id == "1"
    assert result[0].children[0].id == "1.1"
    assert result[0].children[1].id == "1.2"
    assert result[1].id == "2"


def test_finalize_deep_nesting():
    """三层嵌套 id 正确"""
    nodes = [_node("A", 1, [_node("A1", 2, [_node("A1a", 3)])])]
    result = finalize_ids(nodes)
    assert result[0].children[0].children[0].id == "1.1.1"
