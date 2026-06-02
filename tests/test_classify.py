"""文件分类测试——注入 fake LLM"""
from bid_copilot.models import ParsedDocument, SourceType
from bid_copilot.understanding.classify import classify_documents, FileClass, ClassifyResult


class _FakeLLM:
    """按文件名顺序返回预设分类"""
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def complete(self, **kwargs):
        r = self._results[self.calls]
        self.calls += 1
        return r


def test_classify_routes_to_mini_and_returns_labels():
    """分类应对每个文档调用一次，返回标签"""
    docs = [
        ParsedDocument(filename="须知.docx", raw_markdown="投标人须知前附表", extract_method="docx"),
        ParsedDocument(filename="技术.docx", raw_markdown="技术规范书 1. 性能参数", extract_method="docx"),
    ]
    fake = _FakeLLM([
        ClassifyResult(file_class=FileClass.TENDER_MAIN, confidence=0.9),
        ClassifyResult(file_class=FileClass.TECH_SPEC, confidence=0.8),
    ])
    out = classify_documents(docs, llm=fake, model="gpt-5.4-mini")
    assert fake.calls == 2
    assert out["须知.docx"].file_class == FileClass.TENDER_MAIN
    assert out["技术.docx"].file_class == FileClass.TECH_SPEC
