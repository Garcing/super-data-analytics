"""pytest 配置：暴露 sda_mcp import 路径，并提供仓库根与原 CLI 路径 fixture。"""
import sys
from pathlib import Path

# mcp/ 目录本身（conftest 在 mcp/tests/ 下，上两级是仓库根，上一级是 mcp/）
MCP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MCP_DIR.parent

# 让 `import sda_mcp` 可用（pyproject 的 pythonpath 也配了，这里双保险）
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def venv_python() -> str:
    """跑原 CLI 用的解释器（与跑 pytest 同一个即可）。"""
    return sys.executable
