"""配置加载测试"""
import os
from bid_copilot.config import Settings


def test_settings_from_env(monkeypatch):
    """从环境变量读取配置"""
    monkeypatch.setenv("FOUNDRY_API_KEY_AOAI", "k123")
    monkeypatch.setenv("AOAI_BASE_URL", "https://x/openai/v1/")
    monkeypatch.setenv("MODEL_MAIN", "gpt-5.4")
    monkeypatch.setenv("MODEL_MINI", "gpt-5.4-mini")
    monkeypatch.setenv("MODEL_NANO", "gpt-5.4-nano")
    s = Settings()
    assert s.api_key == "k123"
    assert s.base_url.endswith("/openai/v1/")
    assert s.model_main == "gpt-5.4"
    assert s.model_mini == "gpt-5.4-mini"
    assert s.model_nano == "gpt-5.4-nano"


def test_settings_cu_optional(monkeypatch):
    """CU 配置可选，缺省为空字符串"""
    monkeypatch.setenv("FOUNDRY_API_KEY_AOAI", "k")
    monkeypatch.setenv("AOAI_BASE_URL", "https://x/openai/v1/")
    monkeypatch.delenv("CU_ENDPOINT", raising=False)
    s = Settings()
    assert s.cu_endpoint == ""
