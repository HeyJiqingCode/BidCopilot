"""Content Understanding 客户端测试——注入 fake/mock，不打真实服务"""
from bid_copilot.parsing.cu_client import analyze_with_cu, CUResult, CUClient


class _FakeCU:
    def analyze(self, file_path):
        return CUResult(markdown="# 扫描件标题\n| 项 | 分值 |\n| --- | --- |\n| A | 5 |", page_count=3)


def test_analyze_returns_markdown(tmp_path):
    f = tmp_path / "scan.pdf"; f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=_FakeCU())
    assert "扫描件标题" in result.markdown
    assert "| 项 | 分值 |" in result.markdown


def test_analyze_none_client_returns_empty(tmp_path):
    f = tmp_path / "scan.pdf"; f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=None)
    assert result.markdown == ""


def test_cuclient_analyze_polls_and_reads_markdown(tmp_path, monkeypatch):
    import bid_copilot.parsing.cu_client as cu_mod
    posted = {}
    class _Resp:
        def __init__(self, status_code=200, headers=None, payload=None):
            self.status_code = status_code; self.headers = headers or {}; self._payload = payload or {}
        def raise_for_status(self):
            if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
        def json(self): return self._payload
    def fake_post(url, headers=None, data=None, timeout=None):
        posted["url"] = url; posted["bytes"] = len(data) if data else 0
        return _Resp(202, {"Operation-Location": "https://x/op/123"})
    def fake_get(url, headers=None, timeout=None):
        return _Resp(200, {}, {"status": "Succeeded",
                               "result": {"contents": [{"markdown": "# 标题\n| a | b |\n| --- | --- |"}]}})
    monkeypatch.setattr(cu_mod.requests, "post", fake_post)
    monkeypatch.setattr(cu_mod.requests, "get", fake_get)
    f = tmp_path / "doc.doc"; f.write_bytes(b"\xd0\xcf fake doc bytes")
    client = CUClient(endpoint="https://res.cognitiveservices.azure.com", key="k")
    out = client.analyze(f)
    assert "# 标题" in out.markdown
    assert "analyzeBinary" in posted["url"]
    assert posted["bytes"] > 0
