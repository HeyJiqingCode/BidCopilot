# 前端实时日志 + 历史记录 + 配色 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Demo 前端加：阶段内细粒度滚动日志（自动展开/收起/可手动展开）、历史 run 左侧边栏（刷新可加载回看）、一个品牌色+功能色的配色，并把日志/元信息落盘到 runs。

**Architecture:** 纯展示/可观测层 + 落盘，不改管线理解逻辑。pipeline 的 log_callback 升级为发 `{phase,status,message,level}` 细粒度事件；API worker 把事件落盘 logs.jsonl + 写 meta.json，新增 /api/runs 与 /api/runs/{id}/logs，tree 端点从 finalize.json 兜底；前端两栏布局 + 按阶段归集日志 + Alpine 状态机。

**Tech Stack:** Python 3.14（`.venv`）、FastAPI、pytest、Alpine.js + Tailwind（CDN）、Chrome DevTools 截图验证。

**贯穿约定：**
- 跑测试：`.venv/bin/pytest`；起服务：`PYTHONPATH=. .venv/bin/uvicorn outline_extraction.api.main:app --port 8131`。
- commit 结尾加：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- 工具调用单独发、不夹叙述（控制方纪律）。
- **本计划第一个 commit 要顺带把已改但未提交的 B 方案 prompt（locate.txt + extract_skeleton.txt）一起提交**（见 Task 0）。

---

## 现状关键事实（实现时遵守）

- `pipeline.run_pipeline(... log_callback ...)` 已存在，`_log(phase,status,message)` 只发 start/done 两条。事件结构现为 `{"phase","status","message"}`，**本计划加 `level` 字段**。
- `api/main.py`：`_worker` 内 `_log_cb(event)` 把 event `q.put` 推 SSE；`run_pipeline(..., log_callback=_log_cb, project_name=proj, cu=cu)`。`UPLOAD_STORE[run_id]` 指 input 目录。`TREE_STORE` 内存存树。`_DONE` 哨兵。SSE 端点 `/api/progress/{id}` 已存在。
- `runs/<id>/` 已落盘 9 个 `*.json`（含 finalize.json）+ input/。**未落盘 logs/meta**。
- 前端 `web/app.js`：Alpine 组件，状态 `runId/fileNames/running/phases/errorMsg/tree/keepAiMarks`；`PHASE_DEFS` 9 阶段；`applyPhaseEvent(ev)` 处理 start→running/done→push message 到 `p.logs`。`web/index.html` 单栏 + 中性灰配色。
- 前端 SSE 已在 `run()` 里用 EventSource 接 `/api/progress/{id}`，收 `{event:"done"}`/`{event:"error"}`/普通事件。

---

## 文件结构（改动地图）

| 文件 | 改什么 |
|---|---|
| `outline_extraction/llm/prompts/locate.txt`、`extract_skeleton.txt` | （已改未提交）随 Task 0 提交 |
| `outline_extraction/pipeline.py` | `_log` 加 level 参数；各阶段加 `progress`/`level=detail` 细日志 |
| `outline_extraction/api/main.py` | worker 落盘 logs.jsonl + meta.json；新增 /api/runs、/api/runs/{id}/logs；tree 从 finalize.json 兜底 |
| `web/index.html` | 两栏布局 + 历史边栏 + 阶段日志窗 + 配色 |
| `web/app.js` | 历史加载/回看、按阶段归集 detail 日志、展开收起 |
| `tests/test_api.py` | 新端点测试 |
| `tests/test_pipeline.py` | 细日志事件断言 |

---

## Task 0：提交 B 方案 prompt 改动 + 加 level 字段基础

**Files:**
- 已改未提交：`outline_extraction/llm/prompts/locate.txt`、`outline_extraction/llm/prompts/extract_skeleton.txt`
- Modify: `outline_extraction/pipeline.py`（`_log` 加 level 参数）
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 先单独提交 B 方案 prompt（验证已通过、不混入新功能）**

