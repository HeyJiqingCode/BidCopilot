"""本地认证测试——开关、登录、会话守卫（monkeypatch 环境变量切换认证）"""
import io
from fastapi.testclient import TestClient
from bid_copilot.api import main as api_main


def _enable_auth(monkeypatch) -> None:
    """打开本地认证并设默认账号——测试辅助；无返回值"""
    monkeypatch.setenv("ENABLE_LOCAL_AUTH", "true")
    monkeypatch.setenv("LOCAL_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_AUTH_PASSWORD", "admin123")


def test_auth_disabled_allows_all(monkeypatch):
    """认证关闭时，根路径与 API 直接放行（200）"""
    monkeypatch.setenv("ENABLE_LOCAL_AUTH", "false")
    client = TestClient(api_main.app)
    assert client.get("/").status_code == 200
    assert client.get("/api/runs").status_code == 200


def test_login_rejects_bad_credentials(monkeypatch):
    """认证开启时，错误密码登录返回 401"""
    _enable_auth(monkeypatch)
    client = TestClient(api_main.app)
    resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_then_access(monkeypatch):
    """对的凭据登录拿到 cookie → 带 cookie 访问受保护路径 200，会话查询为已登录"""
    _enable_auth(monkeypatch)
    client = TestClient(api_main.app)
    login = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    # 登录后 TestClient 自动携带返回的 cookie
    assert client.get("/").status_code == 200
    sess = client.get("/auth/session").json()
    assert sess["authenticated"] is True
    assert sess["username"] == "admin"


def test_unauthed_redirect_and_401(monkeypatch):
    """认证开启且无 cookie：根路径 302 跳 /login，API 返 401"""
    _enable_auth(monkeypatch)
    client = TestClient(api_main.app)
    # 根路径应重定向到登录页（关掉自动跟随才能断言 302）
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 302
    assert root.headers["location"] == "/login"
    # 受保护 API 无凭据返 401
    assert client.get("/api/runs").status_code == 401
    # 登录页本身是公开路径，可直接访问
    assert client.get("/login").status_code == 200
