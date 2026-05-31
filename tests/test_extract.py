"""文本抽取测试"""
from pathlib import Path
import docx
from outline_extraction.parsing.extract import extract_document, _is_scanned


def test_extract_docx(tmp_path):
    """docx 抽取为 Markdown，方法标记 docx"""
    p = tmp_path / "a.docx"
    d = docx.Document()
    d.add_heading("第一章 总则", level=1)
    d.add_paragraph("这是正文。")
    d.save(p)
    result = extract_document(Path(p), ".docx")
    assert result.extract_method == "docx"
    assert "第一章 总则" in result.raw_markdown
    assert "这是正文。" in result.raw_markdown


def test_extract_docx_heading_becomes_markdown(tmp_path):
    """docx 标题转成 Markdown # 前缀"""
    p = tmp_path / "h.docx"
    d = docx.Document()
    d.add_heading("标题A", level=2)
    d.save(p)
    result = extract_document(Path(p), ".docx")
    assert "## 标题A" in result.raw_markdown


def test_is_scanned_threshold():
    """每页平均字符数低于阈值判为扫描件"""
    assert _is_scanned(total_chars=50, page_count=10) is True   # 5 字/页
    assert _is_scanned(total_chars=5000, page_count=10) is False  # 500 字/页


def test_extract_unknown_suffix(tmp_path):
    """未知后缀返回空 markdown 并标记 skipped，不报错"""
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x00\x01")
    result = extract_document(Path(p), ".bin")
    assert result.extract_method == "skipped"
    assert result.raw_markdown == ""
