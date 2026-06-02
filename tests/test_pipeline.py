"""端到端管线测试——真实解析 + fake LLM"""
from pathlib import Path
import docx
from bid_copilot.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from bid_copilot.understanding.classify import FileClass, ClassifyResult
from bid_copilot.understanding.locate import LocateResult
from bid_copilot.understanding.extract_skeleton import SkeletonResult
from bid_copilot.understanding.extract_requirements import RequirementsResult
from bid_copilot.understanding.alignment.merge import (
    MergeResult, MergeDecision, Disposition, _NormalizeResult, _AttachResult, _DedupeResult,
)
from bid_copilot.understanding.alignment.supplement import SupplementResult
from bid_copilot.understanding.pipeline import run_pipeline


def _nodes_from_skeleton(kwargs):
    """从阶段A 的 input_content 还原骨架 OutlineNode 列表——测试辅助（规范化原样返回骨架）"""
    import json
    from bid_copilot.models import OutlineNode
    try:
        payload = json.loads(kwargs.get("input_content", "[]"))
    except Exception:
        payload = []
    return [OutlineNode(**n) for n in payload] if isinstance(payload, list) else []


class _ScriptedLLM:
    """脚本化 LLM：merge 三阶段（normalize/attach/dedupe）按 schema 自动应答，其余按 push 顺序返回。

    pipeline 测试只 push 业务步骤（classify/locate/skeleton/requirements/supplement）的返回，
    merge 内部拆成的多次调用由本类按 schema 兜底，测试无需关心 merge 调了几次。
    """
    def __init__(self):
        self.script = []
        self.idx = 0

    def push(self, result):
        self.script.append(result)

    def complete(self, **kwargs):
        schema = kwargs.get("schema")
        if schema is _NormalizeResult:                       # 阶段A：原样返回骨架
            return _NormalizeResult(tree=_nodes_from_skeleton(kwargs))
        if schema is _AttachResult:                          # 阶段B：空判定
            return _AttachResult()
        if schema is _DedupeResult:                          # 阶段C：空分组
            return _DedupeResult()
        r = self.script[self.idx]
        self.idx += 1
        return r


def _make_docx(path):
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.add_heading("投标函", level=2)
    d.save(path)


def test_run_pipeline_end_to_end(tmp_path):
    """管线跑通：解析真实 docx + 脚本化 LLM，产出 OutlineTree"""
    src = tmp_path / "fmt.docx"
    _make_docx(src)

    llm = _ScriptedLLM()
    # classify（1个文档）
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    # locate
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[],
                          tech_spec_sections=[], business_sections=[]))
    # extract_skeleton
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])]))
    # merge 内部三阶段由 _ScriptedLLM 按 schema 兜底（规范化原样返回骨架、无要求可挂），无需 push
    # supplement
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])]))

    steps_seen = []
    tree = run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                        run_dir=tmp_path / "run", progress_callback=lambda s, p: steps_seen.append(s))

    assert tree.nodes[0].title == "投标函"
    assert tree.nodes[0].id == "1"           # 已 finalize id
    assert "parse" in steps_seen
    assert "merge" in steps_seen


def test_run_pipeline_accepts_explicit_project_name(tmp_path):
    """run_pipeline 可显式指定 project_name，覆盖默认的 input_path.stem"""
    src = tmp_path / "input"
    src.mkdir()
    f = src / "fmt.docx"
    import docx
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.save(f)

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    # merge 三阶段由 _ScriptedLLM 按 schema 兜底
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    tree = run_pipeline(src, llm=llm, model_main="m", model_mini="mini",
                        run_dir=tmp_path / "run", project_name="淮能项目")
    assert tree.project_name == "淮能项目"


def test_pipeline_emits_detail_level_logs(tmp_path):
    """管线应发出带 level=detail 的细粒度日志事件（不止 main 摘要）"""
    src = tmp_path / "input"
    src.mkdir()
    f = src / "fmt.docx"
    import docx
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.save(f)

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    # merge 三阶段由 _ScriptedLLM 按 schema 兜底
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    events = []
    run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                 run_dir=tmp_path / "run", log_callback=lambda e: events.append(e))

    # 每个事件都带 level 字段
    assert all("level" in e for e in events)
    # 至少有一条 detail 级日志（细粒度），且提到模型或文件
    details = [e for e in events if e.get("level") == "detail"]
    assert len(details) >= 1
    # classify 阶段应有提到分类的 detail 日志
    assert any(e["phase"] == "classify" and e["level"] == "detail" for e in events)


def test_pipeline_detail_logs_cover_main_phases(tmp_path):
    """parse/locate/extract_skeleton/extract_requirements/merge 都应有 detail 日志"""
    src = tmp_path / "input"
    src.mkdir()
    f = src / "fmt.docx"
    import docx
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.add_paragraph("一、商务投标文件")
    d.save(f)

    from bid_copilot.understanding.extract_requirements import RequirementsResult
    from bid_copilot.models import RequirementItem

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[0], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(RequirementsResult(items=[RequirementItem(ref_id="", description="x", source_type=SourceType.SCORING, location="评1", suggested_title="X")]))
    # merge 三阶段由 _ScriptedLLM 按 schema 兜底
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    events = []
    run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                 run_dir=tmp_path / "run", log_callback=lambda e: events.append(e))

    phases_with_detail = {e["phase"] for e in events if e.get("level") == "detail"}
    for ph in ["parse", "locate", "extract_skeleton", "extract_requirements", "merge"]:
        assert ph in phases_with_detail, f"{ph} 缺少 detail 日志"


def test_pipeline_model_tier_routing(tmp_path):
    """models 档位映射：classify 走 mini、merge 显式配 mini 时也走 mini，其余 main"""
    src = tmp_path / "input"
    src.mkdir()
    f = src / "fmt.docx"
    d = docx.Document()
    d.add_heading("投标文件格式", level=1)
    d.save(f)

    used_models = []

    class _RecordingLLM(_ScriptedLLM):
        """记录每次调用所用 model，用于断言档位路由"""
        def complete(self, **kwargs):
            used_models.append(kwargs.get("model"))
            return super().complete(**kwargs)

    llm = _RecordingLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    run_pipeline(src, llm=llm, model_main="MAIN", model_mini="MINI",
                 run_dir=tmp_path / "run",
                 models={"classify": "mini", "locate": "main", "merge": "mini"})

    # classify 用 MINI；locate 用 MAIN；merge 阶段（规范化/挂载）显式配 mini → 用 MINI
    assert "MINI" in used_models    # classify
    assert "MAIN" in used_models    # locate/skeleton 等
