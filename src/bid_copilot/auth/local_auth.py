"""本地认证核心——内存会话存储 + 凭据校验（PoC 级，重启即失效）"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

from bid_copilot.config import Settings

# 内存会话表：token → (用户名, 过期时间)；进程级，重启清空
_sessions: dict[str, tuple[str, datetime]] = {}


def _cleanup_expired_sessions() -> None:
    """清除已过期会话，保持内存表有界——内部辅助；无参数无返回值"""
    now: datetime = datetime.now(timezone.utc)
    expired: list[str] = [token for token, (_, expires_at) in _sessions.items() if expires_at <= now]
    for token in expired:
        _sessions.pop(token, None)


def validate_credentials(username: str, password: str) -> bool:
    """校验提交的用户名/密码是否匹配配置

    参数:
        username: 提交的用户名
        password: 提交的密码
    返回:
        匹配为 True；认证关闭时直接 True。用 hmac.compare_digest 防时序攻击
    """
    settings: Settings = Settings()
    if not settings.enable_local_auth:
        return True
    return (
        hmac.compare_digest(username or "", settings.local_auth_username)
        and hmac.compare_digest(password or "", settings.local_auth_password)
    )


def create_session(username: str) -> str:
    """为已认证用户创建新会话并返回不透明 token

    参数:
        username: 已通过校验的用户名
    返回:
        新生成的会话 token（写入内存表，按配置时长过期）
    """
    settings: Settings = Settings()
    _cleanup_expired_sessions()
    token: str = secrets.token_urlsafe(32)
    expires_at: datetime = datetime.now(timezone.utc) + timedelta(hours=settings.local_auth_session_hours)
    _sessions[token] = (username, expires_at)
    return token


def get_session_username(token: str | None) -> str | None:
    """由会话 token 解析用户名（会话存在且未过期时）

    参数:
        token: 会话 token（可为 None）
    返回:
        有效则返回用户名，否则 None（过期会话顺带清除）
    """
    if not token:
        return None
    _cleanup_expired_sessions()
    row: tuple[str, datetime] | None = _sessions.get(token)
    if not row:
        return None
    username, expires_at = row
    if expires_at <= datetime.now(timezone.utc):
        _sessions.pop(token, None)
        return None
    return username


def delete_session(token: str | None) -> None:
    """从内存表删除一个会话 token——用于登出

    参数:
        token: 会话 token（可为 None，None 时无操作）
    返回:
        无
    """
    if token:
        _sessions.pop(token, None)
