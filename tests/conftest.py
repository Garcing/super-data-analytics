"""pytest 配置：确保可以从仓库根目录导入 sda_mcp。"""
import sys
from pathlib import Path

# 仓库根目录（conftest 位于 tests/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 让 `import sda_mcp` 可用（pyproject 的 pythonpath 也配了，这里双保险）
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
