"""统一读取 ~/.super-data-analytics/config.json。后续所有需要凭证的内核共用。"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from sda_mcp.errors import ConfigError

DEFAULT_CONFIG_PATH = Path(os.environ.get(
    "SDA_CONFIG_PATH", Path.home() / ".super-data-analytics" / "config.json"))


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    try:
        return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {DEFAULT_CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件解析失败 {DEFAULT_CONFIG_PATH}: {exc}") from exc


def get_env(*keys: str) -> dict[str, str]:
    env = load_config().get("env", {})
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise ConfigError(f"配置缺少: {', '.join(missing)}（请在 config.json 的 env 块补全）")
    return {k: str(env[k]) for k in keys}
