"""工具层共享：mcp 实例 + dataclass→dict 转换 + 错误映射装饰器。

设计文档原列 runner.py，其职责（内核 dataclass → MCP 结果、错误包装）折叠到此。
错误：内核抛 SkillError 后必须用 map_tool_errors 显式映射为 ToolError——
mcp 2.1.0 起 SDK 把未捕获异常包成 UnexpectedToolError("Error executing tool <名>")
并丢弃原始消息（2.0.x 会附带消息，升级时错误语义静默回归），显式 ToolError
才能保证客户端拿到类型与原因，行为不随 SDK 版本漂移。

鉴权接线决策（实测 mcp 2.0.0）：
MCPServer.__init__ 接受 token_verifier / auth 关键字参数（构造期传入）。
因此这里在导入期根据 SDA_MCP_TOKEN 是否存在，一次性建好带鉴权的 mcp 实例：
- 有 token → 传 StaticTokenVerifier + AuthSettings，未授权请求得 401；
- 无 token → 裸实例，本地可裸跑测试。
工具用 @mcp.tool 注册到此实例。
"""
from __future__ import annotations

import functools
import logging
import os
from dataclasses import asdict, is_dataclass
from typing import Any

from sda_mcp.errors import SkillError

# 单一 mcp 实例，各 tools/*.py 用 @mcp.tool 注册到它
try:
    from mcp.server import MCPServer as _Server
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp import FastMCP as _Server

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore

logger = logging.getLogger("sda_mcp.tools")


def map_tool_errors(fn):
    """把工具执行异常映射为 ``[错误类型] 原因`` 的 ToolError。

    - SkillError 子类：类型名 + 消息（可操作排错信息直达客户端）；
    - 意外异常：同样透出类型与消息，完整堆栈记入服务端日志。
    必须放在 @mcp.tool 之下直接包裹工具函数（functools.wraps 保留签名供
    SDK 生成入参 schema）。
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except SkillError as exc:
            raise ToolError(f"[{type(exc).__name__}] {exc}") from exc
        except Exception as exc:
            logger.exception("工具 %s 执行意外失败", getattr(fn, "__name__", "?"))
            raise ToolError(f"[{type(exc).__name__}] {exc}") from exc

    return wrapper


def _build_server() -> _Server:
    token = os.environ.get("SDA_MCP_TOKEN", "")
    if token:
        try:
            from pydantic import AnyHttpUrl
            from mcp.server.auth.settings import AuthSettings
            from sda_mcp.auth import StaticTokenVerifier
            auth = AuthSettings(
                issuer_url=AnyHttpUrl("http://localhost"),
                resource_server_url=AnyHttpUrl("http://localhost:3100/mcp"),
                required_scopes=[],
            )
            return _Server("sda", token_verifier=StaticTokenVerifier(), auth=auth)
        except Exception:
            # 鉴权组件不可用 → 退化为裸实例（仍可跑，仅无鉴权）
            pass
    return _Server("sda")


mcp = _build_server()


def tool_annotations(
    title: str,
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> dict[str, Any]:
    """Build a complete MCP ToolAnnotations mapping.

    Keeping every hint explicit avoids inheriting the protocol defaults
    (notably destructiveHint=true) when a client renders or gates a tool.
    """
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }


def to_dict(obj: Any) -> dict[str, Any]:
    """把内核返回（dataclass / dict）转成 JSON 安全 dict（丢 bytes）。
    dataclass 经 asdict；dict 原样；其余包成 {"result": obj}。"""
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return _strip_bytes(asdict(obj))
    return {"result": obj}


def _strip_bytes(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (bytes, bytearray)):
            continue
        out[k] = v
    return out
