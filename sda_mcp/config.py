"""统一读取 config.json。解析顺序：SDA_CONFIG_PATH → 仓库根目录 → ~/.super-data-analytics 回退。后续所有需要凭证的内核共用。"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from sda_mcp.errors import ConfigError

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _default_config_path() -> Path:
    if "SDA_CONFIG_PATH" in os.environ:
        return Path(os.environ["SDA_CONFIG_PATH"])
    # 本机真相源约定在仓库根目录；服务器容器由 SDA_CONFIG_PATH 显式指定，
    # 旧 home 路径仅作回退，兼容既有部署与本机旧布局。
    repo_config = _REPO_ROOT / "config.json"
    if repo_config.is_file():
        return repo_config
    return Path.home() / ".super-data-analytics" / "config.json"


DEFAULT_CONFIG_PATH = _default_config_path()


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    try:
        return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {DEFAULT_CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件解析失败 {DEFAULT_CONFIG_PATH}: {exc}") from exc


def get_env(*keys: str) -> dict[str, str]:
    config_env = load_config().get("env", {})
    # 部署环境可以覆盖机器相关配置；空环境变量不遮蔽 config.json。
    # 例如服务器通过 .env 覆盖 HOLOGRES_HOST/PORT，本机仍使用配置文件值。
    env = {k: os.environ.get(k) or config_env.get(k) for k in keys}
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise ConfigError(f"配置缺少: {', '.join(missing)}（请在 config.json 的 env 块补全）")
    return {k: str(env[k]) for k in keys}
