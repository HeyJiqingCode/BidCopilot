"""本地认证 HTTP 中间件——守卫页面与 API，未登录则重定向/拒绝"""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from bid_copilot.config import Settings
from bid_copilot.auth.local_auth import get_session_username

# 无需登录即可访问的公开路径（登录页、认证接口、图标）
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/login", "/auth/login", "/auth/session", "/auth/logout", "/favicon.ico"}
)


def _is_public_path(path: str) -> bool:
    """判断请求路径是否豁免认证检查

    参数:
        path: 请求 URL 的 path 部分
    返回:
        公开路径（含 /static/ 前缀）返回 True
    """
    if path in _PUBLIC_PATHS:
        return True
    if path.startswith("/static/"):
        return True
    return False


def register_local_auth_middleware(app: FastAPI) -> None:
    """注册本地认证中间件，守卫应用页面与 API 路由

    参数:
        app: FastAPI 应用实例
    返回:
        无（以副作用方式挂载中间件）
    """

    @app.middleware("http")
    async def local_auth_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """逐请求校验会话；认证关闭或公开路径直接放行——内部中间件"""
        settings: Settings = Settings()
        if not settings.enable_local_auth:
            return await call_next(request)

        path: str = request.url.path
        if _is_public_path(path):
            return await call_next(request)

        token: str | None = request.cookies.get(settings.local_auth_cookie_name)
        username: str | None = get_session_username(token)
        if username:
            request.state.auth_user = username
            return await call_next(request)

        # 未登录：根路径重定向到登录页，其余按 API 返回 401
        if path == "/":
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(status_code=401, content={"detail": "需要登录后访问。"})