```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
git add outline_extraction/llm/prompts/locate.txt outline_extraction/llm/prompts/extract_skeleton.txt
git commit -m "fix: locate excludes bidder-instructions clauses; skeleton extracts hierarchy from numbered body text

盲测淮能暴露：顶层骨架被须知条款号(8/9/10/13)污染、正文整句被当标题。
locate prompt 明确排除'投标人须知'流程条款、只认投标文件构成/格式；
extract_skeleton prompt 改为从中文编号(一/（1）/①)推断层级、排除条款正文、产出短标题。
重跑淮能验证：顶层回归 商务/价格/技术投标文件，标题简洁，层级正确。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 2: 写失败测试（_log 带 level）**

在 `tests/test_pipeline.py` 末尾追加：
```python
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
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py::test_pipeline_emits_detail_level_logs -v`
Expected: FAIL（当前事件无 level 字段）

- [ ] **Step 4: 给 `_log` 加 level 参数**

修改 `outline_extraction/pipeline.py` 的 `_log`（当前 61-71 行）为：
```python
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
```

- [ ] **Step 5: 在 classify 阶段加一条 detail 日志（最小让测试过）**

修改 `outline_extraction/pipeline.py` 第 2 步（当前 81-87 行），在 `classify_documents` 调用前加 detail 日志。把第 2 步改为：
```python
    # 2. 分类
    _log("classify", "start")
    for i, doc in enumerate(docs, 1):
        _log("classify", "progress", f"调用 {model_mini} 分类《{doc.filename}》（{i}/{len(docs)}）", level="detail")
    classes = classify_documents(docs, llm=llm, model=model_mini)
    _emit("classify", {k: v.model_dump() for k, v in classes.items()})
    class_stat = ", ".join(f"{cls}×{cnt}" for cls, cnt in
                           Counter(v.file_class.value for v in classes.values()).items())
    _log("classify", "done", f"分类完成：{class_stat}")
```
（注：这里 detail 日志在调用前批量发，简单且不改 classify_documents 内部。其余阶段在 Task 1 补全。）

- [ ] **Step 6: 运行确认通过**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全部 passed

- [ ] **Step 7: Commit**

```bash
git add outline_extraction/pipeline.py tests/test_pipeline.py
git commit -m "feat: log events carry level (main/detail) for granular UI logs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1：pipeline 各阶段补全 detail 细日志

**Files:**
- Modify: `outline_extraction/pipeline.py`（各阶段加 progress/detail 日志）
- Test: `tests/test_pipeline.py`

**背景**：让每阶段都有"调了什么服务/模型/处理什么任务"的细日志。措辞普适、不含特定文件内容判断。

- [ ] **Step 1: 写失败测试**

在 `tests/test_pipeline.py` 末尾追加：
```python
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

    from outline_extraction.understanding.classify import FileClass, ClassifyResult
    from outline_extraction.understanding.locate import LocateResult
    from outline_extraction.understanding.extract_skeleton import SkeletonResult
    from outline_extraction.understanding.extract_requirements import RequirementsResult
    from outline_extraction.alignment.merge import MergeResult
    from outline_extraction.alignment.supplement import SupplementResult
    from outline_extraction.models import OutlineNode, RequirementItem, SourceType

    class _ScriptedLLM:
        def __init__(self): self.script = []; self.idx = 0
        def push(self, r): self.script.append(r)
        def complete(self, **kwargs):
            r = self.script[self.idx]; self.idx += 1; return r

    llm = _ScriptedLLM()
    llm.push(ClassifyResult(file_class=FileClass.BID_FORMAT, confidence=0.9))
    llm.push(LocateResult(bid_format_sections=[0], scoring_sections=[0], tech_spec_sections=[], business_sections=[]))
    llm.push(SkeletonResult(nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))
    llm.push(RequirementsResult(items=[RequirementItem(ref_id="", description="x", source_type=SourceType.SCORING, location="评1", suggested_title="X")]))
    llm.push(MergeResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])], decisions=[]))
    llm.push(SupplementResult(tree=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])]))

    events = []
    from outline_extraction.pipeline import run_pipeline
    run_pipeline(src, llm=llm, model_main="gpt-5.4", model_mini="gpt-5.4-mini",
                 run_dir=tmp_path / "run", log_callback=lambda e: events.append(e))

    phases_with_detail = {e["phase"] for e in events if e.get("level") == "detail"}
    for ph in ["parse", "locate", "extract_skeleton", "extract_requirements", "merge"]:
        assert ph in phases_with_detail, f"{ph} 缺少 detail 日志"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_pipeline.py::test_pipeline_detail_logs_cover_main_phases -v`
Expected: FAIL（parse/locate 等还没 detail 日志）

- [ ] **Step 3: 补全各阶段 detail 日志**

