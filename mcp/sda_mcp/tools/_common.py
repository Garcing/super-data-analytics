"""工具层共享：mcp 实例 + dataclass→dict 转换。

设计文档原列 runner.py，其职责（内核 dataclass → MCP 结果、错误包装）折叠到此。
错误：内核抛 SkillError，FastMCP 自动转 isError:true（无需手动捕获）。

鉴权接线决策（实测 mcp 2.0.0）：
MCPServer.__init__ 接受 token_verifier / auth 关键字参数（构造期传入）。
因此这里在导入期根据 SDA_MCP_TOKEN 是否存在，一次性建好带鉴权的 mcp 实例：
- 有 token → 传 StaticTokenVerifier + AuthSettings，未授权请求得 401；
- 无 token → 裸实例，本地可裸跑测试。
工具用 @mcp.tool 注册到此实例。
"""
from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any

# 单一 mcp 实例，各 tools/*.py 用 @mcp.tool 注册到它
try:
    from mcp.server import MCPServer as _Server
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp import FastMCP as _Server


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
