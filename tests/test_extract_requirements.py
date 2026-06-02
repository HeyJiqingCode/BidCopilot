"""要求条目抽取测试——注入 fake LLM"""
from bid_copilot.models import RequirementItem, SourceType
from bid_copilot.understanding.extract_requirements import (
    extract_requirements, RequirementsResult,
)


class _FakeLLM:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def complete(self, **kwargs):
        r = self._results[self.calls]
        self.calls += 1
        return r


def test_extract_requirements_flattens_multiple_sections():
    """多个章节的抽取结果被合并为一个列表"""
    fake = _FakeLLM([
        RequirementsResult(items=[
            RequirementItem(description="提供ISO9001", source_type=SourceType.SCORING,
                            location="评分第3条", suggested_title="质量体系认证"),
        ]),
        RequirementsResult(items=[
            RequirementItem(description="效率≥98.5%", source_type=SourceType.TECH_SPEC,
                            location="技术3.1", suggested_title="效率参数响应"),
        ]),
    ])
    items = extract_requirements(["评分章节文本", "技术章节文本"], llm=fake, model="gpt-5.4")
    assert fake.calls == 2
    assert len(items) == 2
    assert {i.source_type for i in items} == {SourceType.SCORING, SourceType.TECH_SPEC}


def test_extract_requirements_empty_input():
    """无章节输入时返回空列表，不调用 LLM"""
    fake = _FakeLLM([])
    items = extract_requirements([], llm=fake, model="gpt-5.4")
    assert items == []
    assert fake.calls == 0
