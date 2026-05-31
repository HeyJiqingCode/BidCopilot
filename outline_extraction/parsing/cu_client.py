"""Content Understanding 封装——扫描件 OCR + 复杂表格还原（阶段二）"""
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel


class CUResult(BaseModel):
    """CU 分析结果"""
    markdown: str          # 结构化 Markdown（含表格）
    page_count: Optional[int] = None


def analyze_with_cu(file_path: Path, cu: Any) -> CUResult:
    """用 Content Understanding 分析文件

    参数:
        file_path: 待分析文件
        cu: CU 客户端（须有 analyze(path)->CUResult）；None 表示未配置
    返回:
        CUResult；cu 为 None 时返回空 markdown（优雅降级）
    """
    if cu is None:
        return CUResult(markdown="", page_count=None)
    return cu.analyze(file_path)
