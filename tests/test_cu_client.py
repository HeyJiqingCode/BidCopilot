"""Content Understanding 客户端测试——注入 fake，不打真实服务"""
from outline_extraction.parsing.cu_client import analyze_with_cu, CUResult


class _FakeCU:
    """模拟 CU 分析，返回 Markdown"""
    def analyze(self, file_path):
        return CUResult(markdown="# 扫描件标题\n| 项 | 分值 |\n| A | 5 |", page_count=3)


def test_analyze_returns_markdown(tmp_path):
    """CU 分析返回结构化 Markdown"""
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=_FakeCU())
    assert "扫描件标题" in result.markdown
    assert "| 项 | 分值 |" in result.markdown


def test_analyze_none_client_returns_empty(tmp_path):
    """未配置 CU（cu=None）时返回空结果，不抛异常"""
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    result = analyze_with_cu(f, cu=None)
    assert result.markdown == ""