修改 `outline_extraction/pipeline.py`：

第 1 步 parse（当前 73-79 行）改为：
```python
    # 1. 解析
    _log("parse", "start")
    files = collect_files(Path(input_path))
    docs: list[ParsedDocument] = []
    for p, suf in files:
        fname = Path(p).name
        if suf != ".docx" and cu is not None:
            _log("parse", "progress", f"调用 Content Understanding 解析《{fname}》", level="detail")
        else:
            _log("parse", "progress", f"本地解析《{fname}》", level="detail")
        docs.append(extract_document(Path(p), suf, cu=cu))
    _emit("parse", [d.model_dump() for d in docs])
    method_stat = ", ".join(f"{m}×{c}" for m, c in Counter(d.extract_method for d in docs).items())
    _log("parse", "done", f"解析完成：{len(docs)} 个文件（{method_stat}）")
```

第 4 步 locate（当前 97-105 行）在调用前加 detail：
```python
    # 4. 定位关键章节
    _log("locate", "start")
    _log("locate", "progress", f"调用 {model_main} 定位关键章节（{len(sections)} 个章节块）", level="detail")
    located = locate_sections(sections, llm=llm, model=model_main)
```
（其后 _emit 与 done 保持不变）

第 5 步 extract_skeleton（当前 109-118 行）在循环内加 detail：
```python
    _log("extract_skeleton", "start")
    skeleton = []
    _bid_n = len(located.bid_format_sections)
    for _k, i in enumerate(located.bid_format_sections, 1):
        sec = sections[i]
        span = _gather_span(sections, i)
        if not span.strip():
            continue
        _log("extract_skeleton", "progress",
             f"调用 {model_main} 抽取骨架（bid_format 章节 {_k}/{_bid_n}：{sec.title[:20]}）", level="detail")
        skeleton.extend(extract_skeleton(span, document=sec.doc_source, llm=llm, model=model_main))
    _emit("extract_skeleton", [n.model_dump() for n in skeleton])
    _log("extract_skeleton", "done", f"骨架抽取完成：{len(skeleton)} 个顶层标题")
```

第 6 步 extract_requirements（当前 122-133 行）在调用前加 detail：
```python
    _log("extract_requirements", "start")
    req_indices = located.scoring_sections + located.tech_spec_sections + located.business_sections
    req_texts = [_gather_span(sections, i) for i in req_indices]
    _log("extract_requirements", "progress",
         f"调用 {model_main} 抽取要求（{len(req_texts)} 个关键章节）", level="detail")
    requirements = extract_requirements(req_texts, llm=llm, model=model_main)
```
（其后赋 ref_id、_emit、done 保持不变）

第 7 步 merge（当前 136-139 行）在调用前加 detail：
```python
    _log("merge", "start")
    _log("merge", "progress", f"调用 {model_main} 归并 {len(requirements)} 条要求到骨架", level="detail")
    merged_tree, decisions = merge_requirements(skeleton, requirements, llm=llm, model=model_main)
```
（其后 _emit、done 保持不变）

第 8 步 supplement（当前 142-146 行）在调用前加 detail：
```python
    _log("supplement", "start")
    floating = [r.description for r, d in _pair_floating(requirements, decisions)]
    _log("supplement", "progress", f"调用 {model_main} 生成式补充（{len(floating)} 条游离要求）", level="detail")
    final_nodes = supplement_tree(merged_tree, floating=floating, llm=llm, model=model_main)
```
（其后 _emit、done 保持不变）

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add outline_extraction/pipeline.py tests/test_pipeline.py
git commit -m "feat: granular per-phase detail logs (model/service/task per call)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2：API 落盘 logs.jsonl + meta.json，新增历史端点，tree 兜底

**Files:**
- Modify: `outline_extraction/api/main.py`
- Test: `tests/test_api.py`

**背景**：worker 把日志事件落盘、写元信息；新增列 runs 与取日志端点；tree 从 finalize.json 兜底使刷新可加载。

- [ ] **Step 1: 写失败测试**

