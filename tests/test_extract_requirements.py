"""要求条目抽取测试——注入 fake LLM"""
from bid_copilot.models import RequirementItem, SourceType
from bid_copilot.understanding.extract_requirements import (
    extract_requirements, RequirementsResult,
)


class _FakeLLM:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.seen_instructions = []      # 记录每次调用传入的 instructions，供断言 prompt 被加载

    def complete(self, **kwargs):
        self.seen_instructions.append(kwargs.get("instructions", ""))
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


def test_extract_requirements_loads_prompt_with_param_table_rule():
    """prompt 被加载并作为 instructions 传入，且含'技术参数响应表'聚合规则锚词"""
    fake = _FakeLLM([RequirementsResult(items=[])])
    extract_requirements(["技术章节文本"], llm=fake, model="gpt-5.4")
    assert fake.seen_instructions, "应至少调用一次 LLM 并传入 instructions"
    instr = fake.seen_instructions[0]
    assert "技术参数响应表" in instr        # 聚合规则锚词
    assert "is_param_table" in instr        # 聚合标记字段说明


def test_extract_requirements_passes_through_param_table_flag():
    """is_param_table=true 的聚合条目原样透传进结果列表，不被吞/不被改写"""
    fake = _FakeLLM([
        RequirementsResult(items=[
            RequirementItem(description="对《组件规格表》全部参数统一应答（共约8项）",
                            source_type=SourceType.TECH_SPEC, location="表2",
                            suggested_title="技术参数响应表", is_param_table=True),
            RequirementItem(description="投标方应保证产品符合现行最新标准",
                            source_type=SourceType.TECH_SPEC, location="第一章1.2",
                            suggested_title="技术标准符合性", is_param_table=False),
        ]),
    ])
    items = extract_requirements(["技术章节文本"], llm=fake, model="gpt-5.4")
    assert len(items) == 2
    agg = [i for i in items if i.is_param_table]
    assert len(agg) == 1 and "统一应答" in agg[0].description   # 聚合条保留
    txt = [i for i in items if not i.is_param_table]
    assert len(txt) == 1 and "符合现行最新标准" in txt[0].description   # 文字硬条款保留
