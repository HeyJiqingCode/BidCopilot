"""核心数据模型——系统所有环节流转的统一契约"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """大纲节点来源类型——Demo 可信度展示的关键"""
    SKELETON = "skeleton"        # 投标文件组成/格式（显式骨架）
    SCORING = "scoring"          # 评分办法
    TECH_SPEC = "tech_spec"      # 技术规范书
    BIZ_TERMS = "biz_terms"      # 商务条款
    AI_SUGGESTED = "ai_suggested"  # AI 生成式兜底


class SourceRef(BaseModel):
    """单条来源溯源——说明该标题为何存在"""
    type: SourceType                       # 来源类型
    document: str                          # 来源文件名
    location: str                          # 章节定位，如"七、技术建议书"
    quote: Optional[str] = None            # 原文摘录（可选）
    ref_ids: list[str] = Field(default_factory=list)  # 该来源覆盖的要求 ref_id（用于从树推导覆盖率）


class OutlineNode(BaseModel):
    """大纲树节点——一个投标文件标题"""
    id: str                                # 路径式稳定 id，如 "3.2.1"
    title: str                             # 标题文本
    level: int                             # 层级 1/2/3，映射 Word Heading
    sources: list[SourceRef] = Field(default_factory=list)  # 多来源
    children: list["OutlineNode"] = Field(default_factory=list)  # 子节点
    note: Optional[str] = None             # 应答提示（可选）


class CoverageReport(BaseModel):
    """覆盖率自检——抽取到的要求有多少落进大纲"""
    total_scoring_items: int               # 评分点总数
    mapped_scoring_items: int              # 已对齐评分点数
    total_tech_items: int                  # 技术条目总数
    mapped_tech_items: int                 # 已对齐技术条目数
    total_biz_items: int = 0               # 商务要求总数
    mapped_biz_items: int = 0              # 已对齐商务要求数
    unmapped: list[str] = Field(default_factory=list)  # 未挂载要求（告警）


class OutlineTree(BaseModel):
    """完整大纲 + 元信息"""
    project_name: str                      # 项目名
    source_documents: list[str]            # 参与生成的文件清单
    nodes: list[OutlineNode]               # 顶层节点
    coverage: CoverageReport               # 覆盖率报告


class ParsedDocument(BaseModel):
    """解析层输出——单个文件的统一表示"""
    filename: str                          # 文件名
    raw_markdown: str                      # 统一 Markdown 全文
    extract_method: str                    # docx/textutil/pdf_text/cu_ocr
    page_count: Optional[int] = None       # 页数（PDF）


class Section(BaseModel):
    """章节切分结果——一个带层级的章节块"""
    title: str                             # 章节标题
    level: int                             # 层级
    content: str                           # 章节正文
    doc_source: str                        # 所属文件名


class RequirementItem(BaseModel):
    """从评分/技术规范抽取的单条要求"""
    ref_id: str = ""                       # 稳定唯一关联键（如 R0/R1…），由管线赋值，供归并回填
    description: str                       # 要求描述
    source_type: SourceType                # 来源类型
    location: str                          # 原文定位
    suggested_title: str                   # 建议对应的投标章节标题
    is_param_table: bool = False           # True=该条是整张技术参数表的聚合（投标方在技术参数响应表统一应答），非逐行要求
