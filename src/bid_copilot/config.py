"""配置加载——从 .env / 环境变量读取运行参数"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """运行配置；字段默认从环境变量读取（每次实例化时求值，尊重运行时 env 变更）"""
    # Azure OpenAI 访问密钥
    api_key: str = field(default_factory=lambda: os.getenv("FOUNDRY_API_KEY_AOAI", ""))
    # Azure OpenAI v1 preview 端点（以 /openai/v1/ 结尾）
    base_url: str = field(default_factory=lambda: os.getenv("AOAI_BASE_URL", ""))
    # 主模型部署名
    model_main: str = field(default_factory=lambda: os.getenv("MODEL_MAIN", "gpt-5.4"))
    # 轻量模型部署名
    model_mini: str = field(default_factory=lambda: os.getenv("MODEL_MINI", "gpt-5.4-mini"))
    # Content Understanding 端点（可选，缺省为空字符串）
    cu_endpoint: str = field(default_factory=lambda: os.getenv("CU_ENDPOINT", ""))
    # Content Understanding 密钥（可选，缺省为空字符串）
    cu_key: str = field(default_factory=lambda: os.getenv("CU_KEY", ""))
