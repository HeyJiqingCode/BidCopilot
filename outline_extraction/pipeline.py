"""编排管线——串联解析/理解/对齐/输出 9 步，dump 中间产物"""
import json
from pathlib import Path
from typing import Callable, Optional, Any
from outline_extraction.models import OutlineTree, ParsedDocument, Section
from outline_extraction.parsing.unpack import collect_files
from outline_extraction.parsing.extract import extract_document
from outline_extraction.understanding.classify import classify_documents
from outline_extraction.understanding.segment import segment_text
from outline_extraction.understanding.locate import locate_sections
from outline_extraction.understanding.extract_skeleton import extract_skeleton
from outline_extraction.understanding.extract_requirements import extract_requirements
from outline_extraction.alignment.merge import merge_requirements, compute_coverage, Disposition
from outline_extraction.alignment.supplement import supplement_tree
from outline_extraction.output.tree import finalize_ids


def run_pipeline(
    input_path: Path,
    llm,
    model_main: str,
    model_mini: str,
    run_dir: Path,
    progress_callback: Optional[Callable[[str, Any], None]] = None,
) -> OutlineTree:
    """执行完整大纲提取管线

    参数:
        input_path: 招标文件/文件包路径
        llm: LLMClient
        model_main: 主模型名（定位/抽取/对齐）
        model_mini: 小模型名（分类）
        run_dir: 中间产物输出目录
        progress_callback: 每步回调 (step_name, payload)
    返回:
        最终 OutlineTree
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    def _emit(step: str, payload: Any) -> None:
        """发进度并 dump 产物——内部辅助"""
        if progress_callback:
            progress_callback(step, payload)
        _dump(run_dir, step, payload)

    # 1. 解析
    files = collect_files(Path(input_path))
    docs: list[ParsedDocument] = [extract_document(Path(p), suf) for p, suf in files]
    _emit("parse", [d.model_dump() for d in docs])

    # 2. 分类
    classes = classify_documents(docs, llm=llm, model=model_mini)
    _emit("classify", {k: v.model_dump() for k, v in classes.items()})

    # 3. 切分（全文档汇总）
    sections = []
    for doc in docs:
        sections.extend(segment_text(doc.raw_markdown, doc_source=doc.filename))
    _emit("segment", [s.model_dump() for s in sections])

    # 4. 定位关键章节
    located = locate_sections(sections, llm=llm, model=model_main)
    _emit("locate", located.model_dump())

    # 5. 抽显式骨架（合并所有 bid_format 章节）
    #    定位到的是章节标题，其正文常被切分到后续子章节，故收集整段（标题+全部下级）。
    skeleton = []
    for i in located.bid_format_sections:
        sec = sections[i]
        span = _gather_span(sections, i)
        if not span.strip():
            continue
        skeleton.extend(extract_skeleton(span, document=sec.doc_source, llm=llm, model=model_main))
    _emit("extract_skeleton", [n.model_dump() for n in skeleton])

    # 6. 抽要求条目（评分+技术+商务章节）
    #    同样按整段收集；空段交由 extract_requirements 跳过。
    req_indices = located.scoring_sections + located.tech_spec_sections + located.business_sections
    req_texts = [_gather_span(sections, i) for i in req_indices]
    requirements = extract_requirements(req_texts, llm=llm, model=model_main)
    # 赋稳定唯一 ref_id，作为归并/覆盖率的关联键（location 非唯一、易被 LLM 改写）
    for idx, req in enumerate(requirements):
        req.ref_id = f"R{idx}"
    _emit("extract_requirements", [r.model_dump() for r in requirements])

    # 7. 归并 + 覆盖率
    merged_tree, decisions = merge_requirements(skeleton, requirements, llm=llm, model=model_main)
    coverage = compute_coverage(requirements, decisions)
    _emit("merge", {"tree": [n.model_dump() for n in merged_tree],
                    "coverage": coverage.model_dump()})

    # 8. 生成式兜底（游离要求）
    floating = [r.description for r, d in _pair_floating(requirements, decisions)]
    final_nodes = supplement_tree(merged_tree, floating=floating, llm=llm, model=model_main)
    _emit("supplement", [n.model_dump() for n in final_nodes])

    # 9. id 重整
    final_nodes = finalize_ids(final_nodes)

    tree = OutlineTree(
        project_name=Path(input_path).stem,
        source_documents=[d.filename for d in docs],
        nodes=final_nodes,
        coverage=coverage,
    )
    _emit("finalize", tree.model_dump())
    return tree


def _pair_floating(requirements, decisions):
    """配对出 floating 要求——内部辅助

    参数:
        requirements: 要求列表
        decisions: 归属判定
    返回:
        [(requirement, decision)] 仅 floating 项
    """
    disp_by_ref = {d.ref_id: d for d in decisions}
    pairs = []
    for req in requirements:
        d = disp_by_ref.get(req.ref_id)
        if d is None or d.disposition == Disposition.FLOATING:
            pairs.append((req, d))
    return pairs


def _gather_span(sections: list[Section], start: int) -> str:
    """收集某章节的完整文本——标题 + 其全部下级章节，直到遇到同级或更高级标题

    切分后一个逻辑章节常被拆成"标题段（正文空）+ 多个子段"，单看起始段会丢正文。
    本函数把起始段及其所有更深层级的后续段重新拼回完整文本，与具体标的无关。

    参数:
        sections: 全部章节（按文档顺序）
        start: 起始章节索引
    返回:
        拼接好的整段文本（标题与正文交错）
    """
    head = sections[start]
    parts: list[str] = [head.title]
    if head.content.strip():
        parts.append(head.content)
    for sec in sections[start + 1:]:
        if sec.doc_source != head.doc_source or sec.level <= head.level:
            break  # 跨文件或回到同级/更高级 → 本段结束
        parts.append(sec.title)
        if sec.content.strip():
            parts.append(sec.content)
    return "\n".join(parts)


def _dump(run_dir: Path, step: str, payload: Any) -> None:
    """把中间产物写成 JSON 文件——内部辅助"""
    path = run_dir / f"{step}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
