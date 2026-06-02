"""编排管线——串联解析/理解/对齐/输出 9 步，dump 中间产物"""
import json
from collections import Counter
from pathlib import Path
from typing import Callable, Optional, Any
from bid_copilot.models import OutlineTree, ParsedDocument, Section, OutlineNode, SourceType
from bid_copilot.parsing.unpack import collect_files
from bid_copilot.parsing.extract import extract_document
from bid_copilot.understanding.classify import classify_documents
from bid_copilot.understanding.segment import segment_text
from bid_copilot.understanding.locate import locate_sections
from bid_copilot.understanding.extract_skeleton import extract_skeleton
from bid_copilot.understanding.extract_requirements import extract_requirements
from bid_copilot.understanding.alignment.merge import merge_requirements, compute_coverage, _collect_ref_ids
from bid_copilot.understanding.alignment.supplement import supplement_tree
from bid_copilot.understanding.output.tree import finalize_ids

# 来源类型 → 中文标签（日志摘要用）
_SOURCE_LABELS = {
    SourceType.SCORING: "评分",
    SourceType.TECH_SPEC: "技术",
    SourceType.BIZ_TERMS: "商务",
}


def run_pipeline(
    input_path: Path,
    llm,
    model_main: str,
    model_mini: str,
    run_dir: Path,
    model_nano: str = "",
    progress_callback: Optional[Callable[[str, Any], None]] = None,
    log_callback: Optional[Callable[[dict], None]] = None,
    project_name: Optional[str] = None,
    cu: Any = None,
    efforts: Optional[dict] = None,
    max_concurrency: int = 5,
    models: Optional[dict] = None,
) -> OutlineTree:
    """执行完整大纲提取管线

    参数:
        input_path: 招标文件/文件包路径
        llm: LLMClient
        model_main: 主模型名（定位/抽取/对齐）
        model_mini: 小模型名（分类）
        run_dir: 中间产物输出目录
        model_nano: 最轻量模型名（nano 档）；缺省空串时 nano 档回退到 model_mini
        progress_callback: 每步回调 (step_name, payload)，用于 dump 等
        log_callback: 阶段级结构化日志回调，接收 {"phase","status","message","level"}，供前端实时展示
        project_name: 显式项目名；缺省用 input_path.stem
        cu: CU 客户端，缺省 None（仅本地抽取）
        efforts: 各步推理强度字典 {classify,locate,skeleton,requirements,merge,supplement}；
                 缺省 None 时各步用自身默认值（维持现状）
        max_concurrency: 并行上限（extract 章节并行 + merge 阶段B 分批并行共用），默认 5
        models: 各步模型档位字典 {classify,locate,...: "main"|"mini"}；缺省时 classify 用 mini、其余 main
    返回:
        最终 OutlineTree
    """
    efforts = efforts or {}
    models = models or {}

    # 档位（main/mini/nano）→ 实际模型名。各步默认：classify=mini，其余 main
    # nano 档：用 model_nano；若未配置 model_nano（空串）则回退到 model_mini，避免传空模型名
    def _pick(step: str, default_tier: str) -> str:
        """按步骤档位选模型名——内部辅助

        参数:
            step: 步骤名（classify/locate/.../supplement）
            default_tier: 该步默认档位（main/mini/nano）
        返回:
            档位对应的实际模型名；nano 档未配置时回退 mini
        """
        tier = models.get(step, default_tier)
        if tier == "nano":
            return model_nano or model_mini
        if tier == "mini":
            return model_mini
        return model_main

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    def _emit(step: str, payload: Any) -> None:
        """发进度并 dump 产物——内部辅助"""
        if progress_callback:
            progress_callback(step, payload)
        _dump(run_dir, step, payload)

    def _log(phase: str, status: str, message: str = "", level: str = "main") -> None:
        """发阶段级结构化日志——内部辅助

        参数:
            phase: 阶段名
            status: start（开始）/ progress（阶段内子进度）/ done（完成摘要）
            message: 中文摘要
            level: main（阶段主摘要）/ detail（细粒度子进度），供前端分样式
        返回: 无
        """
        if log_callback:
            log_callback({"phase": phase, "status": status, "message": message, "level": level})

    # 1. 解析
    _log("parse", "start")
    files = collect_files(Path(input_path))
    docs: list[ParsedDocument] = []
    for p, suf in files:
        fname = Path(p).name
        if suf != ".docx" and cu is not None:
            _log("parse", "progress", f"尝试用 Content Understanding 解析《{fname}》", level="detail")
        else:
            _log("parse", "progress", f"本地解析《{fname}》", level="detail")
        docs.append(extract_document(Path(p), suf, cu=cu))
    _emit("parse", [d.model_dump() for d in docs])
    method_stat = ", ".join(f"{c}*{m}" for m, c in Counter(d.extract_method for d in docs).items())
    _log("parse", "done", f"解析完成：{len(docs)} 个文件（{method_stat}）")

    # 2. 分类
    _log("classify", "start")
    for i, doc in enumerate(docs, 1):
        _log("classify", "progress", f"调用 {_pick('classify', 'mini')} 分类《{doc.filename}》（{i}/{len(docs)}）", level="detail")
    classes = classify_documents(docs, llm=llm, model=_pick("classify", "mini"), effort=efforts.get("classify", "low"))
    _emit("classify", {k: v.model_dump() for k, v in classes.items()})
    class_stat = ", ".join(f"{cnt}*{cls}" for cls, cnt in
                           Counter(v.file_class.value for v in classes.values()).items())
    _log("classify", "done", f"分类完成：{class_stat}")

    # 3. 切分（全文档汇总）
    _log("segment", "start")
    sections = []
    for doc in docs:
        sections.extend(segment_text(doc.raw_markdown, doc_source=doc.filename))
    _emit("segment", [s.model_dump() for s in sections])
    _log("segment", "done", f"切分完成：共 {len(sections)} 个章节块")

    # 4. 定位关键章节
    _log("locate", "start")
    _log("locate", "progress", f"调用 {_pick('locate', 'main')} 定位关键章节（{len(sections)} 个章节块）", level="detail")
    located = locate_sections(sections, llm=llm, model=_pick("locate", "main"), effort=efforts.get("locate", "medium"))
    _emit("locate", located.model_dump())
    _log("locate", "done",
         f"定位完成：投标格式 {len(located.bid_format_sections)} 处、"
         f"评分 {len(located.scoring_sections)} 处、"
         f"技术 {len(located.tech_spec_sections)} 处、"
         f"商务 {len(located.business_sections)} 处")

    # 5. 抽显式骨架（合并所有 bid_format 章节）
    #    定位到的是章节标题，其正文常被切分到后续子章节，故收集整段（标题+全部下级）。
    _log("extract_skeleton", "start")
    skeleton = []
    _bid_n = len(located.bid_format_sections)
    for _k, i in enumerate(located.bid_format_sections, 1):
        sec = sections[i]
        span = _gather_span(sections, i)
        if not span.strip():
            continue
        _log("extract_skeleton", "progress",
             f"调用 {_pick('skeleton', 'main')} 抽取骨架（bid_format 章节 {_k}/{_bid_n}：{sec.title[:20]}）", level="detail")
        skeleton.extend(extract_skeleton(span, document=sec.doc_source, llm=llm, model=_pick("skeleton", "main"), effort=efforts.get("skeleton", "medium")))
    _emit("extract_skeleton", [n.model_dump() for n in skeleton])
    _log("extract_skeleton", "done", f"骨架抽取完成：{len(skeleton)} 个顶层标题")

    # 6. 抽要求条目（评分+技术+商务章节）
    #    同样按整段收集；空段交由 extract_requirements 跳过。
    _log("extract_requirements", "start")
    req_indices = located.scoring_sections + located.tech_spec_sections + located.business_sections
    req_texts = [_gather_span(sections, i) for i in req_indices]
    _log("extract_requirements", "progress",
         f"调用 {_pick('requirements', 'main')} 抽取要求（{len(req_texts)} 个关键章节）", level="detail")
    requirements = extract_requirements(req_texts, llm=llm, model=_pick("requirements", "main"), effort=efforts.get("requirements", "medium"), max_concurrency=max_concurrency)
    # 赋稳定唯一 ref_id，作为归并/覆盖率的关联键（location 非唯一、易被 LLM 改写）
    for idx, req in enumerate(requirements):
        req.ref_id = f"R{idx}"
    _emit("extract_requirements", [r.model_dump() for r in requirements])
    req_stat = ", ".join(f"{cnt}*{_SOURCE_LABELS.get(st, st.value)}" for st, cnt in
                         Counter(r.source_type for r in requirements).items())
    _log("extract_requirements", "done",
         f"要求抽取完成：共 {len(requirements)} 条" + (f"（{req_stat}）" if req_stat else ""))

    # 7. 归并（覆盖率延后到最终树上统计）
    _log("merge", "start")
    _log("merge", "progress", f"调用 {_pick('merge', 'main')} 归并 {len(requirements)} 条要求到骨架", level="detail")
    # decisions 不再用于挑 floating（改按树的真相判定，见 _unplaced_requirements），故忽略
    merged_tree, _decisions = merge_requirements(skeleton, requirements, llm=llm, model=_pick("merge", "main"), effort=efforts.get("merge", "high"), max_concurrency=max_concurrency)
    _emit("merge", {"tree": [n.model_dump() for n in merged_tree]})
    _log("merge", "done", f"归并完成：{len(merged_tree)} 个顶层标题")

    # 8. 生成式兜底（安置实际未挂进树的要求）
    #    "未挂进树"按归并树的真相判定（_collect_ref_ids），而非 merge 的 disposition——
    #    杜绝"判了可挂但 node_id 无效、静默丢弃"的要求两头落空（详见 _unplaced_requirements）。
    #    真·无未挂要求时直接跳过：supplement 没事可做，既白等一轮、又有扰动已正确树的风险。
    _log("supplement", "start")
    floating = [r.description for r in _unplaced_requirements(requirements, merged_tree)]
    if floating:
        _log("supplement", "progress", f"调用 {_pick('supplement', 'main')} 生成式补充（{len(floating)} 条游离要求）", level="detail")
        final_nodes = supplement_tree(merged_tree, floating=floating, llm=llm, model=_pick("supplement", "main"), effort=efforts.get("supplement", "high"))
        _log("supplement", "done", f"生成式补充完成：游离要求 {len(floating)} 条待安置")
    else:
        final_nodes = merged_tree                       # 无游离要求，跳过 LLM 调用
        _log("supplement", "done", "无游离要求，跳过生成式补充")
    _emit("supplement", [n.model_dump() for n in final_nodes])

    # 9. id 重整
    _log("finalize", "start")
    final_nodes = finalize_ids(final_nodes)

    # 覆盖率：在最终树（含 supplement 安置的节点）上从树推导，绑定真实产物
    coverage = compute_coverage(requirements, final_nodes)

    tree = OutlineTree(
        project_name=project_name or Path(input_path).stem,
        source_documents=[d.filename for d in docs],
        nodes=final_nodes,
        coverage=coverage,
    )
    _emit("finalize", tree.model_dump())
    _log("finalize", "done",
         f"完成：大纲共 {_count_nodes(final_nodes)} 个标题；"
         f"覆盖率 评分{coverage.mapped_scoring_items}/{coverage.total_scoring_items}、"
         f"技术{coverage.mapped_tech_items}/{coverage.total_tech_items}、"
         f"商务{coverage.mapped_biz_items}/{coverage.total_biz_items}")
    return tree


