"""LLMClient 封装测试——用 fake responses 客户端验证调用拼装与解析"""
from pydantic import BaseModel
from bid_copilot.llm.client import LLMClient


class _Out(BaseModel):
    answer: str


class _FakeParsed:
    """模拟 responses.parse 返回对象"""
    def __init__(self, parsed, usage):
        self.output_parsed = parsed
        self.usage = usage


class _FakeResponses:
    def __init__(self, recorder):
        self.recorder = recorder

    def parse(self, **kwargs):
        self.recorder["last_kwargs"] = kwargs  # 记录调用参数供断言
        return _FakeParsed(_Out(answer="hi"), usage={"total_tokens": 42})


class _FakeClient:
    def __init__(self):
        self.recorder = {}
        self.responses = _FakeResponses(self.recorder)


def test_complete_structured_passes_params():
    """complete 应把模型/instructions/reasoning/text/text_format 正确传给 responses.parse"""
    fake = _FakeClient()
    llm = LLMClient(client=fake)
    result = llm.complete(
        model="gpt-5.4", instructions="do x", input_content="hello",
        effort="high", verbosity="low", schema=_Out,
    )
    assert isinstance(result, _Out)
    assert result.answer == "hi"
    kw = fake.recorder["last_kwargs"]
    assert kw["model"] == "gpt-5.4"
    assert kw["instructions"] == "do x"
    assert kw["input"] == "hello"
    assert kw["reasoning"] == {"effort": "high"}
    assert kw["text"] == {"verbosity": "low"}
    assert kw["text_format"] is _Out


def test_usage_accumulated():
    """每次调用应累计 token 用量，便于成本展示"""
    fake = _FakeClient()
    llm = LLMClient(client=fake)
    llm.complete(model="gpt-5.4", instructions="i", input_content="c", schema=_Out)
    llm.complete(model="gpt-5.4", instructions="i", input_content="c", schema=_Out)
    assert llm.total_calls == 2
