"""pytest 全局夹具——保证单测与本地 .env 无关"""
import pytest


@pytest.fixture(autouse=True)
def _disable_local_auth_by_default(monkeypatch):
    """默认关闭本地认证——避免本地 .env 里 ENABLE_LOCAL_AUTH=true 干扰非认证测试

    需要开启认证的测试（test_auth.py）在用例内自行 monkeypatch.setenv 覆盖，
    其优先级高于本夹具，互不冲突。每个测试结束后 monkeypatch 自动还原。
    """
    monkeypatch.setenv("ENABLE_LOCAL_AUTH", "false")