在 `tests/test_api.py` 末尾追加：
```python
def test_runs_list_and_logs_and_tree_fallback(monkeypatch, tmp_path):
    """落盘 logs.jsonl+meta.json 后：/api/runs 列出、/logs 读取、tree 从 finalize 兜底"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None):
        log_callback({"phase": "parse", "status": "progress", "message": "本地解析《a.docx》", "level": "detail"})
        log_callback({"phase": "finalize", "status": "done", "message": "完成：大纲共 5 个标题", "level": "main"})
        # 模拟 run_pipeline 落盘 finalize.json
        import json as _j
        (run_dir).mkdir(parents=True, exist_ok=True)
        (run_dir / "finalize.json").write_text(_j.dumps(_fake_tree().model_dump(), ensure_ascii=False), encoding="utf-8")
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = [("files", ("a.docx", io.BytesIO(b"x"), "application/octet-stream"))]
    run_id = client.post("/api/upload", files=files).json()["run_id"]
    client.post(f"/api/run/{run_id}")
    # 消费 SSE 确保 worker 跑完
    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        "".join(resp.iter_text())

    # logs.jsonl 落盘且可读
    logs = client.get(f"/api/runs/{run_id}/logs")
    assert logs.status_code == 200
    assert any("本地解析" in e["message"] for e in logs.json())

    # /api/runs 列出该 run（含 project_name/coverage）
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    ids = [r["run_id"] for r in runs.json()]
    assert run_id in ids

    # 清掉内存 TREE_STORE，tree 仍能从 finalize.json 兜底
    api_main.TREE_STORE.pop(run_id, None)
    tree = client.get(f"/api/tree/{run_id}")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["title"] == "投标函"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_api.py::test_runs_list_and_logs_and_tree_fallback -v`
Expected: FAIL（端点不存在 / tree 不兜底）

- [ ] **Step 3: worker 落盘 logs.jsonl + meta.json**

修改 `outline_extraction/api/main.py` 顶部 import 加 `import time`（若无）。把 `_worker` 内的 `_log_cb` 与 run_pipeline 调用段改为（在现有结构上增强）：
```python
    def _worker() -> None:
        """后台线程跑管线，把阶段日志/完成/异常事件入队 + 落盘——内部辅助"""
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "logs.jsonl"

        def _log_cb(event: dict) -> None:
            q.put(event)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            input_dir = UPLOAD_STORE[run_id]
            names = sorted(p.name for p in input_dir.iterdir()) if input_dir.is_dir() else [input_dir.name]
            proj = Path(names[0]).stem if names else run_id
            tree = run_pipeline(
                input_dir, llm=llm,
                model_main=settings.model_main, model_mini=settings.model_mini,
                run_dir=run_dir, log_callback=_log_cb, project_name=proj, cu=cu,
            )
            TREE_STORE[run_id] = tree
            # 写元信息供历史列表
            meta = {
                "run_id": run_id,
                "project_name": tree.project_name,
                "filenames": names,
                "created_at": int(time.time()),
                "coverage": tree.coverage.model_dump(),
            }
            (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            q.put({"event": "done"})
        except Exception as exc:
            q.put({"event": "error", "message": str(exc)})
        finally:
            q.put(_DONE)
```
注意：`cu` 需在 worker 内构造（现有代码已 `from outline_extraction.parsing.cu_client import build_cu_client; cu = build_cu_client(...)`，确认保留）。

- [ ] **Step 4: 新增 /api/runs 与 /api/runs/{id}/logs 端点；tree 兜底**

在 `outline_extraction/api/main.py` 末尾追加：
```python
@app.get("/api/runs")
async def list_runs() -> JSONResponse:
    """列出所有历史 run（读各 run 的 meta.json，按时间倒序）"""
    items = []
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    items.append(json.loads(meta_path.read_text(encoding="utf-8")))
                except Exception:
                    continue
    items.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return JSONResponse(items)


@app.get("/api/runs/{run_id}/logs")
async def get_logs(run_id: str) -> JSONResponse:
    """返回该 run 的日志事件数组（读 logs.jsonl）"""
    log_path = RUNS_DIR / run_id / "logs.jsonl"
    if not log_path.exists():
        raise HTTPException(404, "logs not found")
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return JSONResponse(events)
```

