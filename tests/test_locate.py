"""定位关键章节测试——注入 fake LLM"""
from outline_extraction.models import Section
from outline_extraction.understanding.locate import locate_sections, LocateResult


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.last_kwargs = None

    def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self._result


def test_locate_returns_indices():
    """定位返回各类章节索引，并能据此取回 Section"""
    sections = [
        Section(title="投标文件格式", level=1, content="...", doc_source="fmt.docx"),
        Section(title="评标办法", level=1, content="...", doc_source="main.pdf"),
        Section(title="技术规范书", level=1, content="...", doc_source="tech.docx"),
        Section(title="合同条款", level=1, content="...", doc_source="biz.doc"),
    ]
    fake = _FakeLLM(LocateResult(
        bid_format_sections=[0], scoring_sections=[1],
        tech_spec_sections=[2], business_sections=[3],
    ))
    result = locate_sections(sections, llm=fake, model="gpt-5.4")
    assert result.bid_format_sections == [0]
    assert result.scoring_sections == [1]
    # input 中应包含标题列表
    assert "投标文件格式" in fake.last_kwargs["input_content"]
