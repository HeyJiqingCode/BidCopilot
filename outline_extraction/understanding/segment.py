"""章节切分——正则优先识别中文招标编号体系"""
import re
from outline_extraction.models import Section

# 编号模式 → 层级。顺序即优先级，先匹配先生效。
_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"^第[一二三四五六七八九十百]+[章篇]"), 1),       # 第一章
    (re.compile(r"^#{1,6}\s"), 0),                              # Markdown 标题（动态算级）
    (re.compile(r"^[一二三四五六七八九十]+、"), 2),               # 一、
    (re.compile(r"^（[一二三四五六七八九十]+）"), 3),             # （一）
    (re.compile(r"^\d+\.\d+\.\d+"), 3),                          # 1.1.1
    (re.compile(r"^\d+\.\d+"), 2),                               # 1.1
    (re.compile(r"^\d+\.?\s"), 1),                               # 1 / 1.
]


def segment_text(markdown: str, doc_source: str) -> list[Section]:
    """把文本按编号切成带层级的章节块

    参数:
        markdown: 文档的 Markdown 文本
        doc_source: 来源文件名
    返回:
        Section 列表；无法匹配任何标题时返回单个 level1 整篇块
    """
    lines = markdown.splitlines()
    sections: list[Section] = []
    current: Section | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        level = _match_level(stripped)
        if level is not None:
            current = Section(title=stripped, level=level, content="", doc_source=doc_source)
            sections.append(current)
        elif current is not None:
            current.content += stripped + "\n"
        else:
            # 标题前的前言：建一个 level1 容器
            current = Section(title="（前言）", level=1, content=stripped + "\n", doc_source=doc_source)
            sections.append(current)

    if not sections:
        sections.append(Section(title="（全文）", level=1, content=markdown, doc_source=doc_source))
    return sections


def _match_level(line: str) -> int | None:
    """返回该行作为标题的层级；非标题返回 None——内部辅助"""
    for pattern, level in _PATTERNS:
        if pattern.match(line):
            if level == 0:  # Markdown 标题：按 # 数量定级
                return min(len(line) - len(line.lstrip("#")), 6)
            return level
    return None
