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
    # 最轻量模型部署名（nano 档，最快最省，适合极简任务/用户自测提速）
    model_nano: str = field(default_factory=lambda: os.getenv("MODEL_NANO", "gpt-5.4-nano"))
    # Content Understanding 端点（可选，缺省为空字符串）
    cu_endpoint: str = field(default_factory=lambda: os.getenv("CU_ENDPOINT", ""))
    # Content Understanding 密钥（可选，缺省为空字符串）
    cu_key: str = field(default_factory=lambda: os.getenv("CU_KEY", ""))
    # 是否启用本地登录门（Demo 部署用；false 则完全放行，默认行为不变）
    enable_local_auth: bool = field(default_factory=lambda: os.getenv("ENABLE_LOCAL_AUTH", "false").lower() == "true")
    # 本地登录用户名
    local_auth_username: str = field(default_factory=lambda: os.getenv("LOCAL_AUTH_USERNAME", "admin"))
    # 本地登录密码
    local_auth_password: str = field(default_factory=lambda: os.getenv("LOCAL_AUTH_PASSWORD", "admin123"))
    # 会话有效小时数
    local_auth_session_hours: int = field(default_factory=lambda: int(os.getenv("LOCAL_AUTH_SESSION_HOURS", "24")))
    # 会话 cookie 名
    local_auth_cookie_name: str = field(default_factory=lambda: os.getenv("LOCAL_AUTH_COOKIE_NAME", "bid_copilot_session"))
    # 并行调用上限（extract 章节并行 + merge 阶段B 分批并行共用）
    max_concurrency: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENCY", "5")))
    # 各管线步骤的模型档位（main/mini/nano）；默认 classify=mini、其余 main，可经 env 切换试 mini/nano 提速
    model_classify: str = field(default_factory=lambda: os.getenv("MODEL_CLASSIFY", "mini"))
    model_locate: str = field(default_factory=lambda: os.getenv("MODEL_LOCATE", "main"))
    model_skeleton: str = field(default_factory=lambda: os.getenv("MODEL_SKELETON", "main"))
    model_requirements: str = field(default_factory=lambda: os.getenv("MODEL_REQUIREMENTS", "main"))
    model_merge: str = field(default_factory=lambda: os.getenv("MODEL_MERGE", "main"))
    model_supplement: str = field(default_factory=lambda: os.getenv("MODEL_SUPPLEMENT", "main"))
    # 各管线步骤的推理强度 effort（low/medium/high）；默认维持各步现状，可经 env 覆盖
    effort_classify: str = field(default_factory=lambda: os.getenv("EFFORT_CLASSIFY", "low"))
    effort_locate: str = field(default_factory=lambda: os.getenv("EFFORT_LOCATE", "medium"))
    effort_skeleton: str = field(default_factory=lambda: os.getenv("EFFORT_SKELETON", "medium"))
    effort_requirements: str = field(default_factory=lambda: os.getenv("EFFORT_REQUIREMENTS", "medium"))
    effort_merge: str = field(default_factory=lambda: os.getenv("EFFORT_MERGE", "high"))
    effort_supplement: str = field(default_factory=lambda: os.getenv("EFFORT_SUPPLEMENT", "high"))
