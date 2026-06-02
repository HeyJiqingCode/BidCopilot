"""端到端管线测试——真实解析 + fake LLM"""
from pathlib import Path
import docx
from outline_extraction.models import (
    OutlineNode, SourceRef, SourceType, RequirementItem,
)
from outline_extraction.understanding.classify import FileClass, ClassifyResult
from outline_extraction.understanding.locate import LocateResult
from outline_extraction.understanding.extract_skeleton import SkeletonResult
from outline_extraction.understanding.extract_requirements import RequirementsResult
from outline_extraction.alignment.merge import MergeResult, MergeDecision, Disposition
from outline_extraction.alignment.supplement import SupplementResult
from outline_extraction.pipeline import run_pipeline


class _ScriptedLLM:
    """按调用顺序返回脚本化结果，模拟各步 LLM 输出"""
    def __init__(self):
        self.script = []
        self.idx = 0

    def push(self, result):
        self.script.append(result)

    def complete(self, **kwargs):
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
    # merge（无要求条目，直接返回骨架）
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[
        SourceRef(type=SourceType.SKELETON, document="fmt.docx", location="一", quote=None)], children=[])],
        decisions=[]))
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

    from outline_extraction.understanding.classify import FileClass, ClassifyResult
    from outline_extraction.understanding.locate import LocateResult
    from outline_extraction.understanding.extract_skeleton import SkeletonResult
    from outline_extraction.alignment.merge import MergeResult
    from outline_extraction.alignment.supplement import SupplementResult
    from outline_extraction.models import OutlineNode

    class _ScriptedLLM:
        def __init__(self):
            self.script = []
            self.idx = 0
        def push(self, r):
            self.script.append(r)
        def complete(self, **kwargs):
            r = self.script[self.idx]; self.idx += 1; return r

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])], decisions=[]))
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    from outline_extraction.pipeline import run_pipeline
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

    from outline_extraction.understanding.classify import FileClass, ClassifyResult
    from outline_extraction.understanding.locate import LocateResult
    from outline_extraction.understanding.extract_skeleton import SkeletonResult
    from outline_extraction.alignment.merge import MergeResult
    from outline_extraction.alignment.supplement import SupplementResult
    from outline_extraction.models import OutlineNode

    class _ScriptedLLM:
        def __init__(self):
            self.script = []; self.idx = 0
        def push(self, r): self.script.append(r)
        def complete(self, **kwargs):
            r = self.script[self.idx]; self.idx += 1; return r

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])], decisions=[]))
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    events = []
    from outline_extraction.pipeline import run_pipeline
    run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                 run_dir=tmp_path / "run", log_callback=lambda e: events.append(e))

    # 每个事件都带 level 字段
    assert all("level" in e for e in events)
    # 至少有一条 detail 级日志（细粒度），且提到模型或文件
    details = [e for e in events if e.get("level") == "detail"]
    assert len(details) >= 1
    # classify 阶段应有提到分类的 detail 日志
    assert any(e["phase"] == "classify" and e["level"] == "detail" for e in events)
