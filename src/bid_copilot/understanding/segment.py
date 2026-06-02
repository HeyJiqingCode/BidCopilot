"""章节切分——正则优先识别中文招标编号体系"""
import re
from bid_copilot.models import Section

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

    优先信任 docx 原生 Markdown 标题：若全文存在以 # 开头的标题行，则只用 # 作为标题
    来源（# 数量即层级），其余行一律视为正文——避免正则把正文/表格行误判为标题。
    若全文无 # 标题（如 textutil 抽取的纯文本 .doc），退回正则编号识别。

    参数:
        markdown: 文档的 Markdown 文本
        doc_source: 来源文件名
    返回:
        Section 列表；无法匹配任何标题时返回单个 level1 整篇块
    """
    lines = markdown.splitlines()
    has_md_heading = any(_md_heading_level(line.strip()) for line in lines if line.strip())

    sections: list[Section] = []
    current: Section | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if has_md_heading:
            level = _md_heading_level(stripped)
        else:
            level = _match_level(stripped)
        if level is not None:
            current = Section(title=stripped, level=level, content="", doc_source=doc_source)
            sections.append(current)
        elif current is not None:
            current.content += stripped + "\n"
        else:
            current = Section(title="（前言）", level=1, content=stripped + "\n", doc_source=doc_source)
            sections.append(current)

    if not sections:
        sections.append(Section(title="（全文）", level=1, content=markdown, doc_source=doc_source))
    return sections


def _md_heading_level(line: str) -> int | None:
    """若该行是 Markdown 标题（# 开头且 # 后有空格），返回层级，否则 None——内部辅助

    参数:
        line: 已 strip 的行文本
    返回:
        层级（# 个数，封顶 6）或 None
    """
    if not line.startswith("#"):
        return None
    hashes = len(line) - len(line.lstrip("#"))
    rest = line[hashes:]
    if hashes >= 1 and rest.startswith(" "):
        return min(hashes, 6)
    return None


def _match_level(line: str) -> int | None:
    """返回该行作为标题的层级；非标题返回 None——内部辅助"""
    for pattern, level in _PATTERNS:
        if pattern.match(line):
            if level == 0:  # Markdown 标题：按 # 数量定级
                return min(len(line) - len(line.lstrip("#")), 6)
            return level
    return None
