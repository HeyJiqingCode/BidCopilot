"""定位关键章节——用 5.4 语义识别投标格式/评分/技术/商务章节位置"""
from pathlib import Path
from pydantic import BaseModel, Field
from bid_copilot.models import Section

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "locate.txt"
# 每个章节摘要截断长度
_SUMMARY_CHARS = 450  # 加长摘要，让 LLM 看到评分项/技术参数/表格等内容特征，减少漏定位


class LocateResult(BaseModel):
    """四类关键章节的索引列表（对应输入 Section 顺序）"""
    bid_format_sections: list[int] = Field(default_factory=list)
    scoring_sections: list[int] = Field(default_factory=list)
    tech_spec_sections: list[int] = Field(default_factory=list)
    business_sections: list[int] = Field(default_factory=list)


def locate_sections(sections: list[Section], llm, model: str) -> LocateResult:
    """定位四类关键章节

    参数:
        sections: 全部章节
        llm: LLMClient
        model: 模型名（main）
    返回:
        LocateResult（各类章节索引）
    """
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    listing_lines: list[str] = []
    for idx, sec in enumerate(sections):
        summary = sec.content[:_SUMMARY_CHARS].replace("\n", " ")
        listing_lines.append(f"[{idx}] 文件={sec.doc_source} 标题={sec.title} 摘要={summary}")
    content = "章节列表：\n" + "\n".join(listing_lines)
    return llm.complete(
        model=model, instructions=instructions, input_content=content,
        effort="medium", verbosity="low", schema=LocateResult,
    )