把现有 `get_tree`（当前约 114 行）改为内存优先、finalize.json 兜底：
```python
@app.get("/api/tree/{run_id}")
async def get_tree(run_id: str) -> JSONResponse:
    """返回最终大纲树 JSON（内存优先，刷新后从 finalize.json 兜底）"""
    if run_id in TREE_STORE:
        return JSONResponse(TREE_STORE[run_id].model_dump())
    fin = RUNS_DIR / run_id / "finalize.json"
    if fin.exists():
        return JSONResponse(json.loads(fin.read_text(encoding="utf-8")))
    raise HTTPException(404, "tree not ready")
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: 全部 passed（含新测试 + 原有）

- [ ] **Step 6: 全量回归**

Run: `.venv/bin/pytest -q`
Expected: 全部 passed

- [ ] **Step 7: Commit**

```bash
git add outline_extraction/api/main.py tests/test_api.py
git commit -m "feat: persist logs.jsonl+meta.json; add /api/runs and logs endpoints; tree falls back to finalize.json

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3：前端两栏布局 + 历史边栏 + 阶段日志窗 + 配色

**Files:**
- Modify: `web/index.html`、`web/app.js`

**背景**：纯前端。两栏（左历史栏 + 右主区）；阶段日志窗自动展开/收起/可手动展开；加品牌色+功能色。**控制方会用 Chrome DevTools 截图验证，subagent 不截图。**

- [ ] **Step 1: 改 app.js 状态与逻辑**

把 `web/app.js` 的 `app()` 返回对象整体替换为（保留 PHASE_DEFS 不变，在其下）：
```javascript
function app() {
  return {
    runId: null,
    fileNames: [],
    running: false,
    phases: [],
    errorMsg: "",
    tree: null,
    keepAiMarks: false,
    history: [],        // 历史 run 列表
    viewing: null,      // 正在回看的 run_id（null=新建/实时模式）
    expanded: {},       // {phaseKey: bool} 手动展开状态

    initPhases() {
      this.phases = PHASE_DEFS.map(p => ({ key: p.key, label: p.label, status: "pending", logs: [] }));
      this.expanded = {};
    },

    badge(type) {
      const m = { skeleton: "📋骨架", scoring: "📊评分", tech_spec: "📐技术",
                  biz_terms: "📄商务", ai_suggested: "🤖AI建议" };
      return m[type] || type;
    },

    // 来源类型 → 徽章配色类（功能色，低饱和）
    badgeClass(type) {
      const m = {
        skeleton: "bg-blue-50 text-blue-600",
        scoring: "bg-green-50 text-green-600",
        tech_spec: "bg-purple-50 text-purple-600",
        biz_terms: "bg-orange-50 text-orange-600",
        ai_suggested: "bg-neutral-100 text-neutral-500",
      };
      return m[type] || "bg-neutral-100 text-neutral-500";
    },

    async loadHistory() {
      try {
        const r = await fetch("/api/runs");
        this.history = await r.json();
      } catch (e) { this.history = []; }
    },

    async onFile(e) {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      this.fileNames = files.map(f => f.name);
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      this.runId = (await r.json()).run_id;
    },

    newRun() {
      this.viewing = null; this.runId = null; this.fileNames = [];
      this.tree = null; this.errorMsg = ""; this.phases = []; this.running = false;
    },

    async run() {
      if (!this.runId) return;
      this.viewing = null;
      this.running = true; this.errorMsg = ""; this.tree = null;
      this.initPhases();
      await fetch(`/api/run/${this.runId}`, { method: "POST" });
      const es = new EventSource(`/api/progress/${this.runId}`);
      es.onmessage = async (e) => {
        const ev = JSON.parse(e.data);
        if (ev.event === "done") {
          es.close();
          this.tree = await (await fetch(`/api/tree/${this.runId}`)).json();
          this.running = false;
          this.loadHistory();
        } else if (ev.event === "error") {
          es.close(); this.errorMsg = ev.message || "运行出错"; this.running = false;
        } else {
          this.applyPhaseEvent(ev);
        }
      };
      es.onerror = () => { es.close(); this.running = false; };
    },

    applyPhaseEvent(ev) {
      const p = this.phases.find(x => x.key === ev.phase);
      if (!p) return;
      if (ev.status === "start") {
        p.status = "running";
      } else if (ev.status === "done") {
        p.status = "done";
        if (ev.message) p.logs.push({ level: "main", text: ev.message });
      } else if (ev.status === "progress") {
        p.status = "running";
        if (ev.message) p.logs.push({ level: ev.level || "detail", text: ev.message });
      }
    },

    // 阶段日志窗是否展开：运行中自动开，完成后看手动状态
    isExpanded(p) {
      if (p.status === "running") return true;
      return !!this.expanded[p.key];
    },
    toggle(p) { this.expanded[p.key] = !this.expanded[p.key]; },

    // 点击历史项：回看模式，加载日志+树
    async openHistory(runId) {
      this.viewing = runId; this.running = false; this.errorMsg = "";
      this.initPhases();
      const events = await (await fetch(`/api/runs/${runId}/logs`)).json();
      events.forEach(ev => this.applyPhaseEvent(ev));
      this.phases.forEach(p => { if (p.logs.length) p.status = "done"; });
      this.tree = await (await fetch(`/api/tree/${runId}`)).json();
    },

    get cov() { return this.tree ? this.tree.coverage : {}; },
    exportUrl() { return `/api/export/${this.viewing || this.runId}.docx?keep_ai_marks=${this.keepAiMarks}`; },

    renderNode(node, depth) {
      const pad = depth * 18;
      const types = [...new Set((node.sources || []).map(s => s.type))];
      const badges = types
        .map(t => `<span class="ml-2 px-1.5 py-0.5 rounded text-[11px] ${this.badgeClass(t)}">${this.badge(t)}</span>`)
        .join("");
      const isAi = types.length === 1 && types[0] === "ai_suggested";
      const bg = isAi ? "background:#fafafa;" : "";
      let html = `<div style="padding-left:${pad}px;${bg}" class="py-1.5 border-b border-neutral-50">
        <span class="text-neutral-300 mr-2 text-xs">${node.id}</span>
        <span class="text-neutral-800">${node.title}</span>${badges}</div>`;
      for (const c of (node.children || [])) html += this.renderNode(c, depth + 1);
      return html;
    },

    init() { this.loadHistory(); },
  };
}
```

