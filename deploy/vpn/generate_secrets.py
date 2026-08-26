"""从 config.json 生成 VPN 转发器部署密钥（服务器上执行）。

读取 ~/.super-data-analytics/config.json 的 env 块：
  - VPN_TA_KEY_B64           -> runtime/ta.key（600，tls-auth 静态密钥）
  - VPN_USERNAME/VPN_PASSWORD -> .env（600，compose 注入容器，entrypoint 自动写 pass.txt）

不打印任何密钥内容。用法：
  python3 deploy/vpn/generate_secrets.py [--config /path/to/config.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime"
TA_KEY_MARKERS = (b"2048 bit OpenVPN static key", b"BEGIN OpenVPN Static key V1")
# compose dotenv 裸值安全字符集；含空白/引号/#/=/$ 的值必须人工介入
UNSAFE_ENV_CHARS = re.compile(r"""[\s'"#=$`\\]""")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".super-data-analytics" / "config.json",
    )
    args = parser.parse_args()

    env = json.loads(args.config.read_text(encoding="utf-8"))["env"]
    for key in ("VPN_TA_KEY_B64", "VPN_USERNAME", "VPN_PASSWORD"):
        if not env.get(key):
            raise SystemExit(f"config.json env.{key} 缺失或为空")

    ta_key = base64.b64decode(env["VPN_TA_KEY_B64"])
    if not any(marker in ta_key for marker in TA_KEY_MARKERS):
        raise SystemExit("VPN_TA_KEY_B64 解码后不像 OpenVPN 静态密钥（缺少标识行）")

    for key in ("VPN_USERNAME", "VPN_PASSWORD"):
        if UNSAFE_ENV_CHARS.search(str(env[key])):
            raise SystemExit(f"env.{key} 含 .env 不安全字符，请人工处理 deploy/vpn/.env")

    RUNTIME.mkdir(parents=True, exist_ok=True)
    ta_path = RUNTIME / "ta.key"
    ta_path.write_bytes(ta_key)
    ta_path.chmod(0o600)

    env_file = HERE / ".env"
    env_file.write_text(
        "VPN_USERNAME=%s\nVPN_PASSWORD=%s\n" % (env["VPN_USERNAME"], env["VPN_PASSWORD"]),
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    print(f"已生成 {ta_path.name} 与 .env（内容未打印），权限 600")


if __name__ == "__main__":
    main()
