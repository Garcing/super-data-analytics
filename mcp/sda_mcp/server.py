"""FastMCP(v2 MCPServer) 入口：stateless JSON HTTP，静态 Bearer 鉴权，注册 24 工具。

运行：SDA_MCP_TOKEN=<token> python -m sda_mcp.server
端点：http://0.0.0.0:3100/mcp

鉴权：tools/_common.py 在导入期按 SDA_MCP_TOKEN 决定是否给 mcp 实例挂
StaticTokenVerifier + AuthSettings（详见 tools/__init__.py 顶部决策注释）。
"""
from __future__ import annotations

import os

from sda_mcp.tools import register_all  # noqa: F401  触发各 tools/*.py 的 @mcp.tool
from sda_mcp.tools._common import mcp


def main() -> None:
    # 远程工具调用不依赖跨请求状态；JSON 响应避免为单次结果维持 SSE 长连接。
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("SDA_MCP_PORT", "3100")),
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
