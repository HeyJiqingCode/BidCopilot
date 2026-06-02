"""Word 导出测试"""
from pathlib import Path
import docx
from bid_copilot.models import OutlineTree, OutlineNode, SourceRef, SourceType, CoverageReport
from bid_copilot.understanding.output.word_export import export_to_docx


def _tree():
    return OutlineTree(
        project_name="测试项目",
        source_documents=["a.docx"],
        nodes=[
            OutlineNode(id="1", title="商务部分", level=1, sources=[
                SourceRef(type=SourceType.SKELETON, document="a.docx", location="一", quote=None)],
                children=[OutlineNode(id="1.1", title="投标函", level=2, sources=[], children=[])]),
            OutlineNode(id="2", title="项目实施组织方案", level=1, sources=[
                SourceRef(type=SourceType.AI_SUGGESTED, document="(AI建议)", location="-", quote=None)],
                children=[]),
        ],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )


def test_export_creates_headings(tmp_path):
    """导出的 docx 含对应层级 Heading"""
    out = tmp_path / "out.docx"
    export_to_docx(_tree(), out, keep_ai_marks=False)
    d = docx.Document(str(out))
    headings = [(p.text, p.style.name) for p in d.paragraphs if p.style.name.startswith("Heading")]
    texts = [t for t, _ in headings]
    assert "商务部分" in texts
    assert "投标函" in texts


def test_export_ai_mark_toggle(tmp_path):
    """keep_ai_marks=True 时 AI 建议节点标题带标注"""
    out = tmp_path / "out2.docx"
    export_to_docx(_tree(), out, keep_ai_marks=True)
    d = docx.Document(str(out))
    all_text = "\n".join(p.text for p in d.paragraphs)
    assert "AI建议" in all_text or "🤖" in all_text
