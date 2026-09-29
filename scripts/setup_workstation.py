"""维护工作站一次性接入：迁移配置密钥、安装 hermes SSH 别名、验证连通。

仓库不含任何凭证。新维护机或换机后执行一次：

    python scripts/setup_workstation.py

幂等完成三件事：
1. config.json：本机真相源约定在仓库根目录；旧位置 ~/.super-data-analytics/ 存在
   且根目录缺失时自动搬移（搬移前校验 JSON）。
2. tencent-lighthouse.pem：~/.ssh/ 存在旧副本且根目录缺失时复制过来。
3. ~/.ssh/config：写入带标记的受管 Host hermes 块（IdentityFile 指向根目录密钥），
   重建已有受管块，不动其他内容；若存在非受管 hermes 块则提示手动清理。
最后用 ssh -G 校验生效身份文件，并做一次真实连通探测。

不打印任何密钥内容。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "config.json"
PEM = REPO_ROOT / "tencent-lighthouse.pem"
LEGACY_CONFIG = Path.home() / ".super-data-analytics" / "config.json"
LEGACY_PEM = Path.home() / ".ssh" / "tencent-lighthouse.pem"
SSH_CONFIG = Path.home() / ".ssh" / "config"

BEGIN_MARK = "# BEGIN super-data-analytics (managed by scripts/setup_workstation.py)"
END_MARK = "# END super-data-analytics (managed by scripts/setup_workstation.py)"
MANAGED_BLOCK_RE = re.compile(
    rf"^\s*{re.escape(BEGIN_MARK)}.*?^\s*{re.escape(END_MARK)}\n?",
    re.M | re.S,
)

HERMES_HOST = "106.53.74.143"
HERMES_USER = "ubuntu"


def _ok(msg: str) -> None:
    print(f"[ok] {msg}")


def _warn(msg: str) -> None:
    print(f"[警告] {msg}")


def _fail(msg: str) -> None:
    print(f"[失败] {msg}")
    sys.exit(1)


def migrate_config() -> None:
    if CONFIG.is_file():
        _ok(f"config.json 已在仓库根目录: {CONFIG}")
        if LEGACY_CONFIG.is_file():
            _warn("旧位置 ~/.super-data-analytics/config.json 仍存在；确认根目录为真相源后手动删除")
        return
    if not LEGACY_CONFIG.is_file():
        _fail(f"缺少 config.json：根目录与旧位置 {LEGACY_CONFIG} 均不存在，需从原维护机或备份取得")
    try:
        config = json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"旧配置不是有效 JSON，未搬移: {exc}")
    if not isinstance(config.get("env"), dict):
        _fail("旧配置缺少 env 对象，未搬移")
    shutil.move(str(LEGACY_CONFIG), str(CONFIG))
    _ok(f"config.json 已从旧位置迁至仓库根目录: {CONFIG}")


def migrate_pem() -> None:
    if PEM.is_file():
        _ok(f"登录密钥已在仓库根目录: {PEM.name}")
        return
    if not LEGACY_PEM.is_file():
        _fail(
            f"缺少 {PEM.name}：根目录与 {LEGACY_PEM} 均不存在，"
            "需从原维护机复制或到云控制台重绑密钥对"
        )
    shutil.copy2(LEGACY_PEM, PEM)
    _ok(f"登录密钥已复制到仓库根目录: {PEM.name}")


def _managed_block() -> str:
    # ssh_config 中 IdentityFile 用正斜杠，Windows OpenSSH 同样接受
    return (
        f"{BEGIN_MARK}\n"
        f"Host hermes\n"
        f"    HostName {HERMES_HOST}\n"
        f"    User {HERMES_USER}\n"
        f"    IdentityFile {PEM.as_posix()}\n"
        f"    IdentitiesOnly yes\n"
        f"{END_MARK}\n"
    )


def install_ssh_block() -> None:
    SSH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing = SSH_CONFIG.read_text(encoding="utf-8") if SSH_CONFIG.is_file() else ""
    # 重建受管块：移除旧受管块后追加新块，其余内容原样保留
    cleaned = MANAGED_BLOCK_RE.sub("", existing).rstrip("\n")
    content = (cleaned + "\n\n" if cleaned else "") + _managed_block()
    SSH_CONFIG.write_text(content, encoding="utf-8")
    _ok("已写入 ~/.ssh/config 受管 Host hermes 块")
    # ssh 按首次匹配生效：非受管 hermes 块在前会遮蔽受管块
    if re.search(r"^\s*Host\s+\S*hermes\b", MANAGED_BLOCK_RE.sub("", existing), re.M):
        _warn("~/.ssh/config 存在本脚本管理范围外的 Host hermes 块，可能遮蔽受管配置；请手动删除后重跑")


def _norm(path: str) -> str:
    return Path(path).expanduser().resolve().as_posix().lower()


def verify() -> None:
    if shutil.which("ssh") is None:
        _fail("未找到 ssh 命令；Windows 请先启用 OpenSSH 客户端")
    effective = subprocess.run(
        ["ssh", "-G", "hermes"], capture_output=True, text=True
    )
    if effective.returncode != 0:
        _fail(f"ssh -G hermes 失败: {effective.stderr.strip()}")
    identities = [
        line.split(None, 1)[1].strip()
        for line in effective.stdout.splitlines()
        if line.lower().startswith("identityfile ")
    ]
    if not any(_norm(i) == _norm(str(PEM)) for i in identities):
        _fail(
            "hermes 生效身份文件不是仓库根目录密钥"
            f"（生效: {identities}）；检查 ~/.ssh/config 是否有遮蔽块"
        )
    _ok("ssh -G hermes 生效身份文件指向仓库根目录密钥")
    probe = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "hermes", "true"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        _fail(f"ssh hermes 连通验证失败: {probe.stderr.strip()}")
    _ok("ssh hermes 连通验证通过")


def main() -> None:
    print(f"== SDA 工作站接入（仓库: {REPO_ROOT}）==")
    migrate_config()
    migrate_pem()
    install_ssh_block()
    verify()
    _ok("接入完成。GitHub 推送凭证按需配置：gh auth login，或首次 push 时按凭证管理器提示操作")


if __name__ == "__main__":
    main()
