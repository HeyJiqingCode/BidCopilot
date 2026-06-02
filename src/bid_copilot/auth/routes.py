"""本地认证路由——登录态查询 / 登录 / 登出"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bid_copilot.config import Settings
from bid_copilot.auth.local_auth import (
    create_session,
    delete_session,
    get_session_username,
    validate_credentials,
)

router: APIRouter = APIRouter()


class LoginRequest(BaseModel):
    """登录请求体——用户名与密码"""
    username: str
    password: str


@router.get("/auth/session")
def auth_session(request: Request) -> dict:
    """返回当前登录状态，供登录页与前端检查

    参数:
        request: 请求对象（用于读取会话 cookie）
    返回:
        含 authenticated/username/auth_enabled 的字典
    """
    settings: Settings = Settings()
    if not settings.enable_local_auth:
        return {"authenticated": True, "username": "anonymous", "auth_enabled": False}
    token: str | None = request.cookies.get(settings.local_auth_cookie_name)
    username: str | None = get_session_username(token)
    return {
        "authenticated": bool(username),
        "username": username or "",
        "auth_enabled": True,
    }


@router.post("/auth/login")
def auth_login(req: LoginRequest) -> JSONResponse:
    """校验本地凭据并下发会话 cookie

    参数:
        req: 含 username/password 的登录请求体
    返回:
        成功返回带 Set-Cookie 的 JSON；凭据错误抛 401
    """
    settings: Settings = Settings()
    if not settings.enable_local_auth:
        return JSONResponse({"ok": True, "auth_enabled": False})
    if not validate_credentials(req.username.strip(), req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    token: str = create_session(req.username.strip())
    resp: JSONResponse = JSONResponse(
        {"ok": True, "username": req.username.strip(), "auth_enabled": True}
    )
    resp.set_cookie(
        key=settings.local_auth_cookie_name,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=max(60, settings.local_auth_session_hours * 3600),
        path="/",
    )
    return resp


@router.post("/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    """清除会话 cookie 并删除对应的本地会话

    参数:
        request: 请求对象（用于读取会话 cookie）
    返回:
        清除 cookie 后的 JSON 响应
    """
    settings: Settings = Settings()
    if settings.enable_local_auth:
        token: str | None = request.cookies.get(settings.local_auth_cookie_name)
        delete_session(token)
    resp: JSONResponse = JSONResponse({"ok": True})
    resp.delete_cookie(key=settings.local_auth_cookie_name, path="/")
    return resp