def _count_nodes(nodes: list[OutlineNode]) -> int:
    """递归统计大纲树节点总数——内部辅助

    参数:
        nodes: 顶层节点列表
    返回:
        含所有子级的节点总数
    """
    total = 0
    for node in nodes:
        total += 1 + _count_nodes(node.children)
    return total


def _unplaced_requirements(requirements: list, merged_tree: list[OutlineNode]) -> list:
    """挑出"实际没挂进归并树"的要求——内部辅助，供 supplement 兜底

    为什么按树的真相判定、而非按 decisions 的 disposition：
    merge 的判定有随机性，偶尔会把某条要求判成 merged_into/child_of 但 node_id
    无效（LLM 臆造/飘移），工程回填时静默跳过——这条要求既没真正进树、disposition
    又不是 floating，于是旧逻辑（看 disposition）不会把它交给 supplement，导致它
    两头落空、彻底丢失（漏项=废标）。改为：凡 ref_id 未真实出现在树 sources.ref_ids
    中的要求，都视为待安置，交 supplement。与 compute_coverage 同一真相源
    （_collect_ref_ids），二者自洽。

    参数:
        requirements: 全部要求条目（带稳定 ref_id）
        merged_tree: 归并后的树顶层节点
    返回:
        未挂进树的要求列表
    """
    mapped = _collect_ref_ids(merged_tree)
    return [r for r in requirements if r.ref_id not in mapped]


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
