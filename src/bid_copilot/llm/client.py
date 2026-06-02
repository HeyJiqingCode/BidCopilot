"""Azure OpenAI Responses API 封装——统一入口、结构化输出、用量记录"""
from typing import Optional, Type, Any
from pydantic import BaseModel
from openai import OpenAI
from bid_copilot.config import Settings


class LLMClient:
    """封装 responses.parse；调用方传模型名做路由

    参数:
        settings: 配置对象，缺省自动构造
        client: 可注入的底层客户端（测试用 fake），缺省构造真实 OpenAI 客户端
    """
    def __init__(self, settings: Optional[Settings] = None, client: Any = None) -> None:
        self.settings = settings or Settings()
        if client is not None:
            self.client = client
        else:
            self.client = OpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url)
        self.total_calls: int = 0          # 累计调用次数
        self.usages: list[Any] = []        # 每次 usage 记录

    def complete(
        self,
        *,
        model: str,
        instructions: str,
        input_content: str,
        effort: str = "medium",
        verbosity: str = "low",
        schema: Optional[Type[BaseModel]] = None,
    ) -> Any:
        """调用 LLM 并返回结构化结果

        参数:
            model: 部署名，如 gpt-5.4 / gpt-5.4-mini
            instructions: 系统指令
            input_content: 用户输入内容
            effort: 推理强度 low/medium/high
            verbosity: 输出详尽度 low/medium/high
            schema: Pydantic 模型类；提供则走结构化输出，返回该类型实例
        返回:
            schema 实例（提供 schema 时）或纯文本字符串
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_content,
            "reasoning": {"effort": effort},
            "text": {"verbosity": verbosity},
        }
        if schema is not None:
            kwargs["text_format"] = schema
            response = self.client.responses.parse(**kwargs)
            self._record(response)
            return response.output_parsed
        response = self.client.responses.create(**kwargs)
        self._record(response)
        return response.output_text

    def _record(self, response: Any) -> None:
        """记录用量——内部辅助"""
        self.total_calls += 1
        self.usages.append(getattr(response, "usage", None))
