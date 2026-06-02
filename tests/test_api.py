"""API 测试——monkeypatch 掉真实管线"""
import io
from fastapi.testclient import TestClient
from bid_copilot.api import main as api_main
from bid_copilot.models import OutlineTree, OutlineNode, CoverageReport


def _fake_tree():
    return OutlineTree(
        project_name="x", source_documents=["a.docx"],
        nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )


def test_upload_and_run(monkeypatch, tmp_path):
    """上传文件→run（后台线程）→SSE 收到 done→拿到 tree"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None, efforts=None, max_concurrency=5):
        log_callback({"phase": "parse", "status": "start", "message": ""})
        log_callback({"phase": "parse", "status": "done", "message": "解析完成：1 个文件"})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = [("files", ("a.docx", io.BytesIO(b"fakedocx"), "application/octet-stream"))]
    up = client.post("/api/upload", files=files)
    assert up.status_code == 200
    run_id = up.json()["run_id"]

    run = client.post(f"/api/run/{run_id}")
    assert run.status_code == 200
    assert run.json()["status"] == "started"

    # 消费 SSE 流，确保后台线程跑完（done 事件后流结束）
    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert "解析完成" in body
    assert "done" in body

    tree = client.get(f"/api/tree/{run_id}")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["title"] == "投标函"


def test_run_rejects_duplicate(monkeypatch, tmp_path):
    """同一 run_id 已完成后再次 POST 应返回 409，避免重头跑"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None, efforts=None, max_concurrency=5):
        log_callback({"phase": "parse", "status": "done", "message": "解析完成"})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = [("files", ("a.docx", io.BytesIO(b"x"), "application/octet-stream"))]
    run_id = client.post("/api/upload", files=files).json()["run_id"]

    assert client.post(f"/api/run/{run_id}").status_code == 200
    # 消费 SSE 确保 worker 跑完（finalize.json 落盘 + PROGRESS_QUEUES 清理）
    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        "".join(resp.iter_text())
    # 已完成：再次发起应被拒
    dup = client.post(f"/api/run/{run_id}")
    assert dup.status_code == 409


def test_run_status_transitions(monkeypatch, tmp_path):
    """run_status：未知 run → unknown；跑完落盘 finalize → done"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None, efforts=None, max_concurrency=5):
        log_callback({"phase": "finalize", "status": "done", "message": "完成"})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    # 未知 run
    assert client.get("/api/run_status/nope123").json()["status"] == "unknown"

    files = [("files", ("a.docx", io.BytesIO(b"x"), "application/octet-stream"))]
    run_id = client.post("/api/upload", files=files).json()["run_id"]
    client.post(f"/api/run/{run_id}")
    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        "".join(resp.iter_text())
    # 跑完：done
    assert client.get(f"/api/run_status/{run_id}").json()["status"] == "done"


def test_progress_sse_streams_phase_events(monkeypatch, tmp_path):
    """SSE 进度端点流式推送阶段日志事件"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None, efforts=None, max_concurrency=5):
        log_callback({"phase": "classify", "status": "done", "message": "分类完成：技术规范×2"})
        log_callback({"phase": "finalize", "status": "done", "message": "完成：大纲共 10 个标题"})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = [("files", ("a.docx", io.BytesIO(b"fakedocx"), "application/octet-stream"))]
    run_id = client.post("/api/upload", files=files).json()["run_id"]
    client.post(f"/api/run/{run_id}")

    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        body = "".join(resp.iter_text())
    assert "分类完成：技术规范×2" in body
    assert "完成：大纲共 10 个标题" in body
    assert "classify" in body and "finalize" in body


def test_export_docx(monkeypatch, tmp_path):
    """导出 docx 返回二进制"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(api_main, "run_pipeline",
                        lambda **k: (_ for _ in ()).throw(AssertionError("不应被调用")))
    # 直接写入一棵树到 store
    run_id = "test123"
    api_main.TREE_STORE[run_id] = _fake_tree()
    client = TestClient(api_main.app)
    resp = client.get(f"/api/export/{run_id}.docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/")
    assert len(resp.content) > 0


def test_upload_multiple_files_stores_dir(monkeypatch, tmp_path):
    """上传多个文件应全部存入 input 目录，UPLOAD_STORE 指向该目录"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    client = TestClient(api_main.app)
    files = [
        ("files", ("tech.docx", io.BytesIO(b"t"), "application/octet-stream")),
        ("files", ("biz.docx", io.BytesIO(b"b"), "application/octet-stream")),
    ]
    up = client.post("/api/upload", files=files)
    assert up.status_code == 200
    run_id = up.json()["run_id"]
    stored = api_main.UPLOAD_STORE[run_id]
    assert stored.is_dir()
    names = sorted(p.name for p in stored.iterdir())
    assert names == ["biz.docx", "tech.docx"]
    assert up.json()["filenames"] == ["tech.docx", "biz.docx"]


def test_export_falls_back_to_finalize_json(monkeypatch, tmp_path):
    """TREE_STORE 没有该 run 时，导出应从 finalize.json 兜底重建大纲树并产出 docx"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    run_id = "restartedrun"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    import json as _j
    (run_dir / "finalize.json").write_text(
        _j.dumps(_fake_tree().model_dump(), ensure_ascii=False), encoding="utf-8")
    # 确保内存里没有该 run（模拟服务重启）
    api_main.TREE_STORE.pop(run_id, None)

    client = TestClient(api_main.app)
    resp = client.get(f"/api/export/{run_id}.docx")
    assert resp.status_code == 200
    assert len(resp.content) > 0
    # docx 是 zip 容器，magic number 以 PK 开头
    assert resp.content[:2] == b"PK"


def test_runs_list_and_logs_and_tree_fallback(monkeypatch, tmp_path):
    """落盘 logs.jsonl+meta.json 后：/api/runs 列出、/logs 读取、tree 从 finalize 兜底"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, log_callback, project_name=None, cu=None, efforts=None, max_concurrency=5):
        log_callback({"phase": "parse", "status": "progress", "message": "本地解析《a.docx》", "level": "detail"})
        log_callback({"phase": "finalize", "status": "done", "message": "完成：大纲共 5 个标题", "level": "main"})
        import json as _j
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "finalize.json").write_text(_j.dumps(_fake_tree().model_dump(), ensure_ascii=False), encoding="utf-8")
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = [("files", ("a.docx", io.BytesIO(b"x"), "application/octet-stream"))]
    run_id = client.post("/api/upload", files=files).json()["run_id"]
    client.post(f"/api/run/{run_id}")
    with client.stream("GET", f"/api/progress/{run_id}") as resp:
        "".join(resp.iter_text())

    logs = client.get(f"/api/runs/{run_id}/logs")
    assert logs.status_code == 200
    assert any("本地解析" in e["message"] for e in logs.json())

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    ids = [r["run_id"] for r in runs.json()]
    assert run_id in ids

    api_main.TREE_STORE.pop(run_id, None)
    tree = client.get(f"/api/tree/{run_id}")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["title"] == "投标函"
