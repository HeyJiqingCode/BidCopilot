"""编排管线——串联解析/理解/对齐/输出 9 步，dump 中间产物"""
import json
from pathlib import Path
from typing import Callable, Optional, Any
from outline_extraction.models import OutlineTree, ParsedDocument
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
    skeleton = []
    for i in located.bid_format_sections:
        sec = sections[i]
        skeleton.extend(extract_skeleton(sec.content, document=sec.doc_source, llm=llm, model=model_main))
    _emit("extract_skeleton", [n.model_dump() for n in skeleton])

    # 6. 抽要求条目（评分+技术+商务章节）
    req_indices = located.scoring_sections + located.tech_spec_sections + located.business_sections
    req_texts = [sections[i].content for i in req_indices]
    requirements = extract_requirements(req_texts, llm=llm, model=model_main)
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
    disp_by_loc = {d.requirement_location: d for d in decisions}
    pairs = []
    for req in requirements:
        d = disp_by_loc.get(req.location)
        if d is None or d.disposition == Disposition.FLOATING:
            pairs.append((req, d))
    return pairs


def _dump(run_dir: Path, step: str, payload: Any) -> None:
    """把中间产物写成 JSON 文件——内部辅助"""
    path = run_dir / f"{step}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
