"""章节切分测试"""
from outline_extraction.understanding.segment import segment_text


def test_segment_chapter_and_subsection():
    """识别"第X章"为 level1，"一、"为 level2"""
    md = "第一章 投标须知\n正文A\n一、 总则\n正文B\n二、 资格\n正文C"
    sections = segment_text(md, doc_source="x.docx")
    titles = [(s.title, s.level) for s in sections]
    assert ("第一章 投标须知", 1) in titles
    assert any(t.startswith("一、") and lvl == 2 for t, lvl in titles)


def test_segment_decimal_numbering():
    """识别 1.1 为子级编号"""
    md = "1 概述\n内容\n1.1 背景\n内容\n1.2 目标\n内容"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    assert any("1.1" in t for t in titles)


def test_segment_content_attached():
    """正文挂到对应章节"""
    md = "第一章 总则\n这是总则正文。\n第二章 范围\n这是范围正文。"
    sections = segment_text(md, doc_source="x.docx")
    first = next(s for s in sections if "第一章" in s.title)
    assert "总则正文" in first.content


def test_segment_doc_source_recorded():
    """每段记录来源文件名"""
    md = "第一章 X\n内容"
    sections = segment_text(md, doc_source="abc.docx")
    assert sections[0].doc_source == "abc.docx"
