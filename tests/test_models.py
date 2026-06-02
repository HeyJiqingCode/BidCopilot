"""数据模型测试"""
from bid_copilot.models import (
    SourceType, SourceRef, OutlineNode, OutlineTree, CoverageReport,
    ParsedDocument, Section, RequirementItem,
)


def test_outline_node_nested():
    """验证 OutlineNode 可嵌套子节点并保留多来源"""
    child = OutlineNode(
        id="1.1", title="投标函", level=2,
        sources=[SourceRef(type=SourceType.SKELETON, document="格式.docx",
                           location="一、投标函", quote=None)],
        children=[],
    )
    parent = OutlineNode(
        id="1", title="商务部分", level=1,
        sources=[
            SourceRef(type=SourceType.SKELETON, document="格式.docx", location="一", quote=None),
            SourceRef(type=SourceType.SCORING, document="评分.pdf", location="第3条", quote="提供..."),
        ],
        children=[child],
    )
    assert parent.children[0].title == "投标函"
    assert len(parent.sources) == 2  # 多来源


def test_coverage_report_unmapped():
    """覆盖率报告记录未挂载要求"""
    cov = CoverageReport(
        total_scoring_items=28, mapped_scoring_items=28,
        total_tech_items=10, mapped_tech_items=7,
        unmapped=["技术参数X响应", "技术参数Y响应", "技术参数Z响应"],
    )
    assert cov.mapped_scoring_items == cov.total_scoring_items
    assert len(cov.unmapped) == 3


def test_outline_tree_serializable():
    """OutlineTree 可序列化为 JSON 再还原"""
    tree = OutlineTree(
        project_name="测试项目",
        source_documents=["a.docx"],
        nodes=[OutlineNode(id="1", title="X", level=1, sources=[], children=[])],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )
    dumped = tree.model_dump_json()
    restored = OutlineTree.model_validate_json(dumped)
    assert restored.project_name == "测试项目"
    assert restored.nodes[0].title == "X"


def test_parsed_document_method_field():
    """ParsedDocument 记录抽取方式，便于追溯"""
    doc = ParsedDocument(filename="a.pdf", raw_markdown="# 标题", extract_method="pdf_text", page_count=5)
    assert doc.extract_method == "pdf_text"


def test_requirement_item():
    """RequirementItem 携带来源类型与建议标题"""
    item = RequirementItem(
        description="提供ISO9001认证",
        source_type=SourceType.SCORING,
        location="评分办法第3条",
        suggested_title="质量管理体系认证证书",
    )
    assert item.source_type == SourceType.SCORING