- [ ] **Step 2: 改 index.html 为两栏 + 历史栏 + 日志窗 + 配色**

把 `web/index.html` 的 `<body>` 整体替换为：
```html
<body class="bg-neutral-50 text-neutral-800 antialiased">
  <div x-data="app()" class="flex min-h-screen">
    <!-- 左侧历史边栏 -->
    <aside class="w-64 shrink-0 border-r border-neutral-200 bg-white px-3 py-5 hidden md:block">
      <button @click="newRun()"
              class="w-full mb-4 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors">
        + 新建提取
      </button>
      <div class="text-xs font-semibold text-neutral-400 uppercase tracking-wide mb-2 px-1">历史记录</div>
      <div class="space-y-1">
        <template x-for="h in history" :key="h.run_id">
          <button @click="openHistory(h.run_id)"
                  class="w-full text-left px-3 py-2 rounded-lg hover:bg-neutral-50 transition-colors"
                  :class="viewing === h.run_id ? 'bg-indigo-50 ring-1 ring-indigo-200' : ''">
            <div class="text-sm text-neutral-800 truncate" x-text="h.project_name"></div>
            <div class="text-xs text-neutral-400 mt-0.5">
              <span x-text="(h.coverage ? (h.coverage.mapped_scoring_items+h.coverage.mapped_tech_items+h.coverage.mapped_biz_items) : 0) + ' 项要求'"></span>
            </div>
          </button>
        </template>
        <div class="text-xs text-neutral-300 px-3 py-2" x-show="!history.length">暂无记录</div>
      </div>
    </aside>

    <!-- 右侧主区 -->
    <main class="flex-1 max-w-3xl mx-auto px-6 py-12 w-full">
      <header class="mb-10">
        <h1 class="text-3xl font-semibold tracking-tight text-neutral-900">投标大纲提取</h1>
        <p class="mt-2 text-neutral-500">上传招标文件，自动生成结构化投标文件大纲。</p>
      </header>

      <!-- 上传区（回看模式隐藏） -->
      <div class="mb-8" x-show="!viewing">
        <label class="block border border-dashed border-neutral-300 rounded-2xl bg-white px-8 py-10 text-center cursor-pointer hover:border-indigo-400 transition-colors">
          <input type="file" multiple class="hidden" @change="onFile($event)" />
          <div class="text-neutral-700 font-medium">选择文件或拖拽到此处</div>
          <div class="text-sm text-neutral-400 mt-1">支持 docx / doc / pdf，可多选（文件包）</div>
          <template x-if="fileNames.length">
            <div class="mt-4 text-sm text-neutral-600 space-y-1">
              <template x-for="n in fileNames" :key="n"><div x-text="n"></div></template>
            </div>
          </template>
        </label>
        <button @click="run()" :disabled="!runId || running"
                class="mt-5 px-6 py-2.5 rounded-full bg-indigo-600 text-white text-sm font-medium disabled:opacity-30 hover:bg-indigo-700 transition-colors">
          <span x-text="running ? '处理中…' : '开始提取'"></span>
        </button>
      </div>

      <div class="mb-8 rounded-2xl bg-red-50 text-red-600 px-5 py-4 text-sm" x-show="errorMsg" x-text="errorMsg"></div>

      <!-- 处理流程 + 阶段日志窗 -->
      <section class="mb-8 rounded-2xl bg-white border border-neutral-100 p-6" x-show="phases.length">
        <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide mb-5">处理流程</h2>
        <ol class="space-y-1">
          <template x-for="(p, i) in phases" :key="p.key">
            <li>
              <div class="flex items-center px-2 py-2 rounded-xl transition-colors cursor-pointer"
                   :class="p.status === 'running' ? 'bg-indigo-50' : ''" @click="toggle(p)">
                <span class="w-5 h-5 mr-3 flex items-center justify-center shrink-0">
                  <template x-if="p.status === 'done'">
                    <span class="w-4 h-4 rounded-full bg-indigo-600 text-white text-[10px] flex items-center justify-center">✓</span>
                  </template>
                  <template x-if="p.status === 'running'">
                    <span class="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin"></span>
                  </template>
                  <template x-if="p.status === 'pending'">
                    <span class="w-1.5 h-1.5 rounded-full bg-neutral-300"></span>
                  </template>
                </span>
                <span class="text-sm flex-1"
                      :class="p.status === 'running' ? 'font-semibold text-indigo-700' : (p.status === 'done' ? 'text-neutral-700' : 'text-neutral-300')"
                      x-text="(i + 1) + '. ' + p.label"></span>
                <span class="text-xs text-neutral-300" x-show="p.logs.length" x-text="isExpanded(p) ? '收起' : '展开'"></span>
              </div>
              <!-- 滚动日志窗 -->
              <div x-show="isExpanded(p) && p.logs.length"
                   class="ml-10 mt-1 mb-2 max-h-44 overflow-y-auto rounded-lg bg-neutral-900 text-neutral-100 text-xs font-mono p-3 space-y-1">
                <template x-for="(line, li) in p.logs" :key="li">
                  <div :class="line.level === 'main' ? 'text-emerald-300' : 'text-neutral-400'">
                    <span x-text="line.level === 'main' ? '▸ ' : '· '"></span><span x-text="line.text"></span>
                  </div>
                </template>
              </div>
            </li>
          </template>
        </ol>
      </section>

      <!-- 覆盖率 -->
      <section class="mb-8 rounded-2xl bg-white border border-neutral-100 p-6" x-show="tree">
        <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide mb-4">覆盖率</h2>
        <template x-if="tree">
          <div class="flex flex-wrap gap-8 text-sm">
            <div>
              <div class="text-neutral-400 text-xs mb-1">评分点</div>
              <div :class="cov.mapped_scoring_items===cov.total_scoring_items ? 'text-emerald-600' : 'text-amber-600'"
                   class="text-lg font-medium" x-text="cov.mapped_scoring_items + ' / ' + cov.total_scoring_items"></div>
            </div>
            <div>
              <div class="text-neutral-400 text-xs mb-1">技术条目</div>
              <div :class="cov.mapped_tech_items===cov.total_tech_items ? 'text-emerald-600' : 'text-amber-600'"
                   class="text-lg font-medium" x-text="cov.mapped_tech_items + ' / ' + cov.total_tech_items"></div>
            </div>
            <div>
              <div class="text-neutral-400 text-xs mb-1">商务</div>
              <div :class="cov.mapped_biz_items===cov.total_biz_items ? 'text-emerald-600' : 'text-amber-600'"
                   class="text-lg font-medium" x-text="cov.mapped_biz_items + ' / ' + cov.total_biz_items"></div>
            </div>
          </div>
        </template>
        <template x-if="tree && cov.unmapped && cov.unmapped.length">
          <div class="mt-4 text-sm">
            <div class="text-amber-600 font-medium mb-1">未覆盖（建议人工复核）</div>
            <ul class="list-disc ml-5 text-neutral-500 space-y-0.5">
              <template x-for="u in cov.unmapped" :key="u"><li x-text="u"></li></template>
            </ul>
          </div>
        </template>
      </section>

      <!-- 大纲树 -->
      <section class="rounded-2xl bg-white border border-neutral-100 p-6" x-show="tree">
        <div class="flex justify-between items-center mb-5">
          <h2 class="text-sm font-semibold text-neutral-400 uppercase tracking-wide">投标文件大纲</h2>
          <div class="flex items-center gap-4">
            <label class="text-xs text-neutral-500 flex items-center gap-1.5">
              <input type="checkbox" x-model="keepAiMarks" class="rounded" /> 保留 AI 建议标注
            </label>
            <a :href="exportUrl()" class="px-4 py-1.5 rounded-full bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 transition-colors">导出 Word</a>
          </div>
        </div>
        <div class="text-sm leading-relaxed">
          <template x-for="n in (tree ? tree.nodes : [])" :key="n.id">
            <div x-html="renderNode(n, 0)"></div>
          </template>
        </div>
      </section>
    </main>
  </div>
  <script src="/static/app.js"></script>
</body>
```
注意：保留 `<head>`（含字体 style、Tailwind/Alpine CDN）不变。日志窗用 CSS `max-h` + `overflow-y-auto` 滚动，无需 Alpine ref。

