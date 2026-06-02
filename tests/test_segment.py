"""章节切分测试"""
from bid_copilot.understanding.segment import segment_text


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


def test_segment_trusts_markdown_headings_when_present():
    """含 # 标题时，正文里的“1. xxx”不应被误判为标题"""
    md = "# 第一章 投标须知\n1. 投标价格应完整填写。\n2. 投标有效期为90天。\n## 1、资格要求\n须满足资质。"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    assert any(t == "# 第一章 投标须知" for t in titles)
    assert any(t == "## 1、资格要求" for t in titles)
    assert not any(t.startswith("1. 投标价格") for t in titles)
    assert not any(t.startswith("2. 投标有效期") for t in titles)
    ch1 = next(s for s in sections if s.title == "# 第一章 投标须知")
    assert "投标价格应完整填写" in ch1.content


def test_segment_table_rows_not_titles_with_headings():
    """含 # 标题时，Markdown 表格行应作为正文，不被当标题"""
    md = "# 评分办法\n| 评分项 | 分值 |\n| --- | --- |\n| ISO9001 | 2分 |"
    sections = segment_text(md, doc_source="x.docx")
    titles = [s.title for s in sections]
    assert titles == ["# 评分办法"]
    body = sections[0].content
    assert "ISO9001" in body and "评分项" in body


def test_segment_falls_back_to_regex_without_headings():
    """无 # 标题的纯文本仍走正则兜底（不回退此能力）"""
    md = "第一章 总则\n正文A\n一、 适用范围\n正文B"
    sections = segment_text(md, doc_source="x.doc")
    titles = [(s.title, s.level) for s in sections]
    assert ("第一章 总则", 1) in titles
    assert any(t.startswith("一、") and lvl == 2 for t, lvl in titles)
