"""Content Understanding 封装——非 docx 文档的版面+表格还原（GA 2025-11-01）"""
import time
from pathlib import Path
from typing import Optional, Any
import requests
from pydantic import BaseModel

_API_VERSION = "2025-11-01"
_ANALYZER_ID = "prebuilt-layout"   # 版面/表格还原（不调 LLM，比 documentSearch 更省）
_POLL_INTERVAL_S = 3
_POLL_MAX_TRIES = 80


class CUResult(BaseModel):
    """CU 分析结果"""
    markdown: str
    page_count: Optional[int] = None


class CUClient:
    """Azure AI Content Understanding REST 客户端

    参数:
        endpoint: 资源端点，如 https://<res>.cognitiveservices.azure.com
        key: 订阅密钥
    """
    def __init__(self, endpoint: str, key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key

    def analyze(self, file_path: Path) -> CUResult:
        """上传文件字节给 CU，轮询取结构化 markdown

        参数:
            file_path: 待分析文件
        返回:
            CUResult（含 markdown）；失败抛异常由调用方降级
        """
        with open(file_path, "rb") as f:
            data = f.read()
        url = (f"{self.endpoint}/contentunderstanding/analyzers/"
               f"{_ANALYZER_ID}:analyzeBinary?api-version={_API_VERSION}")
        resp = requests.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": self.key,
                     "Content-Type": "application/octet-stream"},
            data=data, timeout=120,
        )
        resp.raise_for_status()
        op_url = resp.headers["Operation-Location"]
        for _ in range(_POLL_MAX_TRIES):
            poll = requests.get(op_url, headers={"Ocp-Apim-Subscription-Key": self.key}, timeout=60)
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
            if status == "Succeeded":
                contents = body["result"]["contents"]
                markdown = contents[0].get("markdown", "") if contents else ""
                return CUResult(markdown=markdown, page_count=None)
            if status in ("Failed", "Canceled"):
                raise RuntimeError(f"CU 分析 {status}: {body.get('error')}")
            time.sleep(_POLL_INTERVAL_S)
        raise RuntimeError("CU 分析轮询超时")


def analyze_with_cu(file_path: Path, cu: Any) -> CUResult:
    """用 Content Understanding 分析文件

    参数:
        file_path: 待分析文件
        cu: CU 客户端（须有 analyze(path)->CUResult）；None 表示未配置
    返回:
        CUResult；cu 为 None 时返回空 markdown（优雅降级）
    """
    if cu is None:
        return CUResult(markdown="", page_count=None)
    return cu.analyze(file_path)


def build_cu_client(endpoint: str, key: str) -> Optional[CUClient]:
    """按配置构造 CU 客户端；endpoint/key 缺失则返回 None——内部辅助

    参数:
        endpoint: CU 端点
        key: CU 密钥
    返回:
        CUClient 或 None（未配置时调用方走本地兜底）
    """
    if endpoint and key:
        return CUClient(endpoint=endpoint, key=key)
    return None
