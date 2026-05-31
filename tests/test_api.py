"""API 测试——monkeypatch 掉真实管线"""
import io
from fastapi.testclient import TestClient
from outline_extraction.api import main as api_main
from outline_extraction.models import OutlineTree, OutlineNode, CoverageReport


def _fake_tree():
    return OutlineTree(
        project_name="x", source_documents=["a.docx"],
        nodes=[OutlineNode(id="1", title="投标函", level=1, sources=[], children=[])],
        coverage=CoverageReport(total_scoring_items=0, mapped_scoring_items=0,
                                total_tech_items=0, mapped_tech_items=0, unmapped=[]),
    )


def test_upload_and_run(monkeypatch, tmp_path):
    """上传文件→run→拿到 tree"""
    monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)

    def fake_run(input_path, llm, model_main, model_mini, run_dir, progress_callback):
        progress_callback("parse", {})
        progress_callback("finalize", {})
        return _fake_tree()

    monkeypatch.setattr(api_main, "run_pipeline", fake_run)

    client = TestClient(api_main.app)
    files = {"file": ("a.docx", io.BytesIO(b"fakedocx"), "application/octet-stream")}
    up = client.post("/api/upload", files=files)
    assert up.status_code == 200
    run_id = up.json()["run_id"]

    run = client.post(f"/api/run/{run_id}")
    assert run.status_code == 200

    tree = client.get(f"/api/tree/{run_id}")
    assert tree.status_code == 200
    assert tree.json()["nodes"][0]["title"] == "投标函"


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