- [ ] **Step 3: 起服务（控制方做截图验证，此处仅确认能起）**

Run:
```bash
cd /Users/jiqingyou/Documents/Code/VSCode/Microsoft/Demo/Customers/Sungrow/OutlineExtraction
pkill -f "uvicorn outline_extraction" 2>/dev/null; sleep 1
PYTHONPATH=. .venv/bin/uvicorn outline_extraction.api.main:app --port 8131 > /tmp/uvicorn_outline.log 2>&1 &
sleep 4; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8131/
curl -s -o /dev/null -w "runs HTTP %{http_code}\n" http://localhost:8131/api/runs
pkill -f "uvicorn outline_extraction"
```
Expected: 两个 HTTP 200。

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: two-column layout with history sidebar, expandable phase log windows, brand+functional colors

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4：控制方真实渲染验证（Chrome DevTools 截图）

**Files:** 无代码改动；验证关卡（由控制方执行，非 subagent）。

- [ ] **Step 1: 起服务，截初始页**（含左侧历史栏、上传区、indigo 配色）
- [ ] **Step 2: 注入模拟 phases+logs，截"运行中"**（某阶段展开深色滚动日志窗、当前阶段 indigo 高亮转圈）
- [ ] **Step 3: 截"完成态"**（阶段收起为摘要+展开箭头、覆盖率三色、大纲树分类色徽章）
- [ ] **Step 4: 点历史项截"回看模式"**（右侧加载该 run 日志+大纲）
- [ ] **Step 5: 窄屏(390)截图**（边栏隐藏、主区自适应）
- [ ] **Step 6: 据截图修差异并复验，停服务**

