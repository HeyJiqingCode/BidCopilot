"""文本抽取——探测优先决策链，统一输出 Markdown"""
import subprocess
from pathlib import Path
import docx
import pdfplumber
from outline_extraction.models import ParsedDocument

# 扫描件判定阈值：每页平均字符数低于此值视为扫描件
_SCANNED_CHARS_PER_PAGE = 50


def extract_document(file_path: Path, suffix: str) -> ParsedDocument:
    """按后缀走探测优先决策链抽取文本

    参数:
        file_path: 文件路径
        suffix: 小写后缀
    返回:
        ParsedDocument（含统一 Markdown 与抽取方式标记）
    """
    name = file_path.name
    if suffix == ".docx":
        return ParsedDocument(filename=name, raw_markdown=_docx_to_md(file_path),
                              extract_method="docx", page_count=None)
    if suffix == ".doc":
        return ParsedDocument(filename=name, raw_markdown=_doc_to_md(file_path),
                              extract_method="textutil", page_count=None)
    if suffix == ".pdf":
        return _pdf_to_doc(file_path, name)
    if suffix == ".xml":
        return ParsedDocument(filename=name, raw_markdown=file_path.read_text(errors="ignore"),
                              extract_method="xml", page_count=None)
    return ParsedDocument(filename=name, raw_markdown="", extract_method="skipped", page_count=None)


def _docx_to_md(file_path: Path) -> str:
    """docx → Markdown：Heading 样式转 # 前缀——内部辅助"""
    d = docx.Document(str(file_path))
    lines: list[str] = []
    for para in d.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "") if para.style else ""
        if style.startswith("Heading"):
            try:
                level = int(style.split()[-1])
            except (ValueError, IndexError):
                level = 1
            lines.append("#" * min(level, 6) + " " + text)
        else:
            lines.append(text)
    # 表格转 Markdown 表格
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _doc_to_md(file_path: Path) -> str:
    """.doc → 文本：调用 macOS textutil 子进程——内部辅助"""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(file_path)],
        capture_output=True, text=True,
    )
    return result.stdout


def _pdf_to_doc(file_path: Path, name: str) -> ParsedDocument:
    """PDF：抽文本层；字符过少标记 needs_ocr 留待 CU——内部辅助"""
    text_parts: list[str] = []
    page_count = 0
    with pdfplumber.open(str(file_path)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    full = "\n".join(text_parts)
    if _is_scanned(len(full.strip()), page_count):
        return ParsedDocument(filename=name, raw_markdown=full,
                              extract_method="needs_ocr", page_count=page_count)
    return ParsedDocument(filename=name, raw_markdown=full,
                          extract_method="pdf_text", page_count=page_count)


def _is_scanned(total_chars: int, page_count: int) -> bool:
    """判断 PDF 是否为扫描件——与具体文件无关的通用指标

    参数:
        total_chars: 抽到的总字符数
        page_count: 页数
    返回:
        True 表示疑似扫描件（每页平均字符数过低）
    """
    if page_count <= 0:
        return total_chars == 0
    return (total_chars / page_count) < _SCANNED_CHARS_PER_PAGE
