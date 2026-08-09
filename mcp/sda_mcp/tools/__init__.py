"""导入各分组以触发 @mcp.tool 注册。

鉴权接线决策（实测 mcp 2.0.0）：MCPServer.__init__ 接受 token_verifier 与 auth
构造参数；tools/_common.py 在导入期根据 SDA_MCP_TOKEN 是否存在一次性建好带鉴权的
mcp 实例（有 token → StaticTokenVerifier + AuthSettings，未授权请求 401；无 token
→ 裸实例，本地可裸跑测试）。本包各 tools/*.py 用 @mcp.tool 注册到该实例。
"""
from sda_mcp.tools import query_tools      # noqa: F401
from sda_mcp.tools import retrieve_tools   # noqa: F401
from sda_mcp.tools import analyze_tools    # noqa: F401
from sda_mcp.tools import viz_tools        # noqa: F401
from sda_mcp.tools import report_tools     # noqa: F401
from sda_mcp.tools import template_tools   # noqa: F401


def register_all() -> None:
    """显式注册点（server.py 调用以确保导入）。模块导入即注册，此函数仅作锚点。"""
    pass
