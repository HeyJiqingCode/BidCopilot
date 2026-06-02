"""文件分类——用 mini 读文件名+正文开头判定文件类型"""
from enum import Enum
from pathlib import Path
from pydantic import BaseModel
from bid_copilot.models import ParsedDocument

# 喂给 LLM 的正文前缀长度
_PREVIEW_CHARS = 1500
_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "classify.txt"


class FileClass(str, Enum):
    """文件类型枚举"""
    TENDER_MAIN = "tender_main"
    TECH_SPEC = "tech_spec"
    BUSINESS = "business"
    BID_FORMAT = "bid_format"
    ADDENDUM = "addendum"
    UNKNOWN = "unknown"


class ClassifyResult(BaseModel):
    """单文件分类结果"""
    file_class: FileClass
    confidence: float


def classify_documents(docs: list[ParsedDocument], llm, model: str) -> dict[str, ClassifyResult]:
    """对每个文档分类

    参数:
        docs: 已解析文档列表
        llm: LLMClient（或兼容的 complete 接口）
        model: 模型名（mini）
    返回:
        {文件名: ClassifyResult}
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    out: dict[str, ClassifyResult] = {}
    for doc in docs:
        preview = doc.raw_markdown[:_PREVIEW_CHARS]
        content = f"文件名：{doc.filename}\n正文开头：\n{preview}"
        result = llm.complete(
            model=model, instructions=instructions, input_content=content,
            effort="low", verbosity="low", schema=ClassifyResult,
        )
        out[doc.filename] = result
    return out
