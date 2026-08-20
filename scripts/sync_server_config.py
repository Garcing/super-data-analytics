"""Validate and securely synchronize the canonical SDA config to a server.

The transferred JSON stays identical to the local canonical file. Machine-specific
values such as HOLOGRES_HOST/PORT belong in the server's ~/sda-mcp/.env and are
overlaid by sda_mcp.config.get_env().
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


REMOTE_DIR = "~/.super-data-analytics"
REMOTE_CONFIG = f"{REMOTE_DIR}/config.json"
REMOTE_UPLOAD = f"{REMOTE_DIR}/config.json.upload"


def _validate_source(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"配置文件不是有效 JSON: {exc}") from exc
    if not isinstance(config.get("env"), dict):
        raise SystemExit("配置缺少 env 对象")
    graph = config.get("graph-config")
    if not isinstance(graph, dict) or not isinstance(graph.get("entities"), dict):
        raise SystemExit("配置缺少 graph-config.entities")
    digest = hashlib.sha256(raw).hexdigest()
    return digest, len(graph["entities"])


def _run(args: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        args,
        check=True,
        text=True,
        capture_output=capture,
    )
    return completed.stdout.strip() if capture else ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="安全同步 SDA config.json；不会打印配置正文或密钥。"
    )
    parser.add_argument("--host", default="hermes", help="SSH 主机或别名，默认 hermes")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / ".super-data-analytics" / "config.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="只做本地校验")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", args.host):
        raise SystemExit("SSH host 只能包含字母、数字、点、下划线、@ 和连字符")
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"配置文件不存在: {source}")

    local_hash, entity_count = _validate_source(source)
    print(f"本地配置校验通过：{entity_count} 个语义实体")
    if args.dry_run:
        return

    _run(["ssh", args.host, f"mkdir -p {REMOTE_DIR} && chmod 700 {REMOTE_DIR}"])
    _run(["scp", "-q", str(source), f"{args.host}:{REMOTE_UPLOAD}"])
    _run([
        "ssh",
        args.host,
        (
            "set -eu; "
            f"chmod 600 {REMOTE_UPLOAD}; "
            f"if [ -f {REMOTE_CONFIG} ]; then cp -p {REMOTE_CONFIG} {REMOTE_CONFIG}.bak; fi; "
            f"mv {REMOTE_UPLOAD} {REMOTE_CONFIG}"
        ),
    ])
    remote_output = _run(
        ["ssh", args.host, f"sha256sum {REMOTE_CONFIG}"], capture=True
    )
    remote_hash = remote_output.split()[0] if remote_output else ""
    if remote_hash != local_hash:
        raise SystemExit("服务器配置哈希与本机不一致")
    print("服务器配置同步完成，SHA-256 校验一致；配置正文未输出")


if __name__ == "__main__":
    main()