---

## 自审记录

**Spec 覆盖：**
- §3.1 细日志（level/progress）→ Task 0（level 字段）+ Task 1（各阶段 detail）✓
- §3.2 落盘 logs.jsonl+meta.json → Task 2 ✓
- §3.3 /api/runs、/logs、tree 兜底 → Task 2 ✓
- §4.1 左侧历史栏 → Task 3（aside + openHistory/loadHistory）✓
- §4.2 阶段日志窗自动展开/收起/手动 → Task 3（isExpanded/toggle）✓
- §4.3 品牌色+功能色 → Task 3（indigo + badgeClass 分类色 + 覆盖率绿/琥珀）✓
- §6 验证 → Task 3 Step 3（能起）+ Task 4（截图）✓

**占位符扫描：** 无 TBD、无矛盾写法。

**类型一致性：**
- 日志事件 `{phase,status,message,level}`：pipeline 发（Task 0/1）↔ API 落盘/透传（Task 2）↔ 前端 applyPhaseEvent 读 `ev.level`（Task 3）一致。
- `p.logs` 元素结构在前端统一为 `{level, text}`（applyPhaseEvent 里构造，renderNode 无关；日志窗模板读 `line.level`/`line.text`）一致。
- meta.json 字段 `{run_id,project_name,filenames,created_at,coverage}`：Task 2 写 ↔ /api/runs 读 ↔ 前端 history 项读 `h.project_name`/`h.coverage` 一致。
- fake_run 签名带 `cu=None`（Task 2 测试）与 main.py 真实调用 `cu=cu` 一致。
