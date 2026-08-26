"""MCP 手动调试脚本（纯标准库，零依赖）。

用法（任意 Python >= 3.9）：
    python scripts/mcp_debug.py list                          # 列出全部工具
    python scripts/mcp_debug.py schema chart                  # 看某工具的入参 schema
    python scripts/mcp_debug.py call retrieve_search '{"question": "GMV", "top_k": 2}'
    python scripts/mcp_debug.py call chart '{"spec": {...}}'  # 图片块自动存成文件

选项：
    --url    默认 https://mcp.super-data-analytics.online/mcp（或环境变量 SDA_MCP_URL）
    --token  默认读 ~/.sda_mcp_token.txt（或环境变量 SDA_MCP_TOKEN）

原理：对 streamable-http 端点直接 POST JSON-RPC（服务端为 stateless JSON 模式），
返回体兼容纯 JSON 与 SSE（data: 行）两种形态。
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://mcp.super-data-analytics.online/mcp"
TOKEN_FILE = Path.home() / ".sda_mcp_token.txt"
ACCEPT = "application/json, text/event-stream"


def _die(msg: str) -> None:
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def _load_token(cli_token: str | None) -> str:
    token = cli_token or os.environ.get("SDA_MCP_TOKEN") or (
        TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else "")
    if not token:
        _die(f"未提供 token（--token / 环境变量 SDA_MCP_TOKEN / 文件 {TOKEN_FILE} 三选一）")
    return token


def _rpc(url: str, token: str, payload: dict, timeout: int = 180) -> dict:
    """POST 一条 JSON-RPC，返回解析后的结果对象。"""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": ACCEPT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        _die(f"HTTP {e.code}（401=token 错；406=缺 Accept 头）: {e.read().decode('utf-8', 'ignore')[:300]}")
    except urllib.error.URLError as e:
        _die(f"连接失败（检查网络/防火墙/容器）: {e.reason}")

    # 服务端可能返回纯 JSON，也可能返回 SSE（event: message + data: {...}）
    data = body
    if body.lstrip().startswith("event:") or "\ndata: " in body:
        lines = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
        if not lines:
            _die(f"返回体无 data: 行:\n{body[:300]}")
        data = lines[-1]
    msg = json.loads(data)
    if "error" in msg:
        _die(f"JSON-RPC 错误: {json.dumps(msg['error'], ensure_ascii=False)}")
    return msg["result"]


def _save_image_blocks(content: list) -> None:
    """结果里的 ImageContent 块（如 chart）落盘为文件。"""
    n = 0
    for i, block in enumerate(content):
        btype = block.get("type")
        if btype == "image":
            n += 1
            ext = "png" if "png" in (block.get("mimeType") or "") else "bin"
            out = Path(f"mcp_debug_img_{n}.{ext}")
            out.write_bytes(base64.b64decode(block["data"]))
            print(f"[图片块 {n}] 已保存 {out.resolve()}（mimeType={block.get('mimeType')}）")
        elif btype not in ("text",):
            print(f"[块 {i}] type={btype}（未处理，字段: {list(block)}）")
    if n == 0 and any(b.get("type") == "image" for b in content) is False:
        pass  # 无图片块，正常


def cmd_list(args) -> None:
    result = _rpc(args.url, args.token, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = result["tools"]
    print(f"共 {len(tools)} 个工具：\n")
    for t in tools:
        desc = (t.get("description") or "").splitlines()[0]
        print(f"  {t['name']:<24} {desc}")
    print("\n看某工具入参: python scripts/mcp_debug.py schema <工具名>")


def cmd_schema(args) -> None:
    result = _rpc(args.url, args.token, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool = next((t for t in result["tools"] if t["name"] == args.tool), None)
    if tool is None:
        _die(f"工具 {args.tool} 不存在（用 list 查看）")
    print(f"# {tool['name']}\n# {tool.get('description', '')}\n")
    print(json.dumps(tool.get("inputSchema", {}), ensure_ascii=False, indent=2))


def cmd_call(args) -> None:
    try:
        arguments = json.loads(args.arguments) if args.arguments else {}
    except json.JSONDecodeError as e:
        _die(f"第二个参数不是合法 JSON: {e}\n示例: '{json.dumps({'question': 'GMV'}, ensure_ascii=False)}'")
    result = _rpc(args.url, args.token, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": args.tool, "arguments": arguments},
    }, timeout=args.timeout)
    is_error = result.get("isError")
    print(f"isError: {bool(is_error)}\n")
    content = result.get("content", [])
    for block in content:
        if block.get("type") == "text":
            print(block["text"])
    structured = result.get("structuredContent")
    if structured is not None:
        print("\n# structuredContent:")
        print(json.dumps(structured, ensure_ascii=False, indent=2))
    _save_image_blocks(content)
    if is_error:
        sys.exit(1)


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 控制台打印中文
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("SDA_MCP_URL", DEFAULT_URL))
    parser.add_argument("--token", default=None, help=f"缺省读 {TOKEN_FILE}")
    parser.add_argument("--timeout", type=int, default=180, help="call 超时秒数（默认 180，图片生成较慢）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出全部工具")
    p_schema = sub.add_parser("schema", help="打印工具入参 schema")
    p_schema.add_argument("tool")
    p_call = sub.add_parser("call", help="调用工具（第二参数为 JSON 参数串）")
    p_call.add_argument("tool")
    p_call.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args()
    args.token = _load_token(args.token)

    {"list": cmd_list, "schema": cmd_schema, "call": cmd_call}[args.cmd](args)


if __name__ == "__main__":
    main()
