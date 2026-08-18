"""静态 Bearer token 鉴权（MCP v2 TokenVerifier）。

单 token：环境变量 SDA_MCP_TOKEN（或 config.json env）。hermes/笔记本经 Caddy 都带同一 token。
"""
from __future__ import annotations

import os

from mcp.server.auth.provider import AccessToken, TokenVerifier

# token 来源：SDA_MCP_TOKEN 环境变量（容器 run 时注入；镜像不含密钥）
_EXPECTED = os.environ.get("SDA_MCP_TOKEN", "")


class StaticTokenVerifier(TokenVerifier):
    """校验单个静态 Bearer token。token 匹配 → AccessToken；否则 None（→ 401）。"""

    async def verify_token(self, token: str) -> AccessToken | None:
        if _EXPECTED and token and token == _EXPECTED:
            return AccessToken(token=token, client_id="sda", scopes=[])
        return None
